"""Independent Scapy frames exercise validation before packets reach the AC API."""

import socket
import struct

import pytest
from scapy.layers.inet import IP, UDP
from scapy.layers.l2 import Dot1Q, Ether
from scapy.packet import Raw

from custom_components.ac_mitm.packet import decode_frame, route_interface
from custom_components.ac_mitm.transport import local_config

HOST = "192.0.2.44"
PAYLOAD = b"fixture encrypted response with odd length"


def frame(payload=PAYLOAD, tags=(2,), ip=None, udp=None):
    packet = Ether(src="02:00:00:00:00:44", dst="ff:ff:ff:ff:ff:ff")
    for tag in tags:
        packet /= Dot1Q(vlan=tag)
    packet /= IP(**{"src": HOST, "dst": "255.255.255.255", **(ip or {})})
    packet /= UDP(**{"sport": 5001, "dport": 5002, **(udp or {})}) / Raw(payload)
    return bytes(packet)


def aux_vlan(vlan, valid=True):
    return [(263, 8, struct.pack("=IIIHHHH", 16 if valid else 0, 100, 100, 0, 14, vlan, 0x8100))]


@pytest.mark.parametrize("tags", [(), (2,), (100, 2)])
def test_receives_untagged_vlan_and_double_tagged_replies(tags):
    assert decode_frame(frame(tags=tags), [], HOST) == PAYLOAD


def test_receives_offloaded_vlan_and_requires_requested_vlan():
    wire = frame(tags=())
    assert decode_frame(wire, aux_vlan(2), HOST, 2) == PAYLOAD
    assert decode_frame(wire, aux_vlan(3), HOST, 2) is None
    assert decode_frame(wire, aux_vlan(2, valid=False), HOST, 2) is None
    assert decode_frame(frame(), [], HOST, 3) is None
    assert decode_frame(frame(), aux_vlan(100), HOST, 2) == PAYLOAD


@pytest.mark.parametrize(
    "ip,udp",
    [
        ({"src": "192.0.2.45"}, {}),
        ({"dst": "192.0.2.1"}, {}),
        ({"flags": "MF"}, {}),
        ({"frag": 1}, {}),
        ({"version": 6}, {}),
        ({"ihl": 4}, {}),
        ({"len": 65535}, {}),
        ({"chksum": 123}, {}),
        ({}, {"sport": 5003}),
        ({}, {"dport": 5003}),
        ({}, {"len": 7}),
        ({}, {"chksum": 123}),
    ],
)
def test_rejects_other_hosts_ports_fragments_and_invalid_headers(ip, udp):
    assert decode_frame(frame(ip=ip, udp=udp), [], HOST) is None


def test_rejects_truncation_and_corrupt_payload_accepts_padding_and_ip_options():
    wire = frame()
    assert decode_frame(wire[:-1], [], HOST) is None
    assert decode_frame(wire[:16], [], HOST) is None
    assert decode_frame(wire[:-1] + bytes([wire[-1] ^ 1]), [], HOST) is None
    assert decode_frame(wire + b"\0" * 12, [], HOST) == PAYLOAD
    assert decode_frame(frame(ip={"options": b"\x01\x01\x01\x00"}), [], HOST) == PAYLOAD
    # IPv4 permits an omitted UDP checksum; it does not permit a bad nonzero one.
    assert decode_frame(frame(udp={"chksum": 0}), [], HOST) == PAYLOAD


def test_route_selection_uses_active_longest_prefix_then_metric(monkeypatch):
    monkeypatch.setattr(
        "custom_components.ac_mitm.packet.Path.read_text",
        lambda _: (
            "Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
            "default 00000000 010200C0 0003 0 0 10 00000000\n"
            "disabled 000200C0 00000000 0000 0 0 0 00FFFFFF\n"
            "slower 000200C0 00000000 0001 0 0 100 00FFFFFF\n"
            "iot 000200C0 00000000 0001 0 0 20 00FFFFFF\n"
        ),
    )
    assert route_interface(HOST) == "iot"
    assert route_interface("198.51.100.1") == "default"


def test_migration_discards_remote_access_but_retains_local_credentials():
    original = {
        "transport": "gateway",
        "host": HOST,
        "device_id": "fixture-ac",
        "key": "01" * 32,
        "iv": "02" * 16,
        "gateway_host": "192.0.2.1",
        "gateway_key_file": "/unused/private-key",
    }
    migrated = local_config(original)
    assert migrated == {
        "transport": "auto",
        "host": HOST,
        "device_id": "fixture-ac",
        "key": "01" * 32,
        "iv": "02" * 16,
    }
    assert original["transport"] == "gateway"


def test_receiver_closes_socket_when_interface_bind_fails(monkeypatch):
    from custom_components.ac_mitm import packet

    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    monkeypatch.setattr(packet.socket, "AF_PACKET", 17, raising=False)
    monkeypatch.setattr(packet.socket, "socket", lambda *args: first)
    try:
        with pytest.raises((OSError, TypeError)):
            packet.open_receiver("invalid-interface")
        assert first.fileno() == -1
    finally:
        second.close()
