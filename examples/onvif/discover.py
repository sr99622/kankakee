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
from utils.soap import onvif_post
from kankakee import Adapter, NetUtil, Broadcaster

from datastructures.capabilities import Capabilities, parse_capabilities_response
from datastructures.profiles import Profile, parse_profiles_response, \
        parse_video_encoder_configuration_options_response, \
        parse_audio_encoder_configuration_options_response
from datastructures.network import NetworkInterface, DNSInformation, NTPInformation, \
        parse_network_interfaces_response, parse_dns_response, parse_ntp_response
from datastructures.imaging import ImagingSettings, ImagingOptions, \
        parse_imaging_settings_response, parse_imaging_options_response

def check_ip_in_subnet(ip_to_check, network_ip, netmask):
    try:
        network = ipaddress.IPv4Network(f"{network_ip}/{netmask}", strict=False)
        address = ipaddress.IPv4Address(ip_to_check)
        return address in network
    except ValueError:
        return False

def get_camera_name(xml_data):
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

def get_time_offset(url):
    soap = """<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><SOAP-ENV:Body><tds:GetSystemDateAndTime/></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()

    base = "//s:Body//tds:GetSystemDateAndTimeResponse//tds:SystemDateAndTime"
    hour   = get_xml_value(response.content, f"{base}//tt:UTCDateTime//tt:Time//tt:Hour")
    minute = get_xml_value(response.content, f"{base}//tt:UTCDateTime//tt:Time//tt:Minute")
    second = get_xml_value(response.content, f"{base}//tt:UTCDateTime//tt:Time//tt:Second")
    year   = get_xml_value(response.content, f"{base}//tt:UTCDateTime//tt:Date//tt:Year")
    month  = get_xml_value(response.content, f"{base}//tt:UTCDateTime//tt:Date//tt:Month")
    day    = get_xml_value(response.content, f"{base}//tt:UTCDateTime//tt:Date//tt:Day")
    dst    = get_xml_value(response.content, f"{base}//tt:DaylightSavings") == "true"
    tz     = get_xml_value(response.content, f"{base}//tt:TimeZone//tt:TZ")

    camera_utc = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second), tzinfo=timezone.utc).astimezone(timezone.utc)
    computer_utc = datetime.now(timezone.utc)
    return int((camera_utc - computer_utc).total_seconds())

def get_capabilities(url, username, password, time_offset):
    body = """<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>"""
    return onvif_post(url, body, username, password, time_offset)

def get_device_information(url, username, password, time_offset):
    body = """<tds:GetDeviceInformation/>"""
    return onvif_post(url, body, username, password, time_offset)

def get_profiles(url, username, password, time_offset):
    body = "<trt:GetProfiles/>"
    return onvif_post(url, body, username, password, time_offset)

def get_video_encoder_configuration(url, username, password, time_offset, video_encoder_configuration_token):
    body = f"""<trt:GetVideoEncoderConfiguration><trt:ConfigurationToken>{video_encoder_configuration_token}</trt:ConfigurationToken></trt:GetVideoEncoderConfiguration>"""
    return onvif_post(url, body, username, password, time_offset)

def get_video_encoder_configuration_options(url, username, password, time_offset, configuration_token, profile_token):
    body = f"""<trt:GetVideoEncoderConfigurationOptions><trt:ConfigurationToken>{configuration_token}</trt:ConfigurationToken><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetVideoEncoderConfigurationOptions>"""
    return onvif_post(url, body, username, password, time_offset)

def get_audio_encoder_configuration_options(url, username, password, time_offset, profile_token):
    body = f"""<trt:GetAudioEncoderConfigurationOptions><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetAudioEncoderConfigurationOptions>"""
    return onvif_post(url, body, username, password, time_offset)

def get_network_interfaces(url, username, password, time_offset):
    body = "<tds:GetNetworkInterfaces/>"
    return onvif_post(url, body, username, password, time_offset)

def get_stream_uri(url, username, password, time_offset, profile_token):
    body = f"""<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetStreamUri>"""
    return onvif_post(url, body, username, password, time_offset)

def get_snapshot_uri(url, username, password, time_offset, profile_token):
    body = f"""<trt:GetSnapshotUri><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetSnapshotUri>"""
    return onvif_post(url, body, username, password, time_offset)

def get_network_default_gateway(url, username, password, time_offset):
    body = f"""<tds:GetNetworkDefaultGateway/>"""
    return onvif_post(url, body, username, password, time_offset)

def get_dns(url, username, password, time_offset):
    body = f"""<tds:GetDNS/>"""
    return onvif_post(url, body, username, password, time_offset)

def get_ntp(url, username, password, time_offset):
    body = f"""<tds:GetNTP/>"""
    return onvif_post(url, body, username, password, time_offset)

def get_imaging_settings(url, username, password, time_offset, video_source_token):
    body = f"""<timg:GetImagingSettings><timg:VideoSourceToken>{video_source_token}</timg:VideoSourceToken></timg:GetImagingSettings>"""
    return onvif_post(url, body, username, password, time_offset)

def get_imaging_options(url, username, password, time_offset, video_source_token):
    body = f"""<timg:GetOptions><timg:VideoSourceToken>{video_source_token}</timg:VideoSourceToken></timg:GetOptions>"""
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

    if capabilities_xml := get_capabilities(xaddr, camera.username, camera.password, camera.time_offset):
        capabilities = parse_capabilities_response(capabilities_xml)
        setattr(camera, "capabilities", capabilities)
    else:
        logger.error("UNABLE TO COMMUNICATE WITH CAMERA")
        return None 
    
    if device_information_xml := get_device_information(capabilities.device.xaddr, camera.username, camera.password, camera.time_offset):
        serial_number = get_xml_value(device_information_xml, "//s:Body//tds:GetDeviceInformationResponse//tds:SerialNumber")
        setattr(camera, "serial_number", serial_number)
    if network_interfaces_xml := get_network_interfaces(capabilities.device.xaddr, camera.username, camera.password, camera.time_offset):
        network_interfaces = parse_network_interfaces_response(network_interfaces_xml)
        setattr(camera, "network_interfaces", network_interfaces)
    if network_gateway_xml := get_network_default_gateway(capabilities.device.xaddr, camera.username, camera.password, camera.time_offset):
        network_gateway = get_xml_value(network_gateway_xml, "//s:Body//tds:GetNetworkDefaultGatewayResponse//tds:NetworkGateway//tt:IPv4Address")
        setattr(camera, "network_gateway", network_gateway)
    if dns_xml := get_dns(capabilities.device.xaddr, camera.username, camera.password, camera.time_offset):
        dns = parse_dns_response(dns_xml)
        setattr(camera, "dns", dns)
    if ntp_xml := get_ntp(capabilities.device.xaddr, camera.username, camera.password, camera.time_offset):
        ntp = parse_ntp_response(ntp_xml)
        setattr(camera, "ntp", ntp)

    if profiles_xml := get_profiles(capabilities.media.xaddr, camera.username, camera.password, camera.time_offset):
        profiles = parse_profiles_response(profiles_xml)
        setattr(camera, "profiles", profiles)
        for profile in profiles:
            if stream_uri_xml := get_stream_uri(capabilities.media.xaddr, camera.username, camera.password, camera.time_offset, profile.token):
                stream_uri = get_xml_value(stream_uri_xml, "//s:Body//trt:GetStreamUriResponse//trt:MediaUri//tt:Uri")
                setattr(profile, "stream_uri", stream_uri)
            if snapshot_uri_xml := get_snapshot_uri(capabilities.media.xaddr, camera.username, camera.password, camera.time_offset, profile.token):
                snapshot_uri = get_xml_value(snapshot_uri_xml, "//s:Body//trt:GetSnapshotUriResponse//trt:MediaUri//tt:Uri")
                setattr(profile, "snapshot_uri", snapshot_uri)
            if video_options_xml := get_video_encoder_configuration_options(capabilities.media.xaddr, camera.username, camera.password, camera.time_offset, profile.video_encoder.token, profile.token):
                video_encoder_options = parse_video_encoder_configuration_options_response(video_options_xml)
                setattr(profile, "video_encoder_options", video_encoder_options)
            
            if profile.audio_encoder:
                if audio_options_xml := get_audio_encoder_configuration_options(capabilities.media.xaddr, camera.username, camera.password, camera.time_offset, profile.token):
                    audio_options = parse_audio_encoder_configuration_options_response(audio_options_xml)
                    setattr(profile, "audio_encoder_options", audio_options)

            if capabilities.imaging:
                if imaging_xml := get_imaging_settings(capabilities.imaging.xaddr, camera.username, camera.password, camera.time_offset, profile.video_source.source_token):
                    imaging = parse_imaging_settings_response(imaging_xml)
                    setattr(profile, "imaging_settings", imaging)
                if options_xml := get_imaging_options(capabilities.imaging.xaddr, camera.username, camera.password, camera.time_offset, "profile.video_source.source_token"):
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
