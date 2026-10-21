# Advanced setup and troubleshooting

Start with the [simple installation guide](../README.md). This page is for separate IoT networks, manual keys, migration and development.

## Manual installation without HACS

Download `ac_mitm.zip` from the [latest release](https://github.com/dtechterminal/ha-panasonic-miraie-local/releases/latest), extract it, and copy its `custom_components/ac_mitm` folder into Home Assistant's `/config/custom_components/` directory. Restart Home Assistant, then add **Panasonic AC Local** from Devices & services. Keep local keys and SSH files outside the integration folder so updates do not overwrite them.

## Network requirements

### HA and AC on the same VLAN

This is the simplest setup. HA sends UDP to the AC on port **5001**; the tested AC broadcasts replies to **255.255.255.255:5002**. HA must receive those broadcasts. In container installations, the container's network must expose the relevant LAN interface and UDP 5002.

If automatic discovery fails, setup offers the AC's IPv4 address and transport settings. Use a DHCP reservation so its address stays stable. Some networks suppress broadcasts; merely opening UDP between VLANs does not route a limited broadcast.

### Separate IoT VLAN: optional Linux gateway receiver

An advanced transport can receive the AC's replies on its own VLAN and pass the encrypted packets to HA over SSH. It runs directly from HA; it does not need a Mac, extra bridge daemon, or firewall redirects.

Prepare these once:

- A Linux gateway with Python 3 and an interface on the AC VLAN.
- An SSH account able to create an `AF_PACKET` raw socket, normally root or an appropriately configured account with `CAP_NET_RAW`.
- A dedicated, unencrypted SSH private key accessible **inside HA Core**, such as `/config/.ssh/panasonic_local_ed25519`, with mode `0600`. Add its public key to the gateway's authorized keys.
- A `known_hosts` file inside HA containing the gateway's **verified** host key. Host-key verification is mandatory; it is never disabled by the integration.

When discovery falls back to network settings, select **Linux gateway over SSH**, then provide its SSH host/user, key and known-hosts paths, VLAN interface, and IPv4 address on the AC VLAN. These values are network-specific. Only ciphertext and network addresses are sent to the gateway; the AES key stays in HA.

The gateway executes a short Python receiver per exchange. No gateway service is installed, no routing/firewall rules are edited, and no persistent remote program is deployed. A forced `python3 -` SSH command limits command selection but still executes Python from HA, so the SSH account remains a privileged trust relationship.

### Existing HTTP bridge

An advanced compatibility option retains older local HTTP bridge installations. It requires an already working native UDP bridge. Its account/bootstrap, gateway and verification behavior belongs to that bridge; the seamless native setup described above applies to direct/gateway mode. New installations should use native mode.

## Block cloud access after local verification

Create an outbound **internet/WAN-only** block for the AC, covering IPv4 and IPv6. Keep it connected to Wi-Fi and keep LAN access allowed. Preserve DHCP/DNS as needed, UDP 5001 to the AC, UDP 5002 replies, and HA-to-gateway SSH if using that transport.

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
- **Local verification fails:** check the AC IP, same-VLAN broadcast path, UDP 5001/5002, and local key. For gateway mode, also check SSH authentication, verified host keys, interface/source address, Python and raw-socket privileges.
- **Bridge works but native discovery fails:** broadcast replies may be on a different VLAN. Choose the gateway transport or place HA on the AC VLAN.
- **Features unavailable:** local keys and a responding device do not guarantee support for every model-specific control.

## Protocol and development

The tested firmware accepts device-ID TLV type `0`, followed by encrypted command TLV type `1`, and replies with encrypted type `2`. JSON uses AES-256-CBC with zero padding. Discovery uses `DISC_REQ_<registered MAC>` and an encrypted `DISC_RSP_...` response. AES-CBC is not a cryptographic message-authentication code.

Run the standalone protocol/client tests with Python 3.13+:

```sh
python -m pip install pytest pytest-asyncio cryptography asyncssh==2.24.1 aiohttp ruff
ruff check .
pytest -q
```

Tests cover malformed/wrong-device frames, numeric settings, dropped packets, intermediate acknowledgements, a rejected setting change, temperature restoration, and account bootstrap without persisting password/token. Live testing on the model above also verified HA commands with WAN blocked and the optional gateway transport. Same-VLAN discovery is implemented and covered at the packet/transport level; broader model/network compatibility needs testing.

Licensed under MIT. Please report model, firmware, network topology and redacted errors when filing an issue. Never include account passwords, local keys, HA tokens or raw configuration entries.
