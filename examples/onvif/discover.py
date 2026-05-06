from loguru import logger
import traceback
import uuid
from urllib.parse import unquote_plus, urlparse
import ipaddress
from utils.xml import get_xml_value
from kankakee import Adapter, NetUtil, Broadcaster
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed

from devices.camera import Camera, get_camera, get_system_date_and_time, set_system_date_and_time

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

def camera_filled(camera: Camera) -> None:
    print(f"DATA FILLED FOR CAMERA {camera.name}")
    print("*", camera.name, camera.xaddr)
    if camera.profiles:
        for profile in camera.profiles:
            print(profile.token, profile.video_encoder.resolution.width, profile.video_encoder.gov_length)
            print(profile.stream_uri)
            print(profile.snapshot_uri)

    for interface in camera.network_interfaces:
        print(f"INTERFACE: {interface.enabled} {interface.info.name} {interface.info.hw_address} {interface.info.mtu}")
        print(f"ADDRESS: {interface.ipv4.from_dhcp.address} / {interface.ipv4.from_dhcp.prefix_length}")
        print(f"DHCP ENABLED: {interface.ipv4.dhcp}")

def discover(adapter: Adapter, msg_id: uuid) -> list[str]:
    output = []

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

if __name__ == "__main__":
    cameras = []
    camera_jobs = []
    try:
        msg_id = uuid.uuid4()
        adapters = NetUtil().getAllAdapters()
        for adapter in adapters:
            if not adapter.up:
                continue
            if adapter.type.lower() == "loopback":
                continue

            print("ADAPTER IP:", adapter.ip_address)
            print("ADAPTER TYPE:", adapter.type)

            results = discover(adapter, msg_id)
            for result in results:
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

                    host = urlparse(xaddr).hostname
                    if not check_ip_in_subnet(host, adapter.ip_address, adapter.netmask):
                        continue

                    camera_jobs.append((xaddr, name))
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(get_camera, "admin", "admin123", xaddr, name)
                for xaddr, name in camera_jobs
            ]

            for future in as_completed(futures):
                if camera := future.result():
                    camera_filled(camera)
                    cameras.append(camera)

    except Exception as ex:
        logger.error(f"discovery error: {ex}")
        logger.debug(traceback.format_exc())
