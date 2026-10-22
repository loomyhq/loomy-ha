# Loomy for Home Assistant

Reads your smart meter through a Loomy device on your local network.

## Sensors

| Sensor | Unit |
|---|---|
| Energy consumption (day + night) | kWh |
| Energy injection (day + night) | kWh |
| Power consumption | kW |
| Power injection | kW |
| Gas | m³ |
| Water | m³ |

The energy, gas and water sensors can be used in the Energy dashboard.

## Installation

Requires Home Assistant 2025.3 or newer.

Copy `custom_components/loomy` into the `custom_components` folder of your Home Assistant configuration and restart Home Assistant.

## Setup

Go to **Settings → Devices & services → Add integration → Loomy** and enter the IP address of your Loomy device.
