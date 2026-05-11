from typing import Any, get_args, get_origin, Union
import types

EDITABLE_FIELDS = ["network_gateway", "hostname.from_dhcp", "hostname.name"]

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

def convert_string_value(value: str, field_type: Any) -> Any:
    field_type = unwrap_optional(field_type)

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

    # fallback: leave as string
    return value

def resolve_fqn_owner(root: object, fqn: str) -> tuple[object, str, type | None]:
    parts = fqn.split(".")
    owner = root
    for part in parts[:-1]:
        owner = getattr(owner, part)
    field_name = parts[-1]
    field_type = None
    if hasattr(owner, "__dataclass_fields__"):
        field_info = owner.__dataclass_fields__.get(field_name)
        if field_info:
            field_type = field_info.type
    return owner, field_name, field_type


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
"""

}