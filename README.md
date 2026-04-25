# Charge Amps for Home Assistant

This repository contains a [Charge Amps](https://www.chargeamps.com/) component for [Home Assistant](https://www.home-assistant.io/).

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

The module is developed by [Kirei AB](https://www.kirei.se) and is not supported by [Charge Amps AB](https://chargeamps.com).

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

### Real-time Updates (Optional Webhooks)
For instant updates when charging starts or stops, you can configure webhooks:
1. After setup, check your Home Assistant logs for your unique `webhook_id`.
2. Configure the following URL in your Charge Amps portal: `https://<your-ha-url>/api/webhook/<webhook_id>`.

### Hardware Support
Includes specific naming and icons for:
- **Aura**
- **Dawn**
- **Halo** (including specific **Schuko** socket support).

## Diagnostics
If you encounter issues, you can download a redacted diagnostics file from the integration page to help with troubleshooting.

## Services
The integration also supports legacy services for advanced automations (see `services.yaml` for details).

---
*Disclaimer: This integration is an independent project and is not affiliated with Charge Amps AB.*
