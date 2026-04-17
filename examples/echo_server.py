import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
from kankakee import Server, Client
import numpy as np
import io

class ServerProtocols():
    def __init__(self, parent):
        self.parent = parent

    def callback(self, msg):
        if msg == "QUIT":
            self.parent.server.stop()
        buffer = io.BytesIO()
        buffer.write(bytearray(msg))
        return np.frombuffer(buffer.getvalue(), dtype=np.uint8)
    
    def error(self, msg):
        logger.error(f"server protocol error: {msg}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server = None

        self.setWindowTitle("Minimal PyQt6 App")
        self.setGeometry(100, 100, 300, 200)

        button = QPushButton("test", self)
        button.clicked.connect(self.btnClicked)
        button.setGeometry(100, 80, 100, 40)

    def btnClicked(self):
        print("BUTTON CLICKED")
        if self.server:
            self.server.stop()
        else:
            self.server = Server("127.0.0.1", 8000)
            self.server.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())