import asyncio
import json
import socket

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.ac_mitm.protocol import Protocol, tlv
from custom_components.ac_mitm.transport import UdpTransport, discover_host
from test_packet import frame

CONFIG = {
    "device_id": "fixture-ac",
    "key": "01" * 32,
    "iv": "02" * 16,
    "mac": "00:00:00:00:00:01",
    "host": "127.0.0.1",
    "transport": "direct",
}


def encrypted_reply(raw, device_id=b"fixture-ac"):
    raw += b"\0" * (-len(raw) % 16)
    enc = Cipher(
        algorithms.AES(bytes.fromhex(CONFIG["key"])), modes.CBC(bytes.fromhex(CONFIG["iv"]))
    ).encryptor()
    return tlv(0, device_id) + tlv(2, enc.update(raw) + enc.finalize())


class Device(asyncio.DatagramProtocol):
    def __init__(self, discovery=False):
        self.discovery = discovery
        self.requests = []

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, wire, peer):
        self.requests.append(wire)
        if self.discovery:
            # First send a different device's packet to verify discovery skips it.
            self.transport.sendto(
                encrypted_reply(b"DISC_RSP_000000000001", b"another-device"), peer
            )
            self.transport.sendto(encrypted_reply(b"DISC_RSP_000000000001"), peer)
        else:
            self.transport.sendto(
                encrypted_reply(json.dumps({"ps": "off", "actmp": "24"}).encode()), peer
            )


@pytest.mark.asyncio
async def test_real_udp_exchange_receives_and_decodes_status():
    loop = asyncio.get_running_loop()
    device = Device()
    endpoint, _ = await loop.create_datagram_endpoint(
        lambda: device, local_addr=("127.0.0.1", 5001)
    )
    try:
        transport = UdpTransport(CONFIG, asyncio.Lock())
        protocol = Protocol(CONFIG["device_id"], CONFIG["key"], CONFIG["iv"])
        replies = await transport.exchange(protocol.encode())
        assert protocol.decode(replies[-1]) == {"ps": "off", "actmp": "24"}
        assert device.requests and device.requests[0][0] == 0
    finally:
        endpoint.close()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_discovery_finds_selected_device_and_rejects_other_device(monkeypatch):
    loop = asyncio.get_running_loop()
    real_send = loop.sock_sendto

    async def send_locally(sock, data, address):
        assert address == ("255.255.255.255", 5001)
        return await real_send(sock, data, ("127.0.0.1", 5001))

    monkeypatch.setattr(loop, "sock_sendto", send_locally)
    device = Device(discovery=True)
    endpoint, _ = await loop.create_datagram_endpoint(
        lambda: device, local_addr=("127.0.0.1", 5001)
    )
    try:
        host = await discover_host(CONFIG, asyncio.Lock())
        assert host == "127.0.0.1"
        assert device.requests == [b"DISC_REQ_000000000001"]
    finally:
        endpoint.close()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_local_packet_path_reads_vlan_reply_and_rejects_wrong_device(monkeypatch):
    loop = asyncio.get_running_loop()
    receiver, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.setblocking(False)
    monkeypatch.setattr("custom_components.ac_mitm.transport.open_receiver", lambda _: receiver)
    valid = encrypted_reply(b'{"ps":"off","actmp":"25"}')
    wrong = encrypted_reply(b'{"ps":"off","actmp":"16"}', b"another-device")

    class PacketDevice(Device):
        def datagram_received(self, wire, peer):
            self.requests.append(wire)
            sender.send(frame(wrong, ip={"src": "127.0.0.1"}))
            # Invalid packets must not start the short collection deadline.
            loop.call_later(0.15, sender.send, frame(valid, ip={"src": "127.0.0.1"}))

    device = PacketDevice()
    endpoint, _ = await loop.create_datagram_endpoint(
        lambda: device, local_addr=("127.0.0.1", 5001)
    )
    try:
        transport = UdpTransport(
            {**CONFIG, "transport": "auto", "packet_interface": "fixture", "vlan_id": 2},
            asyncio.Lock(),
        )
        protocol = Protocol(CONFIG["device_id"], CONFIG["key"], CONFIG["iv"])
        replies = await transport.exchange(protocol.encode())
        assert [protocol.decode(wire) for wire in replies] == [{"ps": "off", "actmp": "25"}]
        assert transport.last_receiver == "local_packet"
        assert device.requests == [protocol.encode()]
        assert receiver.fileno() == -1
    finally:
        sender.close()
        receiver.close()
        endpoint.close()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_auto_mode_uses_udp_when_packet_permission_is_unavailable(monkeypatch):
    def denied(_):
        raise PermissionError("No CAP_NET_RAW")

    monkeypatch.setattr("custom_components.ac_mitm.transport.open_receiver", denied)
    loop = asyncio.get_running_loop()
    endpoint, _ = await loop.create_datagram_endpoint(Device, local_addr=("127.0.0.1", 5001))
    try:
        transport = UdpTransport(
            {**CONFIG, "transport": "auto", "packet_interface": "fixture"}, asyncio.Lock()
        )
        protocol = Protocol(CONFIG["device_id"], CONFIG["key"], CONFIG["iv"])
        replies = await transport.exchange(protocol.encode())
        assert protocol.decode(replies[-1]) == {"ps": "off", "actmp": "24"}
        assert transport.last_receiver == "udp"
    finally:
        endpoint.close()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_command_waits_for_applied_state_then_returns_without_fixed_delay(monkeypatch):
    loop = asyncio.get_running_loop()
    monkeypatch.setattr("custom_components.ac_mitm.transport.COLLECT_WINDOW", 3)

    class SettlingDevice(Device):
        def datagram_received(self, wire, peer):
            self.transport.sendto(encrypted_reply(b'{"ps":"off","actmp":"24"}'), peer)
            loop.call_later(
                0.03,
                self.transport.sendto,
                encrypted_reply(b'{"ps":"off","actmp":"25"}'),
                peer,
            )

    endpoint, _ = await loop.create_datagram_endpoint(
        SettlingDevice, local_addr=("127.0.0.1", 5001)
    )
    try:
        transport = UdpTransport(CONFIG, asyncio.Lock())
        replies = await asyncio.wait_for(
            transport.exchange(
                transport.protocol.encode({"actmp": "25"}), expected={"actmp": "25"}
            ),
            timeout=0.8,
        )
        assert [transport.protocol.decode(wire)["actmp"] for wire in replies] == ["24", "25"]
    finally:
        endpoint.close()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_cancelled_exchange_closes_packet_socket_and_releases_udp_port(monkeypatch):
    receiver, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.setblocking(False)
    monkeypatch.setattr("custom_components.ac_mitm.transport.open_receiver", lambda _: receiver)
    loop = asyncio.get_running_loop()
    sent = asyncio.Event()
    real_send = loop.sock_sendto

    async def send(sock, wire, destination):
        result = await real_send(sock, wire, destination)
        sent.set()
        return result

    monkeypatch.setattr(loop, "sock_sendto", send)
    transport = UdpTransport(
        {**CONFIG, "transport": "auto", "packet_interface": "fixture"}, asyncio.Lock()
    )
    task = asyncio.create_task(transport.exchange(transport.protocol.encode()))
    try:
        await asyncio.wait_for(sent.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert receiver.fileno() == -1
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("0.0.0.0", 5002))
            assert probe.getsockname()[1] == 5002
        assert not transport.direct_lock.locked()
    finally:
        task.cancel()
        sender.close()
        receiver.close()
