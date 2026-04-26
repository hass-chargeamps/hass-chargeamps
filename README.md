# Charge Amps for Home Assistant

This repository contains a [Charge Amps](https://www.chargeamps.com/) component for [Home Assistant](https://www.home-assistant.io/).

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

The module was originally developed by [Kirei AB](https://www.kirei.se) and is not supported by [Charge Amps AB](https://chargeamps.com).

## Installation

### Via HACS (Recommended)
1. Open HACS in Home Assistant.
2. Search for "Chargeamps".
3. Click "Install".
4. Restart Home Assistant.

### Manual
Copy `custom_components/chargeamps` into your Home Assistant `config/custom_components/` directory and restart.

## Setup

1. In Home Assistant, go to **Settings** -> **Devices & Services**.
2. Click **Add Integration** and search for **Chargeamps**.
3. Enter your credentials:
   - **Email**: Your Charge Amps account email.
   - **Password**: Your Charge Amps account password.
   - **API Key**: Required (Get one from [Charge Amps Support](https://www.chargeamps.com/support/)).
4. Click **Submit**.

## Features

### Modern Entity-First Design
The integration provides standard Home Assistant entities for full control and monitoring:
- **Sensors**: Status, Power (W), Total Energy (kWh), and detailed Per-Phase Current (A) and Voltage (V).
- **Switches**: Enable or disable charging connectors.
- **Lights**: Control downlight and dimmer functionality (with brightness support).
- **Locks**: Lock or unlock the charging cable.
- **Numbers**: Set the maximum current limit (A) directly from the UI.
- **Buttons**: Remotely reboot the charge point hardware.

### Real-time Updates (Optional Callbacks)
By default the integration polls the Charge Amps API every 30 seconds. For instant updates when charging starts, stops, or the charger sends a heartbeat, you can ask Charge Amps to push events directly to your Home Assistant instance.

> **Note:** This requires your Home Assistant to be reachable from the internet (e.g. via [Nabu Casa / Home Assistant Cloud](https://www.nabucasa.com/) or your own reverse proxy). It also requires contacting Charge Amps support — it is not self-service.

#### Step 1 — Find your callback credentials

When the integration is first set up, a **persistent notification** appears in the Home Assistant UI titled **"Charge Amps Webhook Credentials"**. It contains the three things you need to give Charge Amps support:

| Field | Example |
|---|---|
| **Base URL** | `https://your-ha.duckdns.org/api/chargeamps/<entry_id>` |
| **Auth header key** | `x-api-key` |
| **Auth header value** | `a3f8...` (auto-generated token) |

Dismiss the notification once you have noted the details. The same information is always available under **Settings → Devices & Services → Chargeamps → Download diagnostics** in the `webhook` section.

#### Step 2 — Verify reachability

Before contacting support, confirm your setup works with a quick `curl`:

```bash
curl -i -H "x-api-key: <your-secret>" https://<your-ha-url>/api/chargeamps/<entry_id>
```

| Response | Meaning |
|---|---|
| `200 OK` | URL and secret are correct — ready to hand to Charge Amps |
| `401 Unauthorized` | URL is correct but secret is wrong |
| `404 Not Found` | URL is wrong (typo, wrong entry_id, or HA not reachable externally) |

#### Step 3 — Contact Charge Amps support

Email Charge Amps support and ask them to configure callbacks for your charge point. Provide the three values above. Charge Amps will then POST events to your Home Assistant on each of the following:

| Event | Trigger |
|---|---|
| `boot` | Charge point rebooted |
| `heartbeat` | Status update every ~30 s (idle only) |
| `metervalue` | Power/energy reading every ~30 s (charging only) |
| `Start` | Charging session started |
| `Stop` | Charging session ended |

### Hardware Support
Includes specific naming and icons for:
- **Aura**
- **Dawn**
- **Halo** (including specific **Schuko** socket support).

## Diagnostics
Go to **Settings → Devices & Services → Chargeamps → Download diagnostics** to get a file useful for troubleshooting. Sensitive credentials (email, password, API key) are redacted. The callback base URL, auth header key, and webhook token are included in plain text so you can retrieve them if needed.

## Services
The integration also supports legacy services for advanced automations (see `services.yaml` for details).

---
*Disclaimer: This integration is an independent project and is not affiliated with Charge Amps AB.*
