import asyncio
import json

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.ac_mitm.protocol import Protocol, tlv
from custom_components.ac_mitm.transport import UdpTransport, discover_host

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
