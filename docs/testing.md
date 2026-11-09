# Testing

## Version 2.1.0: receiver inside Home Assistant

Tested on a Panasonic CS-CU-EZ18BKYXFM, firmware 3.02, with the AC's internet access blocked. HA received VLAN 2 broadcasts on its existing Linux interface. Commands and replies used only the LAN; no router SSH connection or external bridge was used. No new network interfaces or container privileges were added.

All **40 live Home Assistant control checks passed**, with device state readback:

- Temperature: 16°C, 30°C, and 24°C.
- Fan: Auto, Low, Medium, High, Quiet, and Auto again.
- Swing: Off, On, Vertical, Horizontal, Both.
- Operating modes: Cool, Dry, Fan only, Auto, Heat, Cool.
- Dedicated power-off and power-on actions.
- Display, Powerful, Economy, and coil cleaning, each on and off.
- Capacity: Auto, 40%, 55%, 70%, 80%, 90%, 100%, 110%, Auto.
- Combined temperature and operating-mode command.

Original AC settings and automation enable states were restored. Related AC/fan automations were paused during the control matrix. The separate ceiling fan's state and speed were unchanged.

### Measured latency

These measurements include the HA service request and confirmed device state, not just the first network packet:

| Check | Observed time |
|---|---|
| Temperature changes | 247–388 ms |
| Fan speed | 188–438 ms |
| Swing | 720–1,528 ms |
| Median across all 40 checks | 775 ms |
| Slowest check, heat mode including retry | 3,853 ms |

An earlier read-only investigation measured five raw status replies at 56–194 ms (median 58 ms). That is a different measurement and should not be presented as command latency. Commands return as soon as a reply confirms all requested fields; intermediate acknowledgements and lost packets can require further polling or retries.

A separate instrumented temperature change sent the command after 9 ms, received confirmed state 384 ms after sending, and completed about 4 ms later. That places most of this sample's delay between transmission and reply, rather than in integration processing. It does not distinguish firmware processing from Wi-Fi/network delay. A single-axis swing change in the same probe took 206 ms overall; timings vary with the command and device state.

Readback confirms the firmware accepted a setting. It does not measure physical heating/cooling output, airflow, coil cleanliness, energy savings, or long-term reliability.

### Setup and migration

- Existing version 1 config entry migrated to version 2 while retaining its device credentials and entity IDs.
- Obsolete router-access settings were removed; no dedicated router SSH key remained in HA.
- Reconfigure opened network settings directly using the existing local keys, without another account login.
- A real temperature change and restoration passed before firewall guidance, and again before saving.
- Automatic mode selected the HA-local packet receiver on the existing interface.

The account bootstrap was tested live in 2.0.0 and remains covered by unit tests; another live account login was not required for this upgrade. HACS custom-repository registration was previously verified. This repository is not in the default HACS catalog.

## Automated tests

**45 passing cases** cover native framing and commands, encrypted wrong-device rejection, malformed replies, retries, intermediate acknowledgements, setup restoration, account errors and secret handling, real UDP transport and discovery, VLAN tags and offload metadata, IP/UDP checksums, fragmentation/truncation rejection, route selection, migration cleanup, packet-permission fallback, socket cancellation cleanup, and immediate completion after confirmed readback.

Packet fixtures are encoded independently with Scapy. The asynchronous receiver is exercised with real file descriptors without requiring root in CI. Ruff passes; the test-quality review found no zero-assertion or tautological tests.

GitHub Actions runs the tests, hassfest and the full HACS validation, including the brands check.

## Network compatibility limits

The packet receiver requires Linux, existing packet-socket permission, and the AC VLAN's traffic actually reaching HA. It cannot bypass a switch, hypervisor or firewall that does not deliver those packets. Standard same-VLAN UDP is covered by loopback transport tests; broader model and network compatibility requires testing.
