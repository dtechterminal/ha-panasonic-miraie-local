# Panasonic AC Local

<img src="custom_components/ac_mitm/brand/logo@2x.png" alt="Panasonic" width="280">

**Control your Panasonic AC from Home Assistant—even when the AC cannot access the internet.**

> **This is a fork** of [dtechterminal/ha-panasonic-miraie-local](https://github.com/dtechterminal/ha-panasonic-miraie-local) by Ankur Pandey.
> It adds decoding of the room temperature that firmware 3.02 and newer pack into `rmtmp`
> (for example `"128.25"` → 25 °C instead of showing 128.25 °C). Tested on CS-CU-NU18BKY5WX, firmware 3.02.
> To install it, add `https://github.com/M-chedalla/ha-panasonic-miraie-ac-india` in Marketplace → Custom repositories (type: Integration).

No changes to the AC, special certificates, or Matter setup are needed.

## Before you start

You need:

- Home Assistant with [HACS](https://www.hacs.dev/) installed.
- A Panasonic **India MirAIe** AC that already works in the MirAIe phone app.
- Your MirAIe email/mobile number and password.

**Tested:** Panasonic CS-CU-EZ18BKYXFM, firmware 3.02. Other models may work, but have not been confirmed. This does not support Panasonic Comfort Cloud accounts.

## 1. Install it with HACS

1. Open **HACS** in Home Assistant.
2. Search for **Panasonic AC Local**, open it, and click **Download**.
3. **Restart Home Assistant.**

Future updates appear in Home Assistant's update list.

**Added it earlier as a custom repository?** Nothing to change; updates keep working.

Home Assistant 2026.3 or newer displays the bundled Panasonic logo locally. See [brand image credits](docs/branding.md).

## 2. Add your AC

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Panasonic AC Local**.
3. Choose account setup and sign in with your **MirAIe** account.
4. If you have more than one AC, choose the one to add.
5. Wait while setup finds the AC and checks that it can control it locally.

The check briefly changes the AC’s target temperature by **1°C**, then restores it. It does not send a power-on command.

**If setup asks for the AC’s address:** find it in your router’s device list, enter it, and leave **Automatic** selected. If you use a separate IoT network, read the [separate-network guide](docs/advanced.md#separate-iot-vlan). Home Assistant must be able to receive replies from that network.

## 3. Optional: stop the AC using the internet

**Wait until setup says local control has passed.**

You can then use your router/firewall to block **only the AC’s internet access**. Keep the AC connected to Wi-Fi and allow it to communicate inside your home network.

Do **not** use a button that pauses, disconnects, or blocks the device from your entire network—that would also break local control.

Finish setup after applying your rule. The integration checks local control again. You can also finish without blocking the internet.

The integration does not change router settings for you. Panasonic’s app and cloud features may stop working after you block internet access.

## What you can control

- AC on/off, operating mode, and temperature.
- The AC’s own fan speed and swing.
- Display, Powerful mode, Economy mode, and coil cleaning.
- Capacity limit, where supported by the AC.

These controls belong to the AC. Existing Home Assistant automations may separately link it to ceiling fans or other devices.

## Common questions

**Why does it need my Panasonic account?**  
It signs in once to get the information needed for local control. Your account password and login tokens are not saved. The information needed to control the AC is saved in Home Assistant, so protect your HA backups.

**Will it keep logging in or use the cloud later?**  
No. Normal control stays inside your home network. A factory reset or re-pairing may mean you need to set it up again.

**Do I need to keep a computer running?**  
No separate Mac or computer service is needed. Home Assistant must remain running. All native control and reply handling run inside Home Assistant. Router SSH access is not used.

**Can I install without HACS, use existing local keys, or move from an older integration?**  
Yes—see the [advanced guide](docs/advanced.md).

## Need help?

[Open an issue](https://github.com/M-chedalla/ha-panasonic-miraie-ac-india/issues) with your AC model, firmware version, and the error you see. Never post passwords, local keys, or HA tokens.

This is an independent community integration, not an official Panasonic product. It is available in HACS’s default catalog.
