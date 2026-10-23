# Loomy for Home Assistant

Reads out your Loomy dongle via your local area network.

## Sensors

| Sensor | Unit |
|---|---|
| Energy consumption (day + night) | kWh |
| Energy injection (day + night) | kWh |
| Power consumption | kW |
| Power injection | kW |
| Gas | m³ |
| Water | m³ |

## Installation

### Manual

Requires Home Assistant 2025.3 or newer.

Copy `custom_components/loomy` into the `custom_components` folder of your Home Assistant configuration and restart Home Assistant.

### HACS

The integration can be set up via HACS. Add `https://github.com/loomyhq/loomy-ha` as a custom repository and then add the integration.

## Setup

Go to **Settings → Devices & services → Add integration → Loomy** and enter the IP address of your Loomy device.
