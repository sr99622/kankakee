from kankakee import Server
import numpy as np
import io
from loguru import logger
import traceback

class ServerProtocols():
    def __init__(self, mo):
        self.mw = mo

    def callback(self, msg):
        if msg == "QUIT":
            self.mo.server.stop()
        buffer = io.BytesIO()
        buffer.write(bytearray(msg, 'utf-8'))
        buffer.write(bytearray("\r\n", 'utf-8'))
        return np.frombuffer(buffer.getvalue(), dtype=np.uint8)
    
    def error(self, msg):
        logger.error(f"server protocol error: {msg}")

class MainObject():
    def __init__(self):
        super().__init__()
        try:
            self.server = None
            self.serverProtocols = ServerProtocols(self)
            self.server = Server("127.0.0.1", 8000)
            self.server.serverCallback = self.serverProtocols.callback
            self.server.errorCallback = self.serverProtocols.error
            self.server.start()
        except Exception as ex:
            logger.error(f'Error initializing Server : {ex}')
            logger.debug(traceback.format_exc())

if __name__ == "__main__":
    mo = MainObject()
    while True:
        ...
    