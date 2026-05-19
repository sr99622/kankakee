from loguru import logger
import traceback
from kankakee import NetUtil
from devices.camera import Camera, discover
import subprocess
import sys
import os
import requests
from time import sleep

def get_camera_credentials(camera: Camera) -> None:
    #print(f"GET CAMERA CREDENTIALS: {camera.xaddr}")
    if camera.name == "ANV-L7012R":
        camera.username = "admin"
        camera.password = "Admin123"
    else:
        camera.username = "admin"
        camera.password = "admin123"

def camera_filled(camera: Camera) -> None:
    print(f"DATA FILLED FOR CAMERA {camera.name}")
    print("*", camera.name)
    print("\n")

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

            cameras = discover(adapter.ip_address, get_camera_credentials, camera_filled=camera_filled)
            #for camera in cameras:
            #    camera_filled(camera)

    except Exception as ex:
        logger.error(f"discovery error: {ex}")
        logger.debug(traceback.format_exc())