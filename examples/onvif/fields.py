from typing import Any, get_args, get_origin, Union, List, get_type_hints
import types
import re

_INDEX_RE = re.compile(r"^\[(\d+)\]$")

EDITABLE_FIELDS = [
    "network_gateway", 
    "hostname.from_dhcp", 
    "hostname.name",
    "dns.from_dhcp", 
    "dns.dns_manual",
    "ntp.from_dhcp",
    "ntp.ntp_manual",
    "network_interfaces.[*].ipv4.dhcp",
    "network_interfaces.[*].ipv4.manual",
    "profiles.[*].imaging_settings.brightness",
    "profiles.[*].imaging_settings.color_saturation",
    "profiles.[*].imaging_settings.contrast",
    "profiles.[*].imaging_settings.sharpness",
    "profiles.[*].imaging_settings.ir_cut_filter",
]

def normalize_fqn(fqn: str) -> str:
    return re.sub(r"\[\d+\]", "[*]", fqn)

def is_editable_field(fqn: str) -> bool:
    return normalize_fqn(fqn) in EDITABLE_FIELDS

def join_fqn(parent_fqn: str | None, field_name: str) -> str:
    if parent_fqn:
        return f"{parent_fqn}.{field_name}"
    return field_name

def unwrap_optional(field_type: Any) -> Any:
    origin = get_origin(field_type)

    if origin is Union or origin is types.UnionType:
        args = [arg for arg in get_args(field_type) if arg is not type(None)]
        if len(args) == 1:
            return args[0]

    return field_type

def parse_ip_string_list(text: str) -> list[str]:
    text = text.strip()

    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]

    result: list[str] = []

    for raw in text.split(","):
        item = raw.strip()
        item = item.strip('"').strip("'").strip()

        if not item:
            continue

        #try:
        #    ip = ipaddress.ip_address(item)
        #except ValueError:
        #    raise ValueError(f"Invalid IP address: {item}")

        #result.append(str(ip))
        result.append(item)

    return result

def convert_string_value(value: str, field_type: Any) -> Any:
    field_type = unwrap_optional(field_type)

    origin = get_origin(field_type)
    args = get_args(field_type)

    # --- list[str] handling ---
    if origin is list:
        item_type = args[0] if args else str

        if item_type is str:
            return parse_ip_string_list(value)

        # generic fallback for other list types
        return [
            convert_string_value(item.strip(), item_type)
            for item in value.split(",")
            if item.strip()
        ]

    # --- scalar handling ---
    if field_type is str:
        return value

    if field_type is int:
        return int(value)

    if field_type is float:
        return float(value)

    if field_type is bool:
        value = value.strip().lower()

        if value in {"true", "1", "yes", "y", "on"}:
            return True

        if value in {"false", "0", "no", "n", "off"}:
            return False

        raise ValueError(f"Invalid bool value: {value}")

    # fallback
    return value


def resolve_fqn_owner(
    root: object,
    fqn: str,
) -> tuple[object, str, Any, list[int]]:

    parts = fqn.split(".")
    owner = root

    indices: list[int] = []

    for part in parts[:-1]:
        match = _INDEX_RE.match(part)

        if match:
            index = int(match.group(1))
            indices.append(index)
            owner = owner[index]
        else:
            owner = getattr(owner, part)

    field_name = parts[-1]

    type_hints = get_type_hints(type(owner))
    field_type = type_hints.get(field_name)

    return owner, field_name, field_type, indices

'''
def resolve_fqn_owner(root: object, fqn: str) -> tuple[object, str, Any]:
    parts = fqn.split(".")
    owner = root

    for part in parts[:-1]:
        match = _INDEX_RE.match(part)

        if match:
            index = int(match.group(1))
            owner = owner[index]
        else:
            owner = getattr(owner, part)

    field_name = parts[-1]

    type_hints = get_type_hints(type(owner))
    field_type = type_hints.get(field_name)

    return owner, field_name, field_type
'''

'''
def resolve_fqn_owner(root: object, fqn: str) -> tuple[object, str, Any]:
    parts = fqn.split(".")
    owner = root

    for part in parts[:-1]:
        owner = getattr(owner, part)

    field_name = parts[-1]

    type_hints = get_type_hints(type(owner))
    field_type = type_hints.get(field_name)

    return owner, field_name, field_type
'''

def analyze_field_type(field_type: Any) -> tuple[Any, bool, bool]:
    is_optional = False

    origin = get_origin(field_type)
    args = get_args(field_type)

    # Optional[T] / T | None
    if origin in (Union, types.UnionType):
        non_none = [arg for arg in args if arg is not type(None)]

        if len(non_none) == 1:
            is_optional = True
            field_type = non_none[0]
            origin = get_origin(field_type)
            args = get_args(field_type)

    # list[T] or typing.List[T]
    if origin is list:
        item_type = args[0] if args else Any
        return item_type, is_optional, True

    if field_type is list:
        return Any, is_optional, True

    return field_type, is_optional, False

field_descriptions = {
    "network_gateway": 
"""
This value sets the access point for the camera
to reach other networks, including the internet.

This can be set by DHCP or manually. The value
of the field must be a valid ip address on the
local subnet.

""",

    "hostname":
"""
A value that may be assigned by DHCP or set 
manually that identifies the camera on the
network.

Depending on settings, the name may be set 
by DHCP or manually.

""",

    "hostname.from_dhcp":
"""
This operation controls whether the hostname
is set manually or retrieved via DHCP.
""",

    "hostname.name":
"""
This operation sets the hostname on a device.
It shall be possible to set the device hostname 
configurations through the SetHostname command.

A device shall accept string formated according
to RFC 1123 section 2.1 or alternatively to 
RFC 952, other string shall be considered as 
invalid strings.
""",

    "dns":
"""
A value that may be assigned by DHCP or set
manually that specifies the Domain Name
Server to be used by the camera
""",

    "dns.from_dhcp":
"""
Indicate if the DNS address is to be set 
automatically using DHCP. If this value is
set to False, there should be at least one
value set in the dns_manual list to identify 
DNS servers
"""

}