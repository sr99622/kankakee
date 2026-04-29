from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import xml.etree.ElementTree as ET
from utils.xml import text, int_text, bool_text, attr, NS

@dataclass
class PrefixedIPv4Address:
    address: Optional[str] = None
    prefix_length: Optional[int] = None

@dataclass
class PrefixedIPv6Address:
    address: Optional[str] = None
    prefix_length: Optional[int] = None

@dataclass
class NetworkInterfaceInfo:
    name: Optional[str] = None
    hw_address: Optional[str] = None
    mtu: Optional[int] = None

@dataclass
class NetworkInterfaceConnectionSetting:
    auto_negotiation: Optional[bool] = None
    speed: Optional[int] = None
    duplex: Optional[str] = None

@dataclass
class NetworkInterfaceLink:
    admin_settings: NetworkInterfaceConnectionSetting = field(
        default_factory=NetworkInterfaceConnectionSetting
    )
    oper_settings: NetworkInterfaceConnectionSetting = field(
        default_factory=NetworkInterfaceConnectionSetting
    )
    interface_type: Optional[int] = None

@dataclass
class IPv4NetworkInterface:
    enabled: Optional[bool] = None
    manual: list[PrefixedIPv4Address] = field(default_factory=list)
    link_local: Optional[PrefixedIPv4Address] = None
    from_dhcp: Optional[PrefixedIPv4Address] = None
    dhcp: Optional[bool] = None

@dataclass
class IPv6NetworkInterface:
    enabled: Optional[bool] = None
    accept_router_advert: Optional[bool] = None
    manual: list[PrefixedIPv6Address] = field(default_factory=list)
    link_local: list[PrefixedIPv6Address] = field(default_factory=list)
    from_dhcp: list[PrefixedIPv6Address] = field(default_factory=list)
    from_ra: list[PrefixedIPv6Address] = field(default_factory=list)
    dhcp: Optional[str] = None

@dataclass
class NetworkInterface:
    token: Optional[str] = None
    enabled: Optional[bool] = None
    info: NetworkInterfaceInfo = field(default_factory=NetworkInterfaceInfo)
    link: NetworkInterfaceLink = field(default_factory=NetworkInterfaceLink)
    ipv4: Optional[IPv4NetworkInterface] = None
    ipv6: Optional[IPv6NetworkInterface] = None

'''
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
'''

def parse_prefixed_ipv4(elem: Optional[ET.Element]) -> Optional[PrefixedIPv4Address]:
    if elem is None:
        return None

    return PrefixedIPv4Address(
        address=text(elem, "tt:Address"),
        prefix_length=int_text(elem, "tt:PrefixLength"),
    )

def parse_prefixed_ipv6(elem: Optional[ET.Element]) -> Optional[PrefixedIPv6Address]:
    if elem is None:
        return None

    return PrefixedIPv6Address(
        address=text(elem, "tt:Address"),
        prefix_length=int_text(elem, "tt:PrefixLength"),
    )

def parse_connection_setting(elem: Optional[ET.Element]) -> NetworkInterfaceConnectionSetting:
    if elem is None:
        return NetworkInterfaceConnectionSetting()

    return NetworkInterfaceConnectionSetting(
        auto_negotiation=bool_text(elem, "tt:AutoNegotiation"),
        speed=int_text(elem, "tt:Speed"),
        duplex=text(elem, "tt:Duplex"),
    )

def parse_network_interface_link(elem: Optional[ET.Element]) -> NetworkInterfaceLink:
    if elem is None:
        return NetworkInterfaceLink()

    return NetworkInterfaceLink(
        admin_settings=parse_connection_setting(
            elem.find("tt:AdminSettings", NS)
        ),
        oper_settings=parse_connection_setting(
            elem.find("tt:OperSettings", NS)
        ),
        interface_type=int_text(elem, "tt:InterfaceType"),
    )

def parse_ipv4_network_interface(elem: Optional[ET.Element]) -> Optional[IPv4NetworkInterface]:
    if elem is None:
        return None

    return IPv4NetworkInterface(
        enabled=bool_text(elem, "tt:Enabled"),
        manual=[
            addr
            for addr in (
                parse_prefixed_ipv4(e)
                for e in elem.findall("tt:Config/tt:Manual", NS)
            )
            if addr is not None
        ],
        link_local=parse_prefixed_ipv4(elem.find("tt:Config/tt:LinkLocal", NS)),
        from_dhcp=parse_prefixed_ipv4(elem.find("tt:Config/tt:FromDHCP", NS)),
        dhcp=bool_text(elem, "tt:Config/tt:DHCP"),
    )

def parse_ipv6_network_interface(elem: Optional[ET.Element]) -> Optional[IPv6NetworkInterface]:
    if elem is None:
        return None

    return IPv6NetworkInterface(
        enabled=bool_text(elem, "tt:Enabled"),
        accept_router_advert=bool_text(elem, "tt:Config/tt:AcceptRouterAdvert"),
        manual=[
            addr
            for addr in (
                parse_prefixed_ipv6(e)
                for e in elem.findall("tt:Config/tt:Manual", NS)
            )
            if addr is not None
        ],
        link_local=[
            addr
            for addr in (
                parse_prefixed_ipv6(e)
                for e in elem.findall("tt:Config/tt:LinkLocal", NS)
            )
            if addr is not None
        ],
        from_dhcp=[
            addr
            for addr in (
                parse_prefixed_ipv6(e)
                for e in elem.findall("tt:Config/tt:FromDHCP", NS)
            )
            if addr is not None
        ],
        from_ra=[
            addr
            for addr in (
                parse_prefixed_ipv6(e)
                for e in elem.findall("tt:Config/tt:FromRA", NS)
            )
            if addr is not None
        ],
        dhcp=text(elem, "tt:Config/tt:DHCP"),
    )

def parse_network_interfaces_response(xml: str) -> list[NetworkInterface]:
    root = ET.fromstring(xml)

    interface_elems = root.findall(
        ".//tds:GetNetworkInterfacesResponse/tds:NetworkInterfaces",
        NS,
    )
    if not interface_elems:
        raise ValueError(
            "Could not find tds:GetNetworkInterfacesResponse/tds:NetworkInterfaces"
        )

    interfaces: list[NetworkInterface] = []

    for elem in interface_elems:
        interfaces.append(
            NetworkInterface(
                token=attr(elem, "token"),
                enabled=bool_text(elem, "tt:Enabled"),
                info=NetworkInterfaceInfo(
                    name=text(elem, "tt:Info/tt:Name"),
                    hw_address=text(elem, "tt:Info/tt:HwAddress"),
                    mtu=int_text(elem, "tt:Info/tt:MTU"),
                ),
                link=parse_network_interface_link(elem.find("tt:Link", NS)),
                ipv4=parse_ipv4_network_interface(elem.find("tt:IPv4", NS)),
                ipv6=parse_ipv6_network_interface(elem.find("tt:IPv6", NS)),
            )
        )

    return interfaces