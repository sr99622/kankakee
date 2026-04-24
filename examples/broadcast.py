import kankakee
from loguru import logger
import traceback
from datetime import datetime

class MainObject():
    def __init__(self):
        print("construct MainObject")
        try:
            self.broadcaster = kankakee.Broadcaster('0.0.0.0', '239.255.255.247', 8080)
            self.broadcaster.errorCallback = self.errorCallback
            self.broadcaster.enableLoopback(True)
        except Exception as ex:
            logger.error(f'Error initializing broadcaster {ex}')

    def errorCallback(self, msg):
        logger.error(msg)

if __name__ == "__main__":
    mo = MainObject()
    mo.broadcaster.send(f"HELLO FROM BROADCASTER: {datetime.now()}")
