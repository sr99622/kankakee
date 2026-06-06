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
    "profiles.[*].audio_encoder.encoding",
    "profiles.[*].audio_encoder.bitrate",
    "profiles.[*].audio_encoder.sample_rate",
    "profiles.[*].audio_encoder.session_timeout",
    "profiles.[*].audio_encoder.multicast.port",
    "profiles.[*].audio_encoder.multicast.ttl",
    "profiles.[*].audio_encoder.multicast.ip_address",
    "profiles.[*].video_encoder.session_timeout",
    "profiles.[*].video_encoder.encoding",
    "profiles.[*].video_encoder.profile",
    "profiles.[*].video_encoder.gov_length",
    "profiles.[*].video_encoder.quality",
    "profiles.[*].video_encoder.multicast.port",
    "profiles.[*].video_encoder.multicast.ttl",
    "profiles.[*].video_encoder.multicast.ip_address",
    "profiles.[*].video_encoder.rate_control.frame_rate_limit",
    "profiles.[*].video_encoder.rate_control.encoding_interval",
    "profiles.[*].video_encoder.rate_control.bitrate_limit",
    "capabilities.ptz.presets.[*].name",
    "capabilities.ptz.tours.[*].spots.[*].stay_time",
    "capabilities.ptz.tours.[*].spots.[*].preset_token",
    "capabilities.device_io.relay_outputs.[*].properties.mode",
    "capabilities.device_io.relay_outputs.[*].properties.delay_time",
    "capabilities.device_io.relay_outputs.[*].properties.idle_state",
]

UNUSED_FIELDS = [
    "audio_decoder", 
    "audio_decoder_options", 
    "audio_outputs",
    "capabilities.events.service_capabilities.persistent_notification_storage",
    "capabilities.events.service_capabilities.event_broker_protocols",
    "capabilities.events.service_capabilities.max_event_brokers",
    "capabilities.events.service_capabilities.metadata_over_mqtt",
    "capabilities.events.event_properties.fixed_topic_set",
    "capabilities.events.event_properties.producer_properties_filter_dialect",
    "capabilities.events.event_properties.topic_expression_dialect",
    "capabilities.telex",
]

HIDDEN_FIELDS = [
    "subscription_references",
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


def resolve_fqn_owner(root: object, fqn: str) -> tuple[object, str, Any, list[int]]:
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

ptz_screen = \
"""
PPPp   TTTTTTT  ZZZZZZ
P   p     T         Z  
P   p     T        Z
PPP       T       Z
P         T      Z
P         T     ZZZZZZ

Control camera position using the commands

i - info
w - up
s - down
a - left
d - right
z - zoom in
x - zoom out
c - stop
"""

ptz_presets = \
"""

"""

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
""",

    "capabilities.ptz.xaddr":
ptz_screen,

    "capabilities.ptz.presets":
"""
Presets are used to assign camera position
to a field. Add a new preset at the current
position by typing the 'n' key.

Open the branch to see the presets. Actions
can be taken on the presets individually
when the preset is highlighted.
""",

    "capabilities.ptz.presets.[*]":
"""

The preset can modified from this screen.
Position the camera at the desired settings
then use the 's' key to set.

g - goto preset position
s - set preset to current position
d - delete
""",

    "capabilities.ptz.presets.[*].token":
"""
The token is a read only field assigned by
the camera to identify the preset.
""",
    "capabilities.ptz.presets.[*].name":
"""
The name is a user-editable field that can
be used to identify the preset.
""",
    "capabilities.ptz.presets.[*].ptz_position":
"""
The ptz_position field is designed to be a 
read only field to hold the coordinates for the 
position, but is rarely used in practice.
""",

    "capabilities.ptz.tours":
"""
Tours are a sequence of preset gotos. Build
a tour by adding spots which are a preset and 
a stay time.

Add a new tour using the 'n' key. Actions can 
be taken on individual tours by opening the 
tours branch and highlighting the tour.
""",

    "capabilities.ptz.tours.[*]":
"""
Tours are built by adding spots to the tour.
Navigate to the spots branch to add spots. 
Spots are edited individually once they have 
been added.

Please consult the tour_options branch to 
find allowed settings for tours.

s - start tour 
t - stop tour 
d - delete tour
w - write tour to camera (after spot edit) 
""",

    "capabilities.ptz.tours.[*].spots":
"""
Add spots to the tour using the 'n' key.
Once the spots have been added, open the 
branch and navigate to the spot to edit 
the preset and stay_time.

The tour main branch will show modified.
From there, use the 'w' key to write the 
spots data to the camera.
""",

    "capabilities.ptz.tours.[*].spots.[*]":
"""
Open the spot leaves to edit the preset and
stay_time. Consult the tour_options branch
to view allowed entries.

To delete a spot, use the 'd' key.
""",

    "capabilities.ptz.tours.[*].spots.[*].preset_token":
"""
Use the F2 key to activate the editor and 
type in a preset token.


Allowed values are shown in the tour_options 
branch. After editing, the tour will show 
as (* modified). Use the 'w' from the tour 
main branch to write the tour to the camera.
""",

    "capabilities.ptz.tours.[*].spots.[*].stay_time":
"""
Use the F2 key to activate the editor and 
type in a stay time.


Allowed values are shown in the tour_options 
branch. After editing, the tour will show 
as (* modified). Use the 'w' from the tour 
main branch to write the tour to the camera.
"""
}
