import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, \
    QGridLayout, QWidget
from PyQt6.QtCore import Qt
from kankakee import Server, Client
import numpy as np
import io
from loguru import logger
import traceback

class ServerProtocols():
    def __init__(self, mw):
        self.mw = mw

    def callback(self, msg):
        if msg == "QUIT":
            self.mw.server.stop()
        buffer = io.BytesIO()
        buffer.write(bytearray(msg, 'utf-8'))
        buffer.write(bytearray("\r\n", 'utf-8'))
        return np.frombuffer(buffer.getvalue(), dtype=np.uint8)
    
    def error(self, msg):
        logger.error(f"server protocol error: {msg}")
        logger.debug(traceback.format_exc())

class ClientProtocols():
    def __init__(self, mw):
        self.mw = mw
        
    def callback(self, arg):
        try:
            index = bytearray(arg).find(b'\r\n')
            msg = bytearray(arg[:index]).decode('utf-8')
            configs = msg.split("\n\n")
            for config in configs:
                print(f"from client callback {config}")

        except Exception as ex:
            logger.error("EXCEPTION ", ex)
            return

    def error(self, msg):
        logger.error(f'Client protocol error: {msg}')
        logger.debug(traceback.format_exc())

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server = None
        self.serverProtocols = ServerProtocols(self)
        self.client = None
        self.clientProtocols = ClientProtocols(self)

        self.setWindowTitle("Minimal PyQt6 App")
        self.setGeometry(100, 100, 300, 200)

        panel = QWidget()
        layout = QGridLayout(panel)

        btnServer = QPushButton("server", self)
        btnServer.clicked.connect(self.btnServerClicked)
        btnClient = QPushButton("client", self)
        btnClient.clicked.connect(self.btnClientClicked)
        layout.addWidget(btnServer, 0, 0, 1, 1, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(btnClient, 1, 0, 1, 1, Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(panel)

    def btnServerClicked(self):
        if self.server:
            self.server.stop()
            self.server = None
        else:
            self.server = Server("127.0.0.1", 8000)
            self.server.serverCallback = self.serverProtocols.callback
            self.server.errorCallback = self.serverProtocols.error
            self.server.start()

    def btnClientClicked(self):
        try:
            if not self.client:
                self.client = Client("127.0.0.1", 8000)
                self.client.clientCallback = self.clientProtocols.callback
                self.client.errorCallback = self.clientProtocols.error
            msg = "THIS IS A TEST\r\n"
            self.client.transmit(bytearray(msg, 'utf-8'))
        except Exception as ex:
            logger.error(f'Error initializing Client : {ex}')
            logger.debug(traceback.format_exc())
        

    def initializeClient(self):
        try:
            self.client = Client("127.0.0.1", 8000)
            self.client.clientCallback = self.clientProtocols.callback
            self.client.errorCallback = self.clientProtocols.error
        except Exception as ex:
            logger.error(f'Error initializing Client : {ex}')
            logger.debug(traceback.format_exc())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())