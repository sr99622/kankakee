from __future__ import annotations

from typing import Optional

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
    "tptz": "http://www.onvif.org/ver20/ptz/wsdl",
    "tev": "http://www.onvif.org/ver10/events/wsdl",
    "wstop": "http://docs.oasis-open.org/wsn/t-1",
    "wsa": "http://www.w3.org/2005/08/addressing",
    "tns1": "http://www.onvif.org/ver10/topics",
}


Element = etree._Element


def parse_xml(xml_data: str | bytes) -> Optional[Element]:
    """Parse XML using lxml.

    Returns None on parse failure.
    Leading/trailing whitespace is stripped so XML declarations work
    even when the XML string is triple-quoted with a leading newline.
    """
    try:
        if isinstance(xml_data, str):
            xml_data = xml_data.strip().encode("utf-8")
        else:
            xml_data = xml_data.strip()

        return etree.fromstring(xml_data)
    except (etree.XMLSyntaxError, ValueError):
        return None


def xpath_one(elem: Element, path: str) -> Optional[object]:
    try:
        result = elem.xpath(path, namespaces=NS)
    except etree.XPathError:
        return None

    return result[0] if result else None


def xpath_all(elem: Element, path: str) -> list[object]:
    try:
        return elem.xpath(path, namespaces=NS)
    except etree.XPathError:
        return []


def text(elem: Element, path: str) -> Optional[str]:
    found = xpath_one(elem, path)

    if found is None:
        return None

    if isinstance(found, etree._Element):
        value = "".join(found.itertext()).strip()
        return value if value else None

    value = str(found).strip()
    return value if value else None


def bool_text(elem: Element, path: str) -> Optional[bool]:
    value = text(elem, path)
    if value is None:
        return None

    return value.strip().lower() in ("true", "1", "yes", "on")


def text_list(elem: Element, path: str) -> list[str]:
    values: list[str] = []

    for item in xpath_all(elem, path):
        if isinstance(item, etree._Element):
            value = "".join(item.itertext()).strip()
        else:
            value = str(item).strip()

        if value:
            values.append(value)

    return values


def text_or_none(parent: Element, xpath: str) -> Optional[str]:
    return text(parent, xpath)


def bool_or_none(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None

    return value.strip().lower() == "true"


def int_text(elem: Element, path: str) -> Optional[int]:
    value = text(elem, path)
    return int(value) if value is not None else None


def float_text(elem: Element, path: str) -> Optional[float]:
    value = text(elem, path)
    return float(value) if value is not None else None


def attr(elem: Optional[Element], name: str) -> Optional[str]:
    if elem is None:
        return None

    return elem.attrib.get(name)


def bool_attr(elem: Optional[Element], name: str) -> Optional[bool]:
    value = attr(elem, name)
    if value is None:
        return None

    return value.lower() == "true"


def int_attr(elem: Optional[Element], name: str) -> Optional[int]:
    value = attr(elem, name)
    if value is None:
        return None

    return int(value)


def float_attr(elem: Optional[Element], name: str) -> Optional[float]:
    value = attr(elem, name)
    if value is None:
        return None

    return float(value)


def get_xml_value(xml_data: str | bytes, xpath: str) -> str:
    doc = parse_xml(xml_data)
    if doc is None:
        return ""

    found = xpath_one(doc, xpath)
    if found is None:
        return ""

    if isinstance(found, etree._Element):
        return "".join(found.itertext()).strip()

    return str(found).strip()
