from loguru import logger
import traceback
import uuid
import ipaddress
from urllib.parse import unquote_plus, urlparse
from utils.xml import get_xml_value
from kankakee import Adapter, NetUtil, Broadcaster
from concurrent.futures import ThreadPoolExecutor, as_completed

from datastructures.datetime import NetworkHost, NTPInformation
from devices.camera import Camera, get_camera, get_system_date_and_time, set_system_date_and_time, \
        get_local_date_and_time, set_ntp, set_network_interfaces, discover
from datastructures.network import PrefixedIPv4Address

def camera_filled(camera: Camera) -> None:
    print(f"DATA FILLED FOR CAMERA {camera.name}")
    print("*", camera.name, camera.xaddr)
    
    '''
    sdt = get_system_date_and_time(camera.xaddr)
    print(f"SYSTEM DATE AND TIME: {sdt}")
    #set_system_date_and_time(camera, sdt)
    #local_sdt = get_local_date_and_time()
    #print(f"LOCAL DATE AND TIME: {local_sdt}")
    #set_system_date_and_time(camera, local_sdt)
    try:
        ntp_servers=[NetworkHost(type="IPv4", ipv4="129.6.15.28"), NetworkHost(type="IPv4", ipv4="132.163.96.4")]
        print(f"NTP: {camera.ntp}")
        ntp_information = NTPInformation(from_dhcp=False, ntp_manual=ntp_servers)
        set_ntp(camera, ntp_information)
        local_sdt = get_local_date_and_time()
        print(f"LOCAL SDT: {local_sdt}")
        local_sdt.date_time_type = 'NTP'
        set_system_date_and_time(camera, local_sdt)
    except Exception as ex:
        logger.error(f"NTP FAILURE: {ex}")
    '''

    '''
    if camera.profiles:
        for profile in camera.profiles:
            print(profile.token, profile.video_encoder.resolution.width, profile.video_encoder.gov_length)
            print(profile.stream_uri)
            print(profile.snapshot_uri)
    '''

    #'''
    print(f"FOUND {len(camera.network_interfaces)} INTERFACES ON CAMERA")
    for interface in camera.network_interfaces:
        print(f"INTERFACE: {interface.enabled} {interface.info.name} {interface.info.hw_address} {interface.info.mtu}")
        if interface.ipv4.dhcp:
            print("DHCP ENABLED")
            if from_dhcp := interface.ipv4.from_dhcp:
                print(f"FROM DHCP ADDRESS: {from_dhcp.address} / {from_dhcp.prefix_length}")
        else:
            print("DHCP DISABLED")
            for manual in interface.ipv4.manual:
                print(f"MANUALLY SET ADDRESS: {manual.address} / {manual.prefix_length}")

            #interface.ipv4.dhcp = True
            #interface.ipv4.manual = [PrefixedIPv4Address(address="10.1.1.253", prefix_length=24)]
            #if set_network_interfaces(camera, interface):
            #    print(f"REBOOT REQUIRED FOR CAMERA: {camera.name}")
            #else:
            #    print("REBOOT IS NOT REQUIRED")
    #'''

    names = {"HIKVISION DS-2CD2142FWD-IS":"10.1.1.253", "LOREX LNB8973B":"10.1.1.252", "O4VD2":"10.1.1.251", 
                "Amcrest IP2M-841EB":"10.1.1.250", "AXIS M1065-LW":"10.1.1.249"}
    

    '''
    if not camera.network_interfaces[0].ipv4.dhcp and camera.name in names:
        print(f"CAMERA IP ADDRESS: {names[camera.name]}")
        interface = camera.network_interfaces[0]
        interface.ipv4.dhcp = True
        #interface.ipv4.manual = [PrefixedIPv4Address(address=names[camera.name], prefix_length=24)]
        if set_network_interfaces(camera, interface):
            print(f"REBOOT REQUIRED FOR CAMERA: {camera.name}")
        else:
            print("REBOOT IS NOT REQUIRED")
    #'''

if __name__ == "__main__":
    cameras = []
    camera_jobs = []
    try:
        adapters = NetUtil().getAllAdapters()
        for adapter in adapters:
            if not adapter.up:
                continue
            if adapter.type.lower() == "loopback":
                continue

            cameras = discover(adapter.ip_address)
            for camera in cameras:
                camera_filled(camera)

    except Exception as ex:
        logger.error(f"discovery error: {ex}")
        logger.debug(traceback.format_exc())
