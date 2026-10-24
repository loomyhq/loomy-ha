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

## Development

The checks that CI runs can be run locally with Python 3.14 or newer:

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check .
mypy custom_components
pytest
```

### Releasing

HACS offers GitHub releases as versions, so a tag alone is not enough. Set the new version in `custom_components/loomy/manifest.json`, commit, tag the commit with that same version and push the tag to GitHub. Once the CI workflow passes on the tag it creates the release.

The sensor tests compare every entity against `tests/snapshots`. After an intended change to the sensors, regenerate the snapshot with `pytest --snapshot-update` and review the diff.
