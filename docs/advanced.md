# Advanced setup and troubleshooting

Start with the [simple installation guide](../README.md). This page is for separate IoT networks, manual keys, migration and development.

## Manual installation without HACS

Download `ac_mitm.zip` from the [latest release](https://github.com/dtechterminal/ha-panasonic-miraie-local/releases/latest), extract it, and copy its `custom_components/ac_mitm` folder into Home Assistant's `/config/custom_components/` directory. Restart Home Assistant, then add **Panasonic AC Local** from Devices & services. Device keys are stored in the HA config entry, outside the integration folder.

## Network requirements

### HA and AC on the same VLAN

This is the simplest setup. HA sends UDP to the AC on port **5001**; the tested AC broadcasts replies to **255.255.255.255:5002**. HA must receive those broadcasts. In container installations, the container's network must expose the relevant LAN interface and UDP 5002.

If automatic discovery fails, setup offers the AC's IPv4 address and transport settings. Use a DHCP reservation so its address stays stable. Some networks suppress broadcasts; merely opening UDP between VLANs does not route a limited broadcast.

### Separate IoT VLAN

The AC replies to the local broadcast address `255.255.255.255:5002`. Opening firewall ports between VLANs does not route this broadcast.

Version 2.1 adds a receiver **inside Home Assistant**. Automatic mode listens for normal UDP replies and, where available, AC packets already reaching HA's Linux network interface. It handles VLAN tags both in Ethernet frames and in NIC offload metadata. Commands continue through the existing unicast route to the AC.

For this to work across VLANs:

- The switch and VM network must already carry the AC VLAN to HA's interface (a VLAN trunk), or HA must have an interface on the AC VLAN.
- The HA process needs existing `CAP_NET_RAW` permission for the packet receiver. The integration does not grant privileges, enable promiscuous mode, add interfaces, or change firewall rules.
- VLAN-tagged broadcast traffic must reach that interface. The receiver cannot recover traffic that the switch or hypervisor removes.

If the packet receiver is unavailable, Automatic mode continues with standard UDP. In a separate VLAN this will fail verification unless an ordinary local receive path exists. A properly filtered HA interface on the AC VLAN is another option. Configure the actual network boundary deliberately; the integration cannot create cross-VLAN connectivity on its own.

Enter the AC IP when discovery cannot cross the VLAN boundary. Advanced setup allows an explicit network adapter and receive VLAN ID; otherwise the adapter is selected from HA's IPv4 route to the AC. Override the adapter when policy routing or a separate receive interface makes that route unsuitable. Standard UDP and HA-local VLAN receiver can also be selected explicitly.

The receiver validates IP/UDP lengths and checksums, source IP/ports, optional VLAN, device ID and decrypted status. It only retains accepted AC replies for the current exchange. AES-CBC itself does not provide cryptographic authentication.

**Upgrading from 2.0:** router SSH transport has been removed. Existing gateway entries migrate to Automatic while retaining device keys and entity IDs; obsolete gateway settings are removed. If VLAN replies do not already reach HA, configure a local receive path. The integration cannot remove keys previously installed on a router: revoke those separately. An entry you disabled stays disabled until you enable it.

### Existing HTTP bridge

An advanced compatibility option retains older local HTTP bridge installations. It requires an already working native UDP bridge. Its account/bootstrap and verification behavior belongs to that bridge; the native setup described above applies to the built-in local transports. New installations should use native mode.

## Block cloud access after local verification

Create an outbound **internet/WAN-only** block for the AC, covering IPv4 and IPv6. Keep it connected to Wi-Fi and keep LAN access allowed. Preserve DHCP/DNS as needed, UDP 5001 to the AC, UDP 5002 replies.

Do not use a device pause/disconnect feature that also blocks LAN traffic. An existing proxy or relay can provide another cloud route; remove it if you want complete isolation. Vendor apps and cloud-dependent features may stop working.

The integration advises you after a successful local write/readback test. It **does not configure your firewall or claim to detect a WAN block**. If you apply a block during setup, the final local test checks that the local path still works. Automatic discovery and status parsing do not by themselves prove that internet access is blocked.

## Entities and controls

- Climate: power, HVAC mode, target temperature, AC fan speed, swing, room temperature.
- Switches: display, powerful, economy, coil cleaning.
- Select: convertible capacity limit.

Optional feature entities report availability from the device's local state. Feature support varies by model. Historical energy statistics, cloud schedules, firmware updates and unsupported model features are not implemented.

Economy uses `acem`; coil cleaning uses `acec`. Swing/capacity fields are sent as JSON integers. Commands require device readback, retry lost UDP packets, and tolerate intermediate acknowledgements while settings settle. Failed commands are surfaced to HA instead of being reported as successful optimistically.

## Migrate an earlier installation

Existing `ac_mitm` entries and entity unique IDs remain supported. Reconfigure the integration to move an HTTP bridge entry to native mode while retaining its entity IDs. Update dashboard cards, automations and scripts to use the local climate entity before removing a separate `panasonic_miraie` cloud integration. Existing automations linking the AC to ceiling fans continue to apply if you migrate their references.

## Troubleshooting

- **No ACs after login:** check that this is the Panasonic India MirAIe account and that the device is already registered there.
- **No local key:** the model/account may not expose this protocol. Do not block WAN yet.
- **Local verification fails:** check the AC IP, same-VLAN broadcast path, UDP 5001/5002, and local key. For separate VLANs, check the network trunk, receive adapter and existing packet-socket permissions.
- **Bridge works but native discovery fails:** broadcast replies may be on a different VLAN. Enter the AC IP and use Automatic with a working local VLAN receive path.
- **Features unavailable:** local keys and a responding device do not guarantee support for every model-specific control.

## Protocol and development

The tested firmware accepts device-ID TLV type `0`, followed by encrypted command TLV type `1`, and replies with encrypted type `2`. JSON uses AES-256-CBC with zero padding. Discovery uses `DISC_REQ_<registered MAC>` and an encrypted `DISC_RSP_...` response. AES-CBC is not a cryptographic message-authentication code.

Run the standalone protocol/client tests with Python 3.13+:

```sh
python -m pip install pytest pytest-asyncio cryptography aiohttp scapy ruff
ruff check .
pytest -q
```

Tests cover malformed/wrong-device frames, numeric settings, dropped packets, intermediate acknowledgements, a rejected setting change, temperature restoration, and account bootstrap without persisting password/token. See [testing](testing.md) for release-specific live results and their limits. Same-VLAN discovery is implemented and covered at the packet/transport level; broader model/network compatibility needs testing.

Licensed under MIT. Please report model, firmware, network topology and redacted errors when filing an issue. Never include account passwords, local keys, HA tokens or raw configuration entries.
