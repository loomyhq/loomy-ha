"""Test the P1 telegram parser."""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.loomy.p1 import (
    GAS_METER,
    WATER_METER,
    P1ParseError,
    crc16,
    parse_telegram,
    parse_value,
)

from . import load_telegram

CET = timezone(timedelta(hours=1))
CEST = timezone(timedelta(hours=2))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("000123.456*kWh", 123.456),
        ("00.500*kW", 0.5),
        ("230.0*V", 230.0),
        ("240115143000W", datetime(2024, 1, 15, 14, 30, tzinfo=CET)),
        ("240715143000S", datetime(2024, 7, 15, 14, 30, tzinfo=CEST)),
        ("000000000000W", None),
        ("0001", "0001"),
        ("3153414733313030303033313831", "3153414733313030303033313831"),
        ("", ""),
    ],
)
def test_parse_value(raw: str, expected: object) -> None:
    """Test measurements become floats, timestamps datetimes, the rest text."""
    assert parse_value(raw) == expected


def test_crc16() -> None:
    """Test the CRC against the check value of CRC-16/ARC."""
    assert crc16(b"123456789") == 0xBB3D


def test_parse_telegram() -> None:
    """Test the objects of a telegram are parsed and can be looked up."""
    telegram = parse_telegram(load_telegram("telegram"))

    assert telegram.header == "FLU5\\253770234_A"
    assert telegram.get("1-0:1.8.1") == 123.456
    # The last value of an object is the measurement, after its capture time.
    assert telegram.objects["1-0:1.6.0"] == [
        datetime(2024, 1, 12, 18, 15, tzinfo=CET),
        3.456,
    ]
    assert telegram.get("1-0:1.6.0") == 3.456
    assert telegram.get("9-9:9.9.9") is None
    assert telegram.mbus_channel(GAS_METER) == 1
    assert telegram.mbus_channel(WATER_METER) == 2
    assert telegram.mbus_channel("999") is None


def test_crc_is_validated() -> None:
    """Test a telegram with a CRC is accepted when it matches, rejected otherwise."""
    body = "/FLU5\\253770234_A\r\n\r\n1-0:1.8.1(000123.456*kWh)\r\n!"

    telegram = parse_telegram(f"{body}{crc16(body.encode()):04X}\r\n")
    assert telegram.get("1-0:1.8.1") == 123.456

    with pytest.raises(P1ParseError, match="CRC mismatch"):
        parse_telegram(f"{body}0000\r\n")


def test_no_telegram() -> None:
    """Test anything without a start and end marker is rejected."""
    with pytest.raises(P1ParseError, match="No telegram found"):
        parse_telegram("Not a telegram")
