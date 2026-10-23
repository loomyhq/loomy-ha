"""Parser for P1 telegrams as specified in eMUCS-P1 (based on DSMR P1)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

type P1Value = float | datetime | str | None

# Reduced OBIS identifier (A-B:C.D.E) followed by one or more (value) groups.
_OBJECT_RE = re.compile(r"^(\d+-\d+:\d+\.\d+\.\d+)((?:\([^()]*\))+)$")
_GROUP_RE = re.compile(r"\(([^()]*)\)")
_MEASUREMENT_RE = re.compile(r"^(\d+(?:\.\d+)?)\*\w+$")
_TIMESTAMP_RE = re.compile(r"^\d{12}[SW]$")

# The meter clock runs on Belgian time: S = summer (CEST), W = winter (CET).
_TIMEZONES = {
    "S": timezone(timedelta(hours=2)),
    "W": timezone(timedelta(hours=1)),
}

MBUS_DEVICE_TYPE_GAS = "003"
MBUS_DEVICE_TYPE_WATER = "007"


class P1ParseError(ValueError):
    """Raised when a telegram cannot be parsed."""


@dataclass
class P1Telegram:
    """A parsed P1 telegram."""

    header: str
    objects: dict[str, list[P1Value]]

    def get(self, obis: str, index: int = -1) -> P1Value:
        """Return a value of an object, or None if it is not in the telegram.

        Defaults to the last value, which is the measurement for objects that
        carry a capture time first, like 0-1:24.2.3(<timestamp>)(<value>).
        """
        values = self.objects.get(obis)
        if not values:
            return None
        return values[index]

    def mbus_channel(self, device_type: str) -> int | None:
        """Return the M-Bus channel a submeter of the given type is on."""
        for channel in range(1, 9):
            if self.get(f"0-{channel}:24.1.0") == device_type:
                return channel
        return None


def crc16(data: bytes) -> int:
    """Compute the CRC16 (polynomial x16+x15+x2+1, LSB first) of a telegram."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def parse_value(raw: str) -> P1Value:
    """Parse a single value from between the parentheses.

    Measurements (123.456*kWh) become floats without their unit, timestamps
    (YYMMDDhhmmssX) become aware datetimes, or None when they are invalid.
    Anything else, like identifiers, hex strings and enum values, is returned
    as is.
    """
    if match := _MEASUREMENT_RE.match(raw):
        return float(match.group(1))
    if _TIMESTAMP_RE.match(raw):
        try:
            return datetime.strptime(raw[:12], "%y%m%d%H%M%S").replace(
                tzinfo=_TIMEZONES[raw[12]]
            )
        except ValueError:
            # Meters are known to publish garbage timestamps, like 000000000000W.
            return None
    return raw


def parse_telegram(raw: str) -> P1Telegram:
    """Parse a P1 telegram, validating its CRC when present."""
    start = raw.find("/")
    end = raw.find("!", start)
    if start == -1 or end == -1:
        raise P1ParseError("No telegram found")

    if crc := raw[end + 1 : end + 5].strip():
        expected = crc16(raw[start : end + 1].encode())
        if crc.upper() != f"{expected:04X}":
            raise P1ParseError(f"CRC mismatch: got {crc}, expected {expected:04X}")

    header, *lines = raw[start + 1 : end].splitlines()
    objects: dict[str, list[P1Value]] = {}
    for line in lines:
        # Skip blank lines and anything that is not a data object.
        if match := _OBJECT_RE.match(line.strip()):
            objects[match.group(1)] = [
                parse_value(value) for value in _GROUP_RE.findall(match.group(2))
            ]

    return P1Telegram(header=header.strip(), objects=objects)
