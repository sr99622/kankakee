from __future__ import annotations

from dataclasses import dataclass, field
from textual.timer import Timer
from typing import Optional
import xml.etree.ElementTree as ET
from utils.xml import int_attr, bool_attr, attr, text_list, bool_text, float_attr, text, NS

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

def parse_ptz_position(elem: Optional[ET.Element]) -> Optional[PTZPosition]:
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

def parse_preset_element(elem: ET.Element) -> PTZPreset:
    return PTZPreset(
        token=attr(elem, "token"),
        name=text(elem, "tt:Name"),
        ptz_position=parse_ptz_position(elem.find("tt:PTZPosition", NS)),
    )

def parse_get_presets_response(xml: str) -> list[PTZPreset]:
    root = ET.fromstring(xml)
    preset_elems = root.findall(".//tptz:GetPresetsResponse/tptz:Preset", NS)
    return [parse_preset_element(preset) for preset in preset_elems]


