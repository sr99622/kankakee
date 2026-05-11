EDITABLE_FIELDS = ["network_gateway", "hostname.from_dhcp", "hostname.name"]


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