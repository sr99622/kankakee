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
    print("*", camera.name, camera.dns)

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

            cameras = discover(adapter.ip_address, camera_filled)
            #for camera in cameras:
            #    camera_filled(camera)

    except Exception as ex:
        logger.error(f"discovery error: {ex}")
        logger.debug(traceback.format_exc())
