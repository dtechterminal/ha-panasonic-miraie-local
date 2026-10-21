# Panasonic AC Local for Home Assistant

Control supported Panasonic India **MirAIe** air conditioners over your LAN, including after their internet access is blocked. No Matter pairing, TLS interception, certificate replacement, or firmware modification is needed.

Tested on **CS-CU-EZ18BKYXFM, firmware 3.02**. Other MirAIe models are experimental: the AC must expose local UDP keys and implement the same protocol. This is not a Panasonic Comfort Cloud integration and is not affiliated with Panasonic.

## Install

### HACS custom repository

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/dtechterminal/ha-panasonic-miraie-local`, category **Integration**.
3. Download **Panasonic AC Local**, then restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Panasonic AC Local**.

The repository is a HACS custom repository; it is not listed in the default HACS catalog.

### Manual installation

Copy `custom_components/ac_mitm` into HA's `/config/custom_components/` directory, restart HA, then add **Panasonic AC Local**. The internal domain remains `ac_mitm` for compatibility with earlier installations; no MITM service is needed in native mode.

## Setup

The AC must already be paired with your Panasonic India MirAIe account. This integration does not perform first-time Wi-Fi onboarding.

1. Select account setup and sign in with the email/mobile number and password used by MirAIe.
2. If your account has one AC, it is selected automatically. Otherwise select the AC.
3. HA attempts encrypted LAN discovery and local control verification. During verification it briefly changes the target temperature by 1°C and restores it. It does not change the power state.
4. After verification succeeds, setup explains how to optionally block the AC's internet access. Apply the WAN block if desired, then finish setup. Local control is tested again before the entry is saved.

Your Panasonic account is needed **once to obtain the AC's local encryption keys**. Passwords and account tokens are not saved. The local device ID, AES key and IV are saved in the HA configuration entry, which is sensitive and should be protected in backups. If you already have those local values, choose **Enter existing local keys** and skip account login entirely.

All polling and commands in native mode use LAN UDP. There is no runtime cloud fallback or periodic login. Cloud APIs are unofficial and may change; a reset or re-pairing may invalidate local keys, requiring setup again.

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
