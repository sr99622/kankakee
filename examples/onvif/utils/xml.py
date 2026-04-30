from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import xml.etree.ElementTree as ET
from lxml import etree

NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "timg": "http://www.onvif.org/ver20/imaging/wsdl",
    "wsa5": "http://www.w3.org/2005/08/addressing",
    "wsnt": "http://docs.oasis-open.org/wsn/b-2",
    "d": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "ter": "http://www.onvif.org/ver10/error",
    "a": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
    "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "wsu": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
}

def text(elem: ET.Element, path: str) -> Optional[str]:
    found = elem.find(path, NS)
    return found.text.strip() if found is not None and found.text else None

def bool_text(elem: ET.Element, path: str) -> Optional[bool]:
    value = text(elem, path)
    if value is None:
        return None
    return value.lower() == "true"

def int_text(elem: ET.Element, path: str) -> Optional[int]:
    value = text(elem, path)
    return int(value) if value is not None else None

def float_text(elem: ET.Element, path: str) -> Optional[float]:
    value = text(elem, path)
    return float(value) if value is not None else None

def attr(elem: ET.Element, name: str) -> Optional[str]:
    return elem.attrib.get(name)

def bool_attr(elem: ET.Element, name: str) -> Optional[bool]:
    value = attr(elem, name)
    if value is None:
        return None
    return value.lower() == "true"

def get_xml_value(xml_data, xpath):
    try:
        if isinstance(xml_data, str):
            xml_data = xml_data.encode("utf-8")
        doc = etree.fromstring(xml_data)
    except (etree.XMLSyntaxError, ValueError):
        return ""

    try:
        result = doc.xpath(xpath, namespaces=NS)
    except etree.XPathError:
        return ""

    if not result:
        return ""

    node = result[0]
    if isinstance(node, etree._Element):
        return "".join(node.itertext()).strip()

    return str(node).strip()
