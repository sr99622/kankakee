from loguru import logger
import traceback
import uuid
import requests
from datetime import datetime, timezone, timedelta
import re
import base64
import hashlib
import os
from urllib.parse import unquote_plus, urlparse
import ipaddress
from dataclasses import dataclass, field
from typing import Optional
from utils.xml import get_xml_value
from utils.soap import onvif_post, parse_soap_fault, POST_TIMEOUT
from kankakee import Adapter, NetUtil, Broadcaster
from functools import wraps

from datastructures.capabilities import Capabilities, parse_capabilities_response
from datastructures.profiles import Profile, parse_profiles_response, \
        parse_video_encoder_configuration_options_response, \
        parse_audio_encoder_configuration_options_response
from datastructures.network import NetworkInterface, DNSInformation, \
        parse_network_interfaces_response, parse_dns_response
from datastructures.imaging import ImagingSettings, ImagingOptions, \
        parse_imaging_settings_response, parse_imaging_options_response
from datastructures.datetime import SystemDateAndTime,  NTPInformation, NetworkHost, \
        parse_system_date_and_time_response, parse_ntp_response

def safe_run(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            return None
    return wrapper

def check_ip_in_subnet(ip_to_check: str, network_ip: str, netmask: int) -> bool:
    try:
        network = ipaddress.IPv4Network(f"{network_ip}/{netmask}", strict=False)
        address = ipaddress.IPv4Address(ip_to_check)
        return address in network
    except ValueError:
        return False

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

# this camera query does not require authorization, so it has a different design pattern than those that do
@safe_run
def get_system_date_and_time(url: str) -> str:
    soap = """<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><SOAP-ENV:Body><tds:GetSystemDateAndTime/></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=POST_TIMEOUT)
    fault = parse_soap_fault(response.text)
    if fault:
        raise ValueError(str(fault))
    response.raise_for_status()
    return response.text

def get_time_offset(url: str) -> int:
    if sdt_xml := get_system_date_and_time(url):
        sdt = parse_system_date_and_time_response(sdt_xml)
        camera_utc = datetime(sdt.utc_date_time.date.year, sdt.utc_date_time.date.month, sdt.utc_date_time.date.day, 
            sdt.utc_date_time.time.hour, sdt.utc_date_time.time.minute, sdt.utc_date_time.time.second).replace(tzinfo=timezone.utc)
        computer_utc = datetime.now(timezone.utc)
        return int((camera_utc - computer_utc).total_seconds())
    else:
        return 0

# these two queries come first in camera data population and will trigger authorization execptions if the credentials are not correct
# some cameras may allow get_capabilities without authorization, so both are needed for a proper credential check
# the @safe_run decorator is not used, the authorization exception is an opportunity to collect credentials from the user
def get_capabilities(url: str, username: str, password: str, time_offset: int) -> str:
    body = """<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>"""
    return onvif_post(url, body, username, password, time_offset)

def get_device_information(url: str, username: str, password: str, time_offset: int) -> str:
    body = """<tds:GetDeviceInformation/>"""
    return onvif_post(url, body, username, password, time_offset)
#######################################################################################################################################

@safe_run
def get_profiles(url: str, username: str, password: str, time_offset: int) -> str:
    body = "<trt:GetProfiles/>"
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_video_encoder_configuration(url: str, username: str, password: str, time_offset: int, video_encoder_configuration_token: str) -> str:
    body = f"""<trt:GetVideoEncoderConfiguration><trt:ConfigurationToken>{video_encoder_configuration_token}</trt:ConfigurationToken></trt:GetVideoEncoderConfiguration>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_video_encoder_configuration_options(url: str, username: str, password: str, time_offset: int, configuration_token: str, profile_token: str) -> str:
    body = f"""<trt:GetVideoEncoderConfigurationOptions><trt:ConfigurationToken>{configuration_token}</trt:ConfigurationToken><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetVideoEncoderConfigurationOptions>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_audio_encoder_configuration_options(url: str, username: str, password: str, time_offset: int, profile_token: str) -> str:
    body = f"""<trt:GetAudioEncoderConfigurationOptions><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetAudioEncoderConfigurationOptions>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_network_interfaces(url: str, username: str, password: str, time_offset: int) -> str:
    body = "<tds:GetNetworkInterfaces/>"
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_stream_uri(url: str, username: str, password: str, time_offset: int, profile_token: str) -> str:
    body = f"""<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetStreamUri>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_snapshot_uri(url: str, username: str, password: str, time_offset: int, profile_token: str) -> str:
    body = f"""<trt:GetSnapshotUri><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetSnapshotUri>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_network_default_gateway(url: str, username: str, password: str, time_offset: int) -> str:
    body = f"""<tds:GetNetworkDefaultGateway/>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_dns(url: str, username: str, password: str, time_offset: int) -> str:
    body = f"""<tds:GetDNS/>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_ntp(url: str, username: str, password: str, time_offset: int) -> str:
    body = f"""<tds:GetNTP/>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_imaging_settings(url: str, username: str, password: str, time_offset: int, video_source_token: str) -> str:
    body = f"""<timg:GetImagingSettings><timg:VideoSourceToken>{video_source_token}</timg:VideoSourceToken></timg:GetImagingSettings>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def get_imaging_options(url: str, username: str, password: str, time_offset: int, video_source_token: str) -> str:
    body = f"""<timg:GetOptions><timg:VideoSourceToken>{video_source_token}</timg:VideoSourceToken></timg:GetOptions>"""
    return onvif_post(url, body, username, password, time_offset)

@safe_run
def set_system_date_and_time(url:str, username: str, password: str, time_offset: int, sdt: SystemDateAndTime) -> None:
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
    return onvif_post(url, body, username, password, time_offset)


@safe_run
def set_ntp(url:str, username: str, password: str, time_offset: int, ntp: NTPInformation) -> None:

    manual_settings = ""
    if not ntp.from_dhcp:
        arg = ""
        manual = ntp.ntp_manual[0]
        match manual.type:
            case 'IPv4':
                address = manual.ipv4 if manual.ipv4 else ""
                arg = f"<tt:IPv4Address>{address}</tt:IPv4Address>"
            case 'IPv6':
                address = manual.ipv6 if manual.ipv6 else ""
                arg = f"<tt:IPv6Address>{address}</tt:IPv6Address>"
            case 'DNS':
                address = manual.dns if manual.dns else ""
                arg = f"<tt:DNSname>{address}</tt:DNSname>"

        manual_settings = f"""<tds:NTPManual><tt:Type>{manual.type}</tt:Type>{arg}</tds:NTPManual>""".strip()

    body = f"""<tds:SetNTP><tds:FromDHCP>{str(ntp.from_dhcp).lower()}</tds:FromDHCP>{manual_settings}</tds:SetNTP>""".strip()

    print(body)
    return onvif_post(url, body, username, password, time_offset)

@dataclass
class Camera:
    xaddr: Optional[str] = None
    name: Optional[str] = None
    serial_number: Optional[str] = None
    ip_address: Optional[str] = None
    time_offset: Optional[int] = 0
    username: Optional[str] = None
    password: Optional[str] = None
    capabilities: Optional[Capabilities] = None
    profiles: list[Profile] = None
    network_interfaces: list[NetworkInterface] = None
    network_gateway: Optional[str] = None
    dns: Optional[DNSInformation] = None
    ntp: Optional[NTPInformation] = None

def discover(adapter: Adapter, msg_id: uuid) -> list[str]:
    output = None

    try:
        soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"><SOAP-ENV:Header><a:Action SOAP-ENV:mustUnderstand="1">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action><a:MessageID>urn:uuid:{msg_id}</a:MessageID><a:ReplyTo><a:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:Address></a:ReplyTo><a:To SOAP-ENV:mustUnderstand="1">urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To></SOAP-ENV:Header><SOAP-ENV:Body><p:Probe xmlns:p="http://schemas.xmlsoap.org/ws/2005/04/discovery"><d:Types xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dp0="http://www.onvif.org/ver10/network/wsdl">dp0:NetworkVideoTransmitter</d:Types></p:Probe></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
        broadcaster = Broadcaster(adapter.ip_address, "239.255.255.250", 3702)
        broadcaster.errorCallback = logger.error
        broadcaster.send(soap)
        output = broadcaster.recv()
    except Exception as ex:
        logger.error(f'discover broadcast error: {ex}')
        logger.debug(traceback.format_exc())

    return output

def get_camera(username: str, password: str, xaddr: str, name: str) -> Camera:
    camera = Camera()
    setattr(camera, "name", name)
    setattr(camera, "xaddr", xaddr)
    setattr(camera, "username", username)
    setattr(camera, "password", password)
    setattr(camera, "time_offset", get_time_offset(xaddr))

    try:
        # These are the first camera queries that (may) require authorization, trap the error for user interface, don't use @safe_run
        capabilities_xml = get_capabilities(xaddr, username, password, camera.time_offset)
        capabilities = parse_capabilities_response(capabilities_xml)
        setattr(camera, "capabilities", capabilities)
        device_information_xml = get_device_information(capabilities.device.xaddr, username, password, camera.time_offset)
        serial_number = get_xml_value(device_information_xml, "//s:Body//tds:GetDeviceInformationResponse//tds:SerialNumber")
        setattr(camera, "serial_number", serial_number)
    except Exception as ex:
        logger.error(f"UNABLE TO COMMUNICATE WITH CAMERA {name}: {ex}")
        if "notauthorized" in str(ex).lower():
            print("AUTHORIZATION FAILURE")
        return None 
    
    if network_interfaces_xml := get_network_interfaces(capabilities.device.xaddr, username, password, camera.time_offset):
        network_interfaces = parse_network_interfaces_response(network_interfaces_xml)
        setattr(camera, "network_interfaces", network_interfaces)
    if network_gateway_xml := get_network_default_gateway(capabilities.device.xaddr, username, password, camera.time_offset):
        network_gateway = get_xml_value(network_gateway_xml, "//s:Body//tds:GetNetworkDefaultGatewayResponse//tds:NetworkGateway//tt:IPv4Address")
        setattr(camera, "network_gateway", network_gateway)
    if dns_xml := get_dns(capabilities.device.xaddr, username, password, camera.time_offset):
        dns = parse_dns_response(dns_xml)
        setattr(camera, "dns", dns)
    if ntp_xml := get_ntp(capabilities.device.xaddr, username, password, camera.time_offset):
        ntp = parse_ntp_response(ntp_xml)
        setattr(camera, "ntp", ntp)

        #ntp.from_dhcp = True
        #ntp.ntp_manual = [NetworkHost(type='IPv4', ipv4='10.1.1.67')]
        #ntp.ntp_manual = [NetworkHost(type='DNS', dns='pool.ntp.org')]
        #set_ntp(capabilities.device.xaddr, username, password, camera.time_offset, ntp)
    
    #if sdt_xml := get_system_date_and_time(capabilities.device.xaddr):
    #    sdt = parse_system_date_and_time_response(sdt_xml)
    #    response = set_system_date_and_time(capabilities.device.xaddr, username, password, camera.time_offset, sdt)

    if profiles_xml := get_profiles(capabilities.media.xaddr, username, password, camera.time_offset):
        profiles = parse_profiles_response(profiles_xml)
        setattr(camera, "profiles", profiles)
        for profile in profiles:
            if stream_uri_xml := get_stream_uri(capabilities.media.xaddr, username, password, camera.time_offset, profile.token):
                stream_uri = get_xml_value(stream_uri_xml, "//s:Body//trt:GetStreamUriResponse//trt:MediaUri//tt:Uri")
                setattr(profile, "stream_uri", stream_uri)
            if snapshot_uri_xml := get_snapshot_uri(capabilities.media.xaddr, username, password, camera.time_offset, profile.token):
                snapshot_uri = get_xml_value(snapshot_uri_xml, "//s:Body//trt:GetSnapshotUriResponse//trt:MediaUri//tt:Uri")
                setattr(profile, "snapshot_uri", snapshot_uri)
            if video_options_xml := get_video_encoder_configuration_options(capabilities.media.xaddr, username, password, camera.time_offset, profile.video_encoder.token, profile.token):
                video_encoder_options = parse_video_encoder_configuration_options_response(video_options_xml)
                setattr(profile, "video_encoder_options", video_encoder_options)
            
            if profile.audio_encoder:
                if audio_options_xml := get_audio_encoder_configuration_options(capabilities.media.xaddr, username, password, camera.time_offset, profile.token):
                    audio_options = parse_audio_encoder_configuration_options_response(audio_options_xml)
                    setattr(profile, "audio_encoder_options", audio_options)

            if capabilities.imaging:
                if imaging_xml := get_imaging_settings(capabilities.imaging.xaddr, username, password, camera.time_offset, profile.video_source.source_token):
                    imaging = parse_imaging_settings_response(imaging_xml)
                    setattr(profile, "imaging_settings", imaging)
                if options_xml := get_imaging_options(capabilities.imaging.xaddr, username, password, camera.time_offset, profile.video_source.source_token):
                    imaging_options = parse_imaging_options_response(options_xml)
                    setattr(profile, "imaging_options", imaging_options)
    
    return camera
 
if __name__ == "__main__":
    cameras = []
    try:
        msg_id = uuid.uuid4()
        adapters = NetUtil().getAllAdapters()
        for adapter in adapters:
            if not adapter.up:
                continue

            results = discover(adapter, msg_id)

            for result in results:
                relates_to = get_xml_value(result, "//s:Header//a:RelatesTo")
                if not str(msg_id) in get_xml_value(result, "//s:Header//a:RelatesTo"):
                    continue

                name = get_camera_name(result)
                xaddrs = get_xml_value(result, "//s:Body//d:ProbeMatches//d:ProbeMatch//d:XAddrs").split()
                for xaddr in xaddrs:
                    duplicate = False
                    for camera in cameras:
                        if xaddr == camera.xaddr:
                            duplicate = True
                            break
                    if duplicate:
                        continue

                    host = urlparse(xaddr).hostname
                    if not check_ip_in_subnet(host, adapter.ip_address, adapter.netmask):
                        continue

                    if camera := get_camera("admin", "admin123", xaddr, name):
                        cameras.append(camera)

    except Exception as ex:
        logger.error(f"discovery error: {ex}")
        logger.debug(traceback.format_exc())

    for camera in cameras:
        print(camera.name, camera.xaddr, camera.capabilities.media.xaddr, camera.capabilities.media.streaming.rtp_rtsp_tcp)
        if camera.profiles:
            for profile in camera.profiles:
                print(profile.token, profile.video_encoder.resolution.width, profile.video_encoder.gov_length)
                print(profile.stream_uri)
                print(profile.snapshot_uri)
