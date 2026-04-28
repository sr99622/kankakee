import kankakee
from loguru import logger
import traceback
import uuid
import requests
from lxml import etree
from datetime import datetime, timezone, timedelta
import re
import base64
import hashlib
import os
from urllib.parse import unquote_plus, urlparse
import ipaddress
from dataclasses import dataclass, field
from typing import Optional

from datastructures.capabilities import parse_capabilities_response, Capabilities
from datastructures.profiles import parse_profiles_response, parse_video_encoder_configuration_options_response, Profile

def create_wsse_header_data(password, offset_seconds):
    nonce_raw = os.urandom(20)
    nonce_b64 = base64.b64encode(nonce_raw).decode("ascii")
    created_dt = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    created = created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    digest_raw = hashlib.sha1(nonce_raw + created.encode("utf-8") + password.encode("utf-8")).digest()
    password_digest = base64.b64encode(digest_raw).decode("ascii")
    return password_digest, nonce_b64, created

def check_ip_in_subnet(ip_to_check, network_ip, netmask):
    try:
        network = ipaddress.IPv4Network(f"{network_ip}/{netmask}", strict=False)
        address = ipaddress.IPv4Address(ip_to_check)
        return address in network
    except ValueError:
        return False

def get_xml_value(xml_data, xpath):
    NSMAP = {
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
    }
    try:
        if isinstance(xml_data, str):
            xml_data = xml_data.encode("utf-8")
        doc = etree.fromstring(xml_data)
    except (etree.XMLSyntaxError, ValueError):
        return ""

    try:
        result = doc.xpath(xpath, namespaces=NSMAP)
    except etree.XPathError:
        return ""

    if not result:
        return ""

    node = result[0]
    if isinstance(node, etree._Element):
        return "".join(node.itertext()).strip()

    return str(node).strip()

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
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

def get_device_information(url, username, password, time_offset):
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><tds:GetDeviceInformation/></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

def get_profiles(url, username, password, time_offset):
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><trt:GetProfiles/></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

def get_profile(url, username, password, time_offset, profile_token):
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><trt:GetProfile><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetProfile></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

def get_video_encoder_configuration(url, username, password, time_offset, video_encoder_configuration_token):
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><trt:GetVideoEncoderConfiguration><trt:ConfigurationToken>{video_encoder_configuration_token}</trt:ConfigurationToken></trt:GetVideoEncoderConfiguration></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

def get_stream_uri(url, username, password, time_offset, profile_token):
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetStreamUri></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

def get_snapshot_uri(url, username, password, time_offset, profile_token):
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><trt:GetSnapshotUri><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetSnapshotUri></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

def get_video_encoder_configuration_options(url, username, password, time_offset, configuration_token, profile_token):
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><trt:GetVideoEncoderConfigurationOptions><trt:ConfigurationToken>{configuration_token}</trt:ConfigurationToken><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetVideoEncoderConfigurationOptions></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

def get_audio_encoder_configuration_options(url, username, password, time_offset, profile_token):
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)
    soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><SOAP-ENV:Header><wsse:Security SOAP-ENV:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{username}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></SOAP-ENV:Header><SOAP-ENV:Body><trt:GetAudioEncoderConfigurationOptions><trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetAudioEncoderConfigurationOptions></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
    response = requests.post(url, data=soap, timeout=5)
    response.raise_for_status()
    return response.content

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

if __name__ == "__main__":
    cameras = []
    try:
        msg_id = uuid.uuid4()
        soap = f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"><SOAP-ENV:Header><a:Action SOAP-ENV:mustUnderstand="1">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action><a:MessageID>urn:uuid:{msg_id}</a:MessageID><a:ReplyTo><a:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:Address></a:ReplyTo><a:To SOAP-ENV:mustUnderstand="1">urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To></SOAP-ENV:Header><SOAP-ENV:Body><p:Probe xmlns:p="http://schemas.xmlsoap.org/ws/2005/04/discovery"><d:Types xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dp0="http://www.onvif.org/ver10/network/wsdl">dp0:NetworkVideoTransmitter</d:Types></p:Probe></SOAP-ENV:Body></SOAP-ENV:Envelope>"""
        adapters = kankakee.NetUtil().getAllAdapters()
        for adapter in adapters:
            if not adapter.up:
                continue

            broadcaster = kankakee.Broadcaster(adapter.ip_address, "239.255.255.250", 3702)
            broadcaster.errorCallback = logger.error
            broadcaster.send(soap)
            results = broadcaster.recv()
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

                    camera = Camera()
                    setattr(camera, "name", name)
                    setattr(camera, "xaddr", xaddr)

                    try:
                        time_offset = get_time_offset(xaddr)
                        setattr(camera, "time_offset", time_offset)
                        capabilities = parse_capabilities_response(get_capabilities(xaddr, "admin", "admin123", time_offset))
                        setattr(camera, "capabilities", capabilities)
                        device_information = get_device_information(capabilities.device.xaddr, "admin", "admin123", time_offset)
                        serial_number = get_xml_value(device_information, "//s:Body//tds:GetDeviceInformationResponse//tds:SerialNumber")
                        setattr(camera, "serial_number", serial_number)
                        profiles = parse_profiles_response(get_profiles(capabilities.media.xaddr, "admin", "admin123", time_offset))
                        setattr(camera, "profiles", profiles)
                        for profile in profiles:
                            stream_information = get_stream_uri(capabilities.media.xaddr, "admin", "admin123", time_offset, profile.token)
                            stream_uri = get_xml_value(stream_information, "//s:Body//trt:GetStreamUriResponse//trt:MediaUri//tt:Uri")
                            setattr(profile, "stream_uri", stream_uri)
                            snapshot_information = get_snapshot_uri(capabilities.media.xaddr, "admin", "admin123", time_offset, profile.token)
                            snapshot_uri = get_xml_value(snapshot_information, "//s:Body//trt:GetSnapshotUriResponse//trt:MediaUri//tt:Uri")
                            setattr(profile, "snapshot_uri", snapshot_uri)
                            video_options = get_video_encoder_configuration_options(capabilities.media.xaddr, "admin", "admin123", time_offset, profile.video_encoder.token, profile.token)
                            video_encoder_cofiguration_options = parse_video_encoder_configuration_options_response(video_options)
                            setattr(profile, "video_encoder_options", video_encoder_cofiguration_options)

                            if profile.audio_encoder:
                                audio_options = get_audio_encoder_configuration_options(capabilities.media.xaddr, "admin", "admin123", time_offset, profile.token)
                                print(audio_options)

                    except Exception as ex:
                        logger.error(f"{camera.name} communication error: {ex}")
                        logger.debug(traceback.format_exc())

                    cameras.append(camera)

    except Exception as ex:
        logger.error(f"discovery error: {ex}")
        logger.debug(traceback.format_exc())

    print("TEST POINT")
    for camera in cameras:
        print(camera.name, camera.xaddr, camera.capabilities.media.xaddr, camera.capabilities.media.streaming.rtp_rtsp_tcp)
        for profile in camera.profiles:
            print(profile.token, profile.video_encoder.resolution.width, profile.video_encoder.gov_length)
            #for resolution in profile.video_encoder_options.h264.resolutions_available:
            #    print(resolution.width, resolution.height)
