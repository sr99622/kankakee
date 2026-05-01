from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import xml.etree.ElementTree as ET
from utils.xml import text, int_text, bool_text, attr, bool_attr, float_text, NS

@dataclass
class Time:
    hour: Optional[int] = None
    minute: Optional[int] = None
    second: Optional[int] = None

@dataclass
class Date:
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None

@dataclass
class DateTime:
    time: Time = field(default_factory=Time)
    date: Date = field(default_factory=Date)

@dataclass
class TimeZone:
    tz: Optional[str] = None

@dataclass
class SystemDateAndTime:
    date_time_type: Optional[str] = None
    daylight_savings: Optional[bool] = None
    time_zone: Optional[TimeZone] = None
    utc_date_time: Optional[DateTime] = None
    local_date_time: Optional[DateTime] = None

def parse_time(elem: Optional[ET.Element]) -> Time:
    if elem is None:
        return Time()

    return Time(
        hour=int_text(elem, "tt:Hour"),
        minute=int_text(elem, "tt:Minute"),
        second=int_text(elem, "tt:Second"),
    )

def parse_date(elem: Optional[ET.Element]) -> Date:
    if elem is None:
        return Date()

    return Date(
        year=int_text(elem, "tt:Year"),
        month=int_text(elem, "tt:Month"),
        day=int_text(elem, "tt:Day"),
    )


def parse_datetime(elem: Optional[ET.Element]) -> Optional[DateTime]:
    if elem is None:
        return None

    return DateTime(
        time=parse_time(elem.find("tt:Time", NS)),
        date=parse_date(elem.find("tt:Date", NS)),
    )


def parse_timezone(elem: Optional[ET.Element]) -> Optional[TimeZone]:
    if elem is None:
        return None

    return TimeZone(
        tz=text(elem, "tt:TZ"),
    )

def parse_system_date_and_time_response(xml: str) -> SystemDateAndTime:
    root = ET.fromstring(xml)

    elem = root.find(
        ".//tds:GetSystemDateAndTimeResponse/tds:SystemDateAndTime",
        NS,
    )
    if elem is None:
        raise ValueError(
            "Could not find tds:GetSystemDateAndTimeResponse/tds:SystemDateAndTime"
        )

    return SystemDateAndTime(
        date_time_type=text(elem, "tt:DateTimeType"),
        daylight_savings=bool_text(elem, "tt:DaylightSavings"),
        time_zone=parse_timezone(elem.find("tt:TimeZone", NS)),
        utc_date_time=parse_datetime(elem.find("tt:UTCDateTime", NS)),
        local_date_time=parse_datetime(elem.find("tt:LocalDateTime", NS)),
    )