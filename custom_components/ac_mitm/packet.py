"""Receive only AC UDP replies already present on the local Linux interface."""

from __future__ import annotations

import ipaddress
from pathlib import Path
import socket
import struct

SOL_PACKET = 263
PACKET_AUXDATA = 8
TP_STATUS_VLAN_VALID = 1 << 4
VLAN_TYPES = {0x8100, 0x88A8}


def route_interface(host: str) -> str | None:
    """Find the longest matching active IPv4 route without running a command."""
    target = int(ipaddress.IPv4Address(host))
    candidates = []
    try:
        lines = Path("/proc/net/route").read_text().splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        fields = line.split()
        if len(fields) < 8:
            continue
        try:
            network = int.from_bytes(bytes.fromhex(fields[1]), "little")
            mask = int.from_bytes(bytes.fromhex(fields[7]), "little")
            flags, metric = int(fields[3], 16), int(fields[6])
        except ValueError:
            continue
        if flags & 1 and not flags & 0x200 and target & mask == network:
            candidates.append((mask.bit_count(), -metric, fields[0]))
    return max(candidates)[2] if candidates else None


def open_receiver(interface: str) -> socket.socket:
    """Use existing CAP_NET_RAW only; do not enable promiscuous mode."""
    if not hasattr(socket, "AF_PACKET"):
        raise OSError("The local VLAN receiver requires Linux")
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
    try:
        sock.bind((interface, 0))
        sock.setsockopt(SOL_PACKET, PACKET_AUXDATA, 1)
        sock.setblocking(False)
    except BaseException:
        sock.close()
        raise
    return sock


def checksum(data: bytes) -> int:
    """Internet checksum, including the odd-byte padding rule."""
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def decode_frame(
    frame: bytes, ancillary: list, host: str, vlan_id: int | None = None
) -> bytes | None:
    """Validate Ethernet/VLAN, IPv4 and UDP before handing ciphertext to the API.

    VLAN tags can be in the Ethernet frame or stripped by the NIC and supplied
    as PACKET_AUXDATA. Device identity and decrypted status are checked separately.
    Fragmented, truncated, corrupt and unrelated traffic is ignored.
    """
    if len(frame) < 42:
        return None
    kind = int.from_bytes(frame[12:14], "big")
    offset, tags = 14, []
    for level, typ, data in ancillary:
        if level == SOL_PACKET and typ == PACKET_AUXDATA and len(data) >= 20:
            aux = struct.unpack("=IIIHHHH", data[:20])
            if aux[0] & TP_STATUS_VLAN_VALID:
                tags.append(aux[5] & 0xFFF)
    while kind in VLAN_TYPES:
        if len(tags) >= 2 or len(frame) < offset + 4:
            return None
        tags.append(int.from_bytes(frame[offset : offset + 2], "big") & 0xFFF)
        kind = int.from_bytes(frame[offset + 2 : offset + 4], "big")
        offset += 4
    if kind != 0x0800 or (vlan_id is not None and (not tags or tags[-1] != vlan_id)):
        return None
    ip = frame[offset:]
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 17:
        return None
    ihl = (ip[0] & 15) * 4
    length = int.from_bytes(ip[2:4], "big")
    if ihl < 20 or length < ihl + 8 or length > len(ip):
        return None
    if int.from_bytes(ip[6:8], "big") & 0x3FFF:
        return None
    if socket.inet_ntoa(ip[12:16]) != host or ip[16:20] != b"\xff" * 4:
        return None
    if checksum(ip[:ihl]):
        return None
    udp = ip[ihl:length]
    source, destination, udp_length, udp_checksum = struct.unpack("!HHHH", udp[:8])
    if source != 5001 or destination != 5002 or udp_length != len(udp):
        return None
    pseudoheader = ip[12:20] + b"\0\x11" + struct.pack("!H", udp_length)
    if udp_checksum and checksum(pseudoheader + udp):
        return None
    return udp[8:]
