from __future__ import annotations

from dataclasses import dataclass, field
from textual.timer import Timer
from typing import Optional
#import xml.etree.ElementTree as ET
from utils.xml import int_attr, bool_attr, attr, text_list, bool_text, float_attr, \
        text, text_or_none, bool_or_none, NS
from lxml import etree

#NS = {
#    "s": "http://www.w3.org/2003/05/soap-envelope",
#    "tptz": "http://www.onvif.org/ver20/ptz/wsdl",
#    "tt": "http://www.onvif.org/ver10/schema",
#}

@dataclass
class DurationRange:
    min: Optional[str] = None
    max: Optional[str] = None

@dataclass
class PresetTourOptionsTourSpot:
    preset_tokens: list[str] = field(default_factory=list)
    stay_time: DurationRange = field(default_factory=DurationRange)

@dataclass
class PresetTourOptions:
    auto_start: Optional[bool] = None
    starting_condition: Optional[str] = None
    tour_spot: PresetTourOptionsTourSpot = field(default_factory=PresetTourOptionsTourSpot)

@dataclass
class PresetTourStatus:
    state: Optional[str] = None

@dataclass
class TourSpot:
    preset_token: Optional[str] = None
    stay_time: Optional[str] = None

@dataclass
class PresetTour:
    token: Optional[str] = None
    name: Optional[str] = None
    status: PresetTourStatus = field(default_factory=PresetTourStatus)
    auto_start: Optional[bool] = None
    spots: list[TourSpot] = field(default_factory=list)

@dataclass
class Vector2D:
    x: Optional[float] = None
    y: Optional[float] = None
    space: Optional[str] = None

@dataclass
class Vector1D:
    x: Optional[float] = None
    space: Optional[str] = None

@dataclass
class PTZPosition:
    pan_tilt: Optional[Vector2D] = None
    zoom: Optional[Vector1D] = None

@dataclass
class PTZPreset:
    token: Optional[str] = None
    name: Optional[str] = None
    ptz_position: Optional[PTZPosition] = None

def parse_ptz_position(elem: Optional[etree._Element]) -> Optional[PTZPosition]:
    if elem is None:
        return None

    pan_tilt = elem.find("tt:PanTilt", NS)
    zoom = elem.find("tt:Zoom", NS)

    return PTZPosition(
        pan_tilt=Vector2D(
            x=float_attr(pan_tilt, "x"),
            y=float_attr(pan_tilt, "y"),
            space=attr(pan_tilt, "space"),
        ) if pan_tilt is not None else None,
        zoom=Vector1D(
            x=float_attr(zoom, "x"),
            space=attr(zoom, "space"),
        ) if zoom is not None else None,
    )

def parse_preset_element(elem: etree._Element) -> PTZPreset:
    return PTZPreset(
        token=attr(elem, "token"),
        name=text(elem, "tt:Name"),
        ptz_position=parse_ptz_position(elem.find("tt:PTZPosition", NS)),
    )

def parse_get_presets_response(xml: str) -> list[PTZPreset]:
    if not xml: return
    root = etree.fromstring(xml.encode('utf-8'))
    preset_elems = root.findall(".//tptz:GetPresetsResponse/tptz:Preset", NS)
    return [parse_preset_element(preset) for preset in preset_elems]

def parse_get_preset_tours_response(xml: str | bytes) -> list[PresetTour]:
    if not xml: return
    root = etree.fromstring(xml.encode('utf-8'))

    tours: list[PresetTour] = []

    for tour_el in root.xpath(".//tptz:GetPresetToursResponse/tptz:PresetTour", namespaces=NS):
        spots: list[TourSpot] = []

        for spot_el in tour_el.xpath("./tt:TourSpot", namespaces=NS):
            spot = TourSpot(
                preset_token=text_or_none(spot_el, "./tt:PresetDetail/tt:PresetToken"),
                stay_time=text_or_none(spot_el, "./tt:StayTime"),
            )
            spots.append(spot)

        tour = PresetTour(
            token=tour_el.get("token"),
            name=text_or_none(tour_el, "./tt:Name"),
            status=PresetTourStatus(
                state=text_or_none(tour_el, "./tt:Status/tt:State")
            ),
            auto_start=bool_or_none(text_or_none(tour_el, "./tt:AutoStart")),
            spots=spots,
        )

        tours.append(tour)

    return tours

def parse_get_preset_tour_options_response(xml: str | bytes) -> PresetTourOptions:
    if not xml: return
    root = etree.fromstring(xml.encode('utf-8'))

    options_el = root.xpath(
        ".//tptz:GetPresetTourOptionsResponse/tptz:Options",
        namespaces=NS,
    )

    response_el = root.xpath(
        ".//tptz:GetPresetTourOptionsResponse",
        namespaces=NS,
    )

    options = PresetTourOptions()

    if options_el:
        options.auto_start = bool_or_none(
            text_or_none(options_el[0], "./tt:AutoStart")
        )
        options.starting_condition = text_or_none(
            options_el[0], "./tt:StartingCondition"
        )

    if response_el:
        spot_el = response_el[0].xpath("./tt:TourSpot", namespaces=NS)

        if spot_el:
            spot = spot_el[0]

            preset_tokens = [
                el.text.strip()
                for el in spot.xpath(
                    "./tt:PresetDetail/tt:PresetToken",
                    namespaces=NS,
                )
                if el.text
            ]

            options.tour_spot = PresetTourOptionsTourSpot(
                preset_tokens=preset_tokens,
                stay_time=DurationRange(
                    min=text_or_none(spot, "./tt:StayTime/tt:Min"),
                    max=text_or_none(spot, "./tt:StayTime/tt:Max"),
                ),
            )

    return options


