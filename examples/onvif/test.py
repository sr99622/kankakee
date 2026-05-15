from loguru import logger
import traceback
from kankakee import NetUtil
from devices.camera import Camera, discover
import subprocess
import sys
import os
import requests
from time import sleep

http_process = None

def startHttpServer():
    try:
        #if not http_process:
        http_process = subprocess.Popen([sys.executable, f'{os.path.dirname(os.path.realpath(__file__))}/server.py'], env=os.environ.copy(), start_new_session=True)
        return_code = http_process.returncode
        logger.debug(f"starting http server from dir {os.path.dirname(os.path.realpath(__file__))}")
    except Exception as ex:
        logger.error(f'Error starting http server: {ex}')
        logger.debug(traceback.format_exc())

def stopHttpServer():
    try:
        requests.post("http://127.0.0.1:8800/shutdown", timeout=1)
    except Exception:
        pass

    if http_process:
        http_process.terminate()
        http_process.wait(timeout=5)
        http_process = None
        logger.debug("Http server stopped")


def camera_filled(camera: Camera) -> None:
    print(f"DATA FILLED FOR CAMERA {camera.name}")
    print()

if __name__ == "__main__":

    #logger.debug("HELLO WORLD")
    #startHttpServer()
    #while True:
    #    sleep(100)


    #'''
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
    #'''
