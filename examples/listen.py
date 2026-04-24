from loguru import logger
import traceback
import kankakee
from time import sleep
from datetime import datetime

class ListenProtocols():
    def __init__(self, mo):
        self.mo = mo
        self.last_timestamp = ""

    def error(self, msg):
        if msg.find("WSACancelBlockingCall") < 0:
            logger.error(msg)

    def callback(self, msg):
        print(msg)

class MainObject():
    def __init__(self):
        try:
            self.listener = None
            self.listenProtocols = ListenProtocols(self)
            self.listener = kankakee.Listener('0.0.0.0', '239.255.255.247', 8080)
            self.listener.listenCallback = self.listenProtocols.callback
            self.listener.errorCallback = self.listenProtocols.error
            self.listener.start()
            logger.debug("Listener was started successfully")
        except Exception as ex:
            logger.error(f'Error starting Listener : {ex}')
            logger.debug(traceback.format_exc())

if __name__ == "__main__":
    mo = MainObject()
    while True:
        sleep(100)
