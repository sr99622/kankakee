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
        #arguments = msg.split("\n\n")
        #timestamp = arguments.pop(0)
        #if timestamp == self.last_timestamp:
        #    return
        
        #self.last_timestamp = timestamp
        print(msg)
        #cmd = arguments.pop(0)
        #print(f"CALLBACK RETURN: {cmd}")
        #print(f"ALARM STATE: {arguments}")
        #print(f"LAST ALARM: {datetime.now()}")

class MainObject():
    def __init__(self):
        self.listener = None
        self.listenProtocols = ListenProtocols(self)
        self.start("0.0.0.0")

    def start(self, ip_addr):
        try:
            if not self.listener:
                self.listener = kankakee.Listener([ip_addr])
                self.listener.listenCallback = self.listenProtocols.callback
                self.listener.errorCallback = self.listenProtocols.error
            if not self.listener.running:
                self.listener.start()
                logger.debug("Alarm Listener was started successfully")
        except Exception as ex:
            logger.error(f'Error starting Alarm Listener : {ex}')
            logger.debug(traceback.format_exc())

if __name__ == "__main__":
    mo = MainObject()
    while True:
        sleep(100)
