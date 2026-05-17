from loguru import logger
import traceback
import niquests as requests
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional, List
from utils.xml import get_xml_value
from utils.soap import onvif_post, parse_soap_fault, POST_TIMEOUT
from functools import wraps
import xml.etree.ElementTree as ET
from utils.xml import text, NS
from urllib.parse import unquote_plus, urlparse
import uuid
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
import socket
import struct

from datastructures.capabilities import Capabilities, parse_capabilities_response
from datastructures.profiles import Profile, VideoEncoderConfiguration, AudioEncoderConfiguration, \
        AudioOutputConfiguration, AudioDecoderConfiguration, AudioDecoderConfigurationOptions, \
        parse_profiles_response, parse_video_encoder_configuration_options_response, \
        parse_audio_encoder_configuration_options_response, parse_audio_output_configurations_response, \
        parse_audio_decoder_configurations_response, parse_audio_output_configurations_response, \
        parse_audio_decoder_configuration_options_response
from datastructures.network import NetworkInterface, DNSInformation, HostnameInformation, \
        parse_network_interfaces_response, parse_dns_response, parse_hostname_response
from datastructures.imaging import ImagingSettings, ImagingOptions, \
        parse_imaging_settings_response, parse_imaging_options_response
from datastructures.datetime import Date, DateTime, SystemDateAndTime,  NTPInformation, Time, TimeZone, \
        parse_system_date_and_time_response, parse_ntp_response
from datastructures.event import ServiceCapabilities, EventProperties, \
        parse_service_capabilities_response, parse_event_properties_response

class AuthorizationError(Exception):
    pass

@dataclass
class DeviceInformation:
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    serial_number: Optional[str] = None
    hardware_id: Optional[str] = None

@dataclass
class Camera:
    xaddr: Optional[str] = None
    name: Optional[str] = None
    system_date_and_time: Optional[SystemDateAndTime] = None
    device_information: Optional[str] = None
    time_offset: Optional[int] = 0
    username: Optional[str] = None
    password: Optional[str] = None
    capabilities: Optional[Capabilities] = None
    profiles: list[Profile] = None
    network_interfaces: list[NetworkInterface] = None
    network_gateway: Optional[str] = None
    dns: Optional[DNSInformation] = None
    ntp: Optional[NTPInformation] = None
    hostname: Optional[HostnameInformation] = None
    service_capabilities: Optional[ServiceCapabilities] = None
    event_properties: Optional[EventProperties] = None
    audio_output: list[AudioOutputConfiguration] = None
    audio_decoder: Optional[AudioDecoderConfiguration] = None
    audio_decoder_options: Optional[AudioDecoderConfigurationOptions] = None

def safe_run(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            #logger.error(f"Error in {func.__name__}: {e}")
            #logger.debug(traceback.format_exc())
            return None
    return wrapper

def get_camera_name(xml_data: str) -> str:
    scopes = get_xml_value(xml_data, "//s:Body//d:ProbeMatches//d:ProbeMatch//d:Scopes")
    name_id = "onvif://www.onvif.org/name/"
    hdwr_id = "onvif://www.onvif.org/hardware/"
    name = ""
    hdwr = ""
    for field in scopes.split():
        if name_id in field:
            name = unquote_plus(field[len(name_id):])
        if hdwr_id in field:
            hdwr = unquote_plus(field[len(hdwr_id):])
    if name and hdwr:
        if hdwr not in name:
            return f"{name} {hdwr}"
        return name
    return "UNKNOWN CAMERA"

# DATE AND TIME FUNCTIONS
#
# this camera query does not require authorization, so it has a different design pattern
# it also returns the SystemDateTime object directly rather than setting it on the camera 
def get_system_date_and_time(url: str) -> SystemDateAndTime:
    soap = """<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><SOAP-ENV:Body><tds:GetSystemDateAndTime/></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=POST_TIMEOUT)
    fault = parse_soap_fault(response.text)
    if fault:
        raise ValueError(str(fault))
    response.raise_for_status()
    return parse_system_date_and_time_response(response.text)

def get_time_offset(camera: Camera) -> None:
    sdt = get_system_date_and_time(camera.xaddr)
    setattr(camera, "system_date_and_time", sdt)
    camera_utc = datetime(sdt.utc_date_time.date.year, sdt.utc_date_time.date.month, sdt.utc_date_time.date.day, 
        sdt.utc_date_time.time.hour, sdt.utc_date_time.time.minute, sdt.utc_date_time.time.second).replace(tzinfo=timezone.utc)
    computer_utc = datetime.now(timezone.utc)
    camera.time_offset = int((camera_utc - computer_utc).total_seconds())

# this will work as the argument for set_system_date_and_time for most cameras, but some may not implement DST properly, 
# so the safest option is to ignore DST. It was observed that Hikvision cameras may need a reboot for updating time protocol
def get_local_date_and_time(ignore_dst: bool = True) -> SystemDateAndTime:

    local_time = time.localtime()
    utc_time = time.gmtime()
    is_dst = False if ignore_dst else local_time.tm_isdst > 0
    offset = -local_time.tm_gmtoff if ignore_dst else time.timezone
    offset_hours = offset // 3600
    offset_minutes = (offset % 3600) // 60
    timezone = f"UTC{offset_hours:+03d}:{offset_minutes:02d}"

    return SystemDateAndTime(
        date_time_type="Manual",
        daylight_savings=is_dst,
        time_zone=TimeZone(timezone),
        local_date_time=DateTime(
            date=Date(year=local_time.tm_year, month=local_time.tm_mon, day=local_time.tm_mday),
            time=Time(hour=local_time.tm_hour, minute=local_time.tm_min, second=local_time.tm_sec)
        ),
        utc_date_time=DateTime(
            date=Date(year=utc_time.tm_year, month=utc_time.tm_mon, day=utc_time.tm_mday),
            time=Time(hour=utc_time.tm_hour, minute=utc_time.tm_min, second=utc_time.tm_sec)
        )
    )

def set_system_date_and_time(camera: Camera, sdt: SystemDateAndTime) -> str:
    body = f"""
<tds:SetSystemDateAndTime>
    <tds:DateTimeType>{sdt.date_time_type}</tds:DateTimeType>
    <tds:DaylightSavings>{str(sdt.daylight_savings).lower()}</tds:DaylightSavings>
    <tds:TimeZone><tt:TZ>{sdt.time_zone.tz}</tt:TZ></tds:TimeZone>
    <tds:UTCDateTime>
        <tt:Time>
            <tt:Hour>{sdt.utc_date_time.time.hour}</tt:Hour>
            <tt:Minute>{sdt.utc_date_time.time.minute}</tt:Minute>
            <tt:Second>{sdt.utc_date_time.time.second}</tt:Second>
        </tt:Time>
        <tt:Date>
            <tt:Year>{sdt.utc_date_time.date.year}</tt:Year>
            <tt:Month>{sdt.utc_date_time.date.month}</tt:Month>
            <tt:Day>{sdt.utc_date_time.date.day}</tt:Day>
        </tt:Date>
    </tds:UTCDateTime>
</tds:SetSystemDateAndTime>""".strip()
    return onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)

# when setting camera time using an NTP server, you need to first set_ntp with the NTP server information or accept DHCP settings, 
# then call set_system_date_and_time with the DateTimeType set to 'NTP'. It has been observed that many cameras do not implement
# manual NTP server settings for DNS. Also, only a few cameras properly parse a list of servers, many use only the first item
def set_ntp(camera: Camera) -> str:
    manual_settings = ""
    if not camera.ntp.from_dhcp:
        arg = ""
        manual_settings = ""
        for address_text in camera.ntp.ntp_manual:

            ip_type = "DNS"
            try:
                ip = ipaddress.ip_address(address_text)
                if ip.version == 4:
                    ip_type = "IPv4"
                if ip.version == 6:
                    ip_type = "IPv6"
            except Exception as ex:
                pass

            match ip_type:
                case 'IPv4':
                    arg = f"<tt:IPv4Address>{ip}</tt:IPv4Address>"
                case 'IPv6':
                    arg = f"<tt:IPv6Address>{ip}</tt:IPv6Address>"
                case 'DNS':
                    arg = f"<tt:DNSname>{address_text}</tt:DNSname>"

            manual_settings += f"""<tds:NTPManual><tt:Type>{ip_type}</tt:Type>{arg}</tds:NTPManual>""".strip()

    body = f"""<tds:SetNTP><tds:FromDHCP>{str(camera.ntp.from_dhcp).lower()}</tds:FromDHCP>{manual_settings}</tds:SetNTP>""".strip()
    return onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)

############################################################################################################


# these two queries come first in camera data population and will trigger authorization execptions if the credentials are not correct
# some cameras may allow get_capabilities without authorization, so both are needed for a proper credential check
# the @safe_run decorator is not used, the authorization exception is an opportunity to collect credentials from the user
def get_capabilities(camera: Camera) -> None:
    body = """<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>"""
    xml = onvif_post(camera.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "capabilities", parse_capabilities_response(xml))

def get_device_information(camera: Camera) -> str:
    body = """<tds:GetDeviceInformation/>"""
    xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "device_information", parse_device_information_response(xml))
#######################################################################################################################################

@safe_run
def get_profiles(camera: Camera) -> str:
    body = "<trt:GetProfiles/>"
    xml = onvif_post(camera.capabilities.media.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "profiles", parse_profiles_response(xml))

@safe_run
def get_stream_uri(camera: Camera, profile: Profile) -> None:
    body = f"""<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>{profile.token}</trt:ProfileToken></trt:GetStreamUri>"""
    xml = onvif_post(camera.capabilities.media.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(profile, "stream_uri", get_xml_value(xml, "//s:Body//trt:GetStreamUriResponse//trt:MediaUri//tt:Uri"))

@safe_run
def get_snapshot_uri(camera: Camera, profile: Profile) -> None:
    body = f"""<trt:GetSnapshotUri><trt:ProfileToken>{profile.token}</trt:ProfileToken></trt:GetSnapshotUri>"""
    xml = onvif_post(camera.capabilities.media.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(profile, "snapshot_uri", get_xml_value(xml, "//s:Body//trt:GetSnapshotUriResponse//trt:MediaUri//tt:Uri"))

@safe_run
def get_video_encoder_configuration_options(camera: Camera, profile: Profile) -> None:
    body = f"""<trt:GetVideoEncoderConfigurationOptions><trt:ConfigurationToken>{profile.video_encoder.token}</trt:ConfigurationToken><trt:ProfileToken>{profile.token}</trt:ProfileToken></trt:GetVideoEncoderConfigurationOptions>"""
    xml = onvif_post(camera.capabilities.media.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(profile, "video_encoder_options", parse_video_encoder_configuration_options_response(xml))

@safe_run
def get_audio_encoder_configuration_options(camera: Camera, profile: Profile) -> None:
    body = f"""<trt:GetAudioEncoderConfigurationOptions><trt:ProfileToken>{profile.token}</trt:ProfileToken></trt:GetAudioEncoderConfigurationOptions>"""
    xml = onvif_post(camera.capabilities.media.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(profile, "audio_encoder_options", parse_audio_encoder_configuration_options_response(xml))

@safe_run
def get_network_interfaces(camera: Camera) -> None:
    body = "<tds:GetNetworkInterfaces/>"
    xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera,  "network_interfaces", parse_network_interfaces_response(xml))

@safe_run
def get_hostname(camera: Camera) -> None:
    body = "<tds:GetHostname/>"
    xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "hostname", parse_hostname_response(xml))

@safe_run
def get_network_default_gateway(camera: Camera) -> str:
    body = f"""<tds:GetNetworkDefaultGateway/>"""
    xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "network_gateway", get_xml_value(xml, "//s:Body//tds:GetNetworkDefaultGatewayResponse//tds:NetworkGateway//tt:IPv4Address"))

@safe_run
def get_dns(camera: Camera) -> None:
    body = f"""<tds:GetDNS/>"""
    xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "dns", parse_dns_response(xml))

@safe_run
def get_ntp(camera: Camera) -> None:
    body = f"""<tds:GetNTP/>"""
    xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "ntp", parse_ntp_response(xml))

# this function does not follow design pattern. the audio output feature is not widely implemented, and could be removed without
# a large loss of functionality. Field presentation is supressed in the tui for the None case. Most users will not be looking for 
# this data and won't miss it. Be aware that the fields are presented at the camera level, but are implemented in profiles.py
def get_audio_decoder_configurations(camera: Camera) -> None:
    try:
        body = f"""<trt:GetAudioDecoderConfigurations/>"""
        xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
        setattr(camera, "audio_decoder", parse_audio_decoder_configurations_response(xml))
        body = f"""<trt:GetAudioOutputConfigurations/>"""
        xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
        setattr(camera, "audio_output", parse_audio_output_configurations_response(xml))
        body = f"""<trt:GetAudioDecoderConfigurationOptions/>"""
        xml = onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)
        setattr(camera, "audio_decoder_options", parse_audio_decoder_configuration_options_response(xml))
    except Exception as ex:
        ...

@safe_run
def get_service_capabilities(camera: Camera) -> None:
    body = f"""<tev:GetServiceCapabilities/>"""
    xml = onvif_post(camera.capabilities.events.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "service_capabilities", parse_service_capabilities_response(xml))

@safe_run
def get_event_properties(camera: Camera) -> None:
    body = f"""<tev:GetEventProperties/>"""
    xml = onvif_post(camera.capabilities.events.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(camera, "event_properties", parse_event_properties_response(xml))

@safe_run
def get_imaging_settings(camera: Camera, profile: Profile) -> None:
    body = f"""<timg:GetImagingSettings><timg:VideoSourceToken>{profile.video_source.source_token}</timg:VideoSourceToken></timg:GetImagingSettings>"""
    xml = onvif_post(camera.capabilities.imaging.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(profile, "imaging_settings", parse_imaging_settings_response(xml))

@safe_run
def get_imaging_options(camera: Camera, profile: Profile) -> None:
    body = f"""<timg:GetOptions><timg:VideoSourceToken>{profile.video_source.source_token}</timg:VideoSourceToken></timg:GetOptions>"""
    xml = onvif_post(camera.capabilities.imaging.xaddr, body, camera.username, camera.password, camera.time_offset)
    setattr(profile, "imaging_options", parse_imaging_options_response(xml))

def set_video_encoder_configuration(camera: Camera, encoder: VideoEncoderConfiguration) -> str:

    ip = ipaddress.ip_address(encoder.multicast.ip_address)
    if ip.version == 4:
        address_xml = f"""
            <tt:Address>
                <tt:Type>IPv4</tt:Type>
                <tt:IPv4Address>{ip}</tt:IPv4Address>
            </tt:Address>"""
    else:
        address_xml = f"""
            <tt:Address>
                <tt:Type>IPv6</tt:Type>
                <tt:IPv6Address>{ip}</tt:IPv6Address>
            </tt:Address>"""

    encoder_paramters = ""
    if encoder.encoding == "H264":
        encoder_paramters = f"""
        <tt:H264>
            <tt:GovLength>{encoder.gov_length if encoder.gov_length else 30}</tt:GovLength>
            <tt:H264Profile>{encoder.profile if encoder.profile in [ "Baseline", "Main", "Extended", "High"] else "High"}</tt:H264Profile>
        </tt:H264>"""
    elif encoder.encoding == "MPEG4":
        encoder_paramters = f"""
        <tt:MPEG4>
            <tt:GovLength>{encoder.gov_length if encoder.gov_length else 30}</tt:GovLength>
            <tt:MPEG4Profile>{encoder.profile if encoder.profile in ["SP", "ASP"] else "SP"}</tt:MPEG4Profile>
        </tt:MPEG4>"""

    width = encoder.resolution.split("x")[0].strip()
    height = encoder.resolution.split("x")[1].strip()

    body = f"""
<trt:SetVideoEncoderConfiguration>
    <trt:Configuration token="{encoder.token}">
        <tt:Name>{encoder.name}</tt:Name>
        <tt:UseCount>{encoder.use_count}</tt:UseCount>
        <tt:Encoding>{encoder.encoding}</tt:Encoding>
        <tt:Resolution>
            <tt:Width>{width}</tt:Width>
            <tt:Height>{height}</tt:Height>
        </tt:Resolution>
        <tt:Quality>{encoder.quality}</tt:Quality>
        <tt:RateControl>
            <tt:FrameRateLimit>{encoder.rate_control.frame_rate_limit}</tt:FrameRateLimit>
            <tt:EncodingInterval>{encoder.rate_control.encoding_interval}</tt:EncodingInterval>
            <tt:BitrateLimit>{encoder.rate_control.bitrate_limit}</tt:BitrateLimit>
        </tt:RateControl>{encoder_paramters}
        <tt:Multicast>{address_xml}
            <tt:Port>{encoder.multicast.port}</tt:Port>
            <tt:TTL>{encoder.multicast.ttl}</tt:TTL>
            <tt:AutoStart>{str(encoder.multicast.auto_start).lower()}</tt:AutoStart>
        </tt:Multicast>
        <tt:SessionTimeout>{encoder.session_timeout}</tt:SessionTimeout>
    </trt:Configuration>
    <trt:ForcePersistence>true</trt:ForcePersistence>
</trt:SetVideoEncoderConfiguration>""".strip()

    return onvif_post(camera.capabilities.media.xaddr, body, camera.username, camera.password, camera.time_offset)


def set_audio_encoder_configuration(camera: Camera, encoder: AudioEncoderConfiguration) -> str:
    
    ip = ipaddress.ip_address(encoder.multicast.ip_address)
    if ip.version == 4:
        address_xml = f"""
            <tt:Address>
                <tt:Type>IPv4</tt:Type>
                <tt:IPv4Address>{ip}</tt:IPv4Address>
            </tt:Address>"""
    else:
        address_xml = f"""
            <tt:Address>
                <tt:Type>IPv6</tt:Type>
                <tt:IPv6Address>{ip}</tt:IPv6Address>
            </tt:Address>"""

    body = f"""
<trt:SetAudioEncoderConfiguration>
    <trt:Configuration token="{encoder.token}">
        <tt:Name>{encoder.name}</tt:Name>
        <tt:UseCount>{encoder.use_count}</tt:UseCount>
        <tt:Encoding>{encoder.encoding}</tt:Encoding>
        <tt:Bitrate>{encoder.bitrate}</tt:Bitrate>
        <tt:SampleRate>{encoder.sample_rate}</tt:SampleRate>
        <tt:Multicast>{address_xml}
            <tt:Port>{encoder.multicast.port}</tt:Port>
            <tt:TTL>{encoder.multicast.ttl}</tt:TTL>
            <tt:AutoStart>{str(encoder.multicast.auto_start).lower()}</tt:AutoStart>
        </tt:Multicast>
        <tt:SessionTimeout>{encoder.session_timeout}</tt:SessionTimeout>
    </trt:Configuration>
    <trt:ForcePersistence>true</trt:ForcePersistence>
</trt:SetAudioEncoderConfiguration>""".strip()

    return onvif_post(camera.capabilities.media.xaddr, body, camera.username, camera.password, camera.time_offset)

    
def set_imaging_settings(camera: Camera, video_source_token: str, imaging: ImagingSettings) -> str:
    ir_cut_filter = f"""
        <tt:IrCutFilter>{imaging.ir_cut_filter}</tt:IrCutFilter>""" if imaging.ir_cut_filter else ""
    body = f"""
<timg:SetImagingSettings>
    <timg:VideoSourceToken>{video_source_token}</timg:VideoSourceToken>
    <timg:ImagingSettings>
        <tt:Brightness>{int(imaging.brightness)}</tt:Brightness>
        <tt:ColorSaturation>{int(imaging.color_saturation)}</tt:ColorSaturation>
        <tt:Contrast>{int(imaging.contrast)}</tt:Contrast>
        <tt:Sharpness>{int(imaging.sharpness)}</tt:Sharpness>{ir_cut_filter}
    </timg:ImagingSettings>
</timg:SetImagingSettings>""".strip()

    return onvif_post(camera.capabilities.imaging.xaddr, body, camera.username, camera.password, camera.time_offset)


def set_network_interfaces(camera: Camera, network_interface: NetworkInterface, manual: List[str]) -> str:

    arg = ""
    for ip_address_string in manual:
        address = ip_address_string.split("/")[0].strip()
        prefix_length = ip_address_string.split("/")[1].strip()
        ip_address_xml = f"""
            <tt:Manual>
                <tt:Address>{address}</tt:Address>
                <tt:PrefixLength>{prefix_length}</tt:PrefixLength>
            </tt:Manual>"""
        arg += ip_address_xml

    body = f"""
<tds:SetNetworkInterfaces>
    <tt:InterfaceToken>{network_interface.token}</tt:InterfaceToken>
    <tt:NetworkInterface>
        <tt:IPv4>
            <tt:DHCP>{str(network_interface.ipv4.dhcp).lower()}</tt:DHCP>{arg}
        </tt:IPv4>
    </tt:NetworkInterface>
</tds:SetNetworkInterfaces>""".strip()
    
    return onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)

def reboot(camera: Camera) -> str:
    body = f"""
<tds:SystemReboot/>
"""
    return onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)

def unsubscribe(camera: Camera, subscription_reference: str):
    body = f"""
<wsnt:Unsubscribe/>
"""
    return onvif_post(subscription_reference, body, camera.username, camera.password, camera.time_offset)

def set_network_default_gateway(camera: Camera) -> str:
    body = f"""
<tds:SetNetworkDefaultGateway>
    <tt:IPv4Address>{camera.network_gateway}</tt:IPv4Address>
</tds:SetNetworkDefaultGateway>""".strip()
    
    return onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)

def set_hostname_from_dhcp(camera: Camera) -> str:
    body = f"""
<tds:SetHostnameFromDHCP>
    <tds:FromDHCP>{str(camera.hostname.from_dhcp).lower()}</tds:FromDHCP>
</tds:SetHostnameFromDHCP>""".strip()
    
    return onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)

def set_hostname(camera: Camera) -> str:
    body = f"""
<tds:SetHostname>
    <tds:Name>{camera.hostname.name}</tds:Name>
</tds:SetHostname>
""".strip()
    
    return onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)

def set_dns(camera: Camera) -> str:
    manual_xml = ""
    for address_text in camera.dns.dns_manual:
        ip = ipaddress.ip_address(address_text)

        if ip.version == 4:
            ip_type = "IPv4"
            address_xml = f"<tt:IPv4Address>{ip}</tt:IPv4Address>"
        else:
            ip_type = "IPv6"
            address_xml = f"<tt:IPv6Address>{ip}</tt:IPv6Address>"

        manual_xml += f"""
            <tds:DNSManual>
                <tt:Type>{ip_type}</tt:Type>
                {address_xml}
            </tds:DNSManual>
        """

    body = f"""
<tds:SetDNS>
    <tds:FromDHCP>{str(camera.dns.from_dhcp).lower()}</tds:FromDHCP>{manual_xml}
</tds:SetDNS>
""".strip()
    
    return onvif_post(camera.capabilities.device.xaddr, body, camera.username, camera.password, camera.time_offset)

@safe_run
def subscribe_events(camera: Camera, event: str) -> str:
    callback_url = "http://10.1.1.76:8800/onvif/events"
    initial_termination_time = "PT1M"

    filter = f"""    
                <wsnt:Filter>
                    <wsnt:TopicExpression Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:{event}</wsnt:TopicExpression>
                </wsnt:Filter>"""
    
    body = f"""
        <wsnt:Subscribe>
            <wsnt:ConsumerReference>
                <wsa:Address>{callback_url}</wsa:Address>
            </wsnt:ConsumerReference>{filter}
            <wsnt:InitialTerminationTime>{initial_termination_time}</wsnt:InitialTerminationTime>
        </wsnt:Subscribe>""".strip()
    
    #return body
    xml = onvif_post(camera.capabilities.events.xaddr, body, camera.username, camera.password, camera.time_offset)
    subscription_reference = get_xml_value(xml, "//s:Body//wsnt:SubscribeResponse//wsnt:SubscriptionReference//wsa:Address")
    termination_time = get_xml_value(xml, "//s:Body//wsnt:TerminationTime")
    setattr(camera.event_properties, "subscription_reference", subscription_reference)
    setattr(camera.event_properties, "termination_time", termination_time)

#            <wsnt:Filter>
#                <wsnt:TopicExpression Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:VideoSource/MotionAlarm</wsnt:TopicExpression>
#            </wsnt:Filter>


def parse_device_information_response(xml: str) -> DeviceInformation:
    root = ET.fromstring(xml)

    elem = root.find(
        ".//tds:GetDeviceInformationResponse",
        NS,
    )
    if elem is None:
        raise ValueError(
            "Could not find tds:GetDeviceInformation"
        )

    return DeviceInformation(
        manufacturer=text(elem, "tds:Manufacturer"),
        model=text(elem, "tds:Model"),
        firmware_version=text(elem, "tds:FirmwareVersion"),
        serial_number=text(elem, "tds:SerialNumber"),
        hardware_id=text(elem, "tds:HardwareId"),
    )

def get_camera(username: str, password: str, xaddr: str, name: str) -> Camera:
    camera = Camera(username=username, password=password, xaddr=xaddr, name=name)
    get_time_offset(camera)

    try:
        # These are the first camera queries that (may) require authorization, trap the error for user interface, don't use @safe_run
        get_capabilities(camera)
        get_device_information(camera)
    except Exception as ex:
        logger.error(f"UNABLE TO COMMUNICATE WITH CAMERA {name}: {ex}")
        logger.debug(traceback.format_exc())
        if "notauthorized" in str(ex).lower():
            raise AuthorizationError("Not Authorized")
        raise ex
    
    get_service_capabilities(camera)
    get_event_properties(camera)
    subscribe_events(camera)

    get_network_interfaces(camera)
    get_network_default_gateway(camera)
    get_hostname(camera)
    get_dns(camera)
    get_ntp(camera)
    get_profiles(camera)
    get_audio_decoder_configurations(camera) # odd
    for profile in camera.profiles:
        get_stream_uri(camera, profile)
        get_snapshot_uri(camera, profile)
        get_video_encoder_configuration_options(camera, profile)
        if profile.audio_encoder:
            get_audio_encoder_configuration_options(camera, profile)
        if camera.capabilities.imaging:    
            get_imaging_settings(camera, profile)
            get_imaging_options(camera, profile)
            
    return camera
 
def discover(ip_address: str, camera_filled: Callable[[Camera], None] | None = None) -> list[Camera]:
    cameras = []
    camera_jobs = []
    msg_id = uuid.uuid4()
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"><SOAP-ENV:Header><a:Action SOAP-ENV:mustUnderstand="1">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action><a:MessageID>urn:uuid:{msg_id}</a:MessageID><a:ReplyTo><a:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:Address></a:ReplyTo><a:To SOAP-ENV:mustUnderstand="1">urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To></SOAP-ENV:Header><SOAP-ENV:Body><p:Probe xmlns:p="http://schemas.xmlsoap.org/ws/2005/04/discovery"><d:Types xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dp0="http://www.onvif.org/ver10/network/wsdl">dp0:NetworkVideoTransmitter</d:Types></p:Probe></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    timeout = 0.5
    responses = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((ip_address, 0))
    sock.settimeout(timeout)
    ttl = struct.pack("b", 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    multicast_address = ("239.255.255.250", 3702)
    sock.sendto(soap.encode("utf-8"), multicast_address)
    receiver_buffer_size = 8192
    while True:
        try:
            data, addr = sock.recvfrom(receiver_buffer_size)
            response = data.decode("utf-8", errors="ignore")
            responses.append(response)
        except socket.timeout:
            break
    sock.close()

    for result in responses:
        if not str(msg_id) in get_xml_value(result, "//s:Header//a:RelatesTo"):
            continue

        name = get_camera_name(result)
        xaddrs = get_xml_value(result, "//s:Body//d:ProbeMatches//d:ProbeMatch//d:XAddrs").split()
        for xaddr in xaddrs:
            duplicate = False
            for x, n in camera_jobs:
                if x == xaddr:
                    duplicate = True
                    break
            if duplicate:
                continue

            ip_obj = ipaddress.ip_address(urlparse(xaddr).hostname)
            if ip_obj.version == 6:
                continue
            if ip_obj.is_link_local:
                continue

            camera_jobs.append((xaddr, name))

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(get_camera, "admin", "admin123", xaddr, name)
            for xaddr, name in camera_jobs
        ]

        for future in as_completed(futures):
            if camera := future.result():
                cameras.append(camera)

                if camera_filled:
                    camera_filled(camera)

    return cameras
