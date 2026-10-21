"""Direct LAN transport and optional Linux gateway broadcast receiver."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import socket

import asyncssh

from .protocol import Protocol, ProtocolError


# Only ciphertext and network addresses are sent to the gateway. Keys stay in HA.
GATEWAY_SCRIPT = r"""
import base64, json, select, socket, struct, time
request = json.loads(__REQUEST_JSON__)
raw = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
raw.bind((request['interface'], 0))
raw.setblocking(False)
sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sender.bind((request['source'], 0))
sender.sendto(bytes.fromhex(request['packet']), (request['host'], 5001))
deadline = time.monotonic() + 3
packets = []
while time.monotonic() < deadline:
    ready, _, _ = select.select([raw], [], [], max(0, deadline - time.monotonic()))
    if not ready:
        break
    frame = raw.recv(65535)
    if len(frame) < 42 or frame[12:14] != b'\x08\x00':
        continue
    ip = frame[14:]
    ihl = (ip[0] & 15) * 4
    if len(ip) < ihl + 8 or ip[9] != 17 or socket.inet_ntoa(ip[12:16]) != request['host']:
        continue
    udp = ip[ihl:]
    source_port, destination_port, length = struct.unpack('!HHH', udp[:6])
    if source_port != 5001 or destination_port != 5002 or length < 8 or length > len(udp):
        continue
    packets.append(base64.b64encode(udp[8:length]).decode())
    deadline = min(deadline, time.monotonic() + 0.08)
print(json.dumps(packets))
"""


class UdpTransport:
    def __init__(self, config: dict, direct_lock: asyncio.Lock):
        self.config = config
        self.host = str(ipaddress.IPv4Address(config["host"]))
        self.direct_lock = direct_lock

    async def exchange(self, packet: bytes) -> list[bytes]:
        if self.config.get("transport") == "gateway":
            return await self._gateway(packet)
        async with self.direct_lock:
            return await self._direct(packet)

    async def _direct(self, packet: bytes) -> list[bytes]:
        loop = asyncio.get_running_loop()
        replies = []
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("0.0.0.0", 5002))
            sock.setblocking(False)
            await loop.sock_sendto(sock, packet, (self.host, 5001))
            deadline = loop.time() + 3
            while loop.time() < deadline:
                try:
                    async with asyncio.timeout(deadline - loop.time()):
                        wire, peer = await loop.sock_recvfrom(sock, 65535)
                except TimeoutError:
                    break
                if peer == (self.host, 5001):
                    replies.append(wire)
                    deadline = min(deadline, loop.time() + 0.08)
        return replies

    async def _gateway(self, packet: bytes) -> list[bytes]:
        request = {
            "interface": self.config["gateway_interface"],
            "source": str(ipaddress.IPv4Address(self.config["gateway_source"])),
            "host": self.host,
            "packet": packet.hex(),
        }
        script = GATEWAY_SCRIPT.replace("__REQUEST_JSON__", repr(json.dumps(request)))
        async with asyncio.timeout(12):
            async with asyncssh.connect(
                self.config["gateway_host"],
                port=int(self.config.get("gateway_port", 22)),
                username=self.config["gateway_username"],
                client_keys=[self.config["gateway_key_file"]],
                known_hosts=self.config["gateway_known_hosts"],
                config=None,
            ) as connection:
                result = await connection.run("python3 -", input=script, check=True)
        return [base64.b64decode(value, validate=True) for value in json.loads(result.stdout)]


async def discover_host(config: dict, lock: asyncio.Lock) -> str | None:
    """Discover only the selected AC, verifying the encrypted response and device ID."""
    mac = config.get("mac", "").replace(":", "").upper()
    if not mac:
        return None
    protocol = Protocol(config["device_id"], config["key"], config["iv"])
    loop = asyncio.get_running_loop()
    async with lock:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("0.0.0.0", 5002))
            sock.setblocking(False)
            for _ in range(2):
                await loop.sock_sendto(
                    sock, ("DISC_REQ_" + mac).encode(), ("255.255.255.255", 5001)
                )
                deadline = loop.time() + 2
                while loop.time() < deadline:
                    try:
                        async with asyncio.timeout(deadline - loop.time()):
                            wire, peer = await loop.sock_recvfrom(sock, 65535)
                    except TimeoutError:
                        break
                    if peer[1] != 5001:
                        continue
                    try:
                        if protocol.decrypt(wire).upper() == ("DISC_RSP_" + mac).encode():
                            return str(ipaddress.IPv4Address(peer[0]))
                    except (ProtocolError, ValueError):
                        continue
    return None
