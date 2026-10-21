"""Local UDP with an optional receiver for VLAN frames already reaching HA."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket

from .packet import decode_frame, open_receiver, route_interface
from .protocol import Protocol, ProtocolError, matches

_LOGGER = logging.getLogger(__name__)
REPLY_TIMEOUT = 3
COLLECT_WINDOW = 0.08


def local_config(config: dict) -> dict:
    """Remove obsolete remote-access settings, retaining device credentials."""
    result = {k: v for k, v in config.items() if not k.startswith("gateway_")}
    if result.get("transport") in (None, "gateway"):
        result["transport"] = "auto"
    return result


class UdpTransport:
    def __init__(self, config: dict, direct_lock: asyncio.Lock):
        self.config = local_config(config)
        self.host = str(ipaddress.IPv4Address(config["host"]))
        self.direct_lock = direct_lock
        self.protocol = Protocol(config["device_id"], config["key"], config["iv"])
        self.last_receiver = None
        self._interface = self.config.get("packet_interface") or None
        self._packet_unavailable = False

    async def _open_packet_socket(self):
        if self.config["transport"] == "direct" or self._packet_unavailable:
            return None
        try:
            if not self._interface:
                self._interface = await asyncio.to_thread(route_interface, self.host)
            if not self._interface:
                raise OSError("No local interface for the AC route")
            return open_receiver(self._interface)
        except OSError:
            if self.config["transport"] == "packet":
                raise
            self._packet_unavailable = True
            _LOGGER.debug("Local packet receiver unavailable; using standard UDP")
            return None

    async def exchange(self, packet: bytes, *, expected: dict | None = None) -> list[bytes]:
        async with self.direct_lock:
            return await self._local_exchange(packet, expected)

    async def _local_exchange(self, packet: bytes, expected: dict | None) -> list[bytes]:
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=32)
        replies, seen = [], set()
        raw = None

        def accept(wire, receiver):
            try:
                state = self.protocol.decode(wire)
            except (ProtocolError, ValueError):
                return
            if wire not in seen and not queue.full():
                seen.add(wire)
                queue.put_nowait((wire, receiver, matches(state, expected or {})))

        def read_raw():
            # Bound work per callback so unrelated LAN traffic cannot monopolize HA.
            for _ in range(32):
                try:
                    frame, ancillary, flags, _ = raw.recvmsg(65535, 128)
                except BlockingIOError:
                    return
                except OSError:
                    loop.remove_reader(raw.fileno())
                    return
                if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
                    continue
                wire = decode_frame(frame, ancillary, self.host, self.config.get("vlan_id"))
                if wire:
                    accept(wire, "local_packet")

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind(("0.0.0.0", 5002))
                sock.setblocking(False)
                raw = await self._open_packet_socket()

                def read_udp():
                    for _ in range(32):
                        try:
                            wire, peer = sock.recvfrom(65535)
                        except BlockingIOError:
                            return
                        except OSError:
                            loop.remove_reader(sock.fileno())
                            return
                        if peer == (self.host, 5001):
                            accept(wire, "udp")

                loop.add_reader(sock.fileno(), read_udp)
                if raw is not None:
                    loop.add_reader(raw.fileno(), read_raw)
                await loop.sock_sendto(sock, packet, (self.host, 5001))
                deadline = loop.time() + REPLY_TIMEOUT
                while loop.time() < deadline:
                    try:
                        async with asyncio.timeout(deadline - loop.time()):
                            wire, receiver, confirmed = await queue.get()
                    except TimeoutError:
                        break
                    replies.append(wire)
                    self.last_receiver = receiver
                    if confirmed:
                        break
                    deadline = min(deadline, loop.time() + COLLECT_WINDOW)
                return replies
            finally:
                loop.remove_reader(sock.fileno())
                if raw is not None:
                    loop.remove_reader(raw.fileno())
                    raw.close()


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
