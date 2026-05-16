from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import xml.etree.ElementTree as ET
from utils.xml import int_attr, bool_attr, attr, text, bool_text, NS

import http.server
import socketserver
import os
import signal
import sys
from pathlib import Path
from functools import partial

PORT = 8800

def my_func():
    return "MY FUNC"

def getLocation():
    path = Path(os.path.dirname(__file__))
    return str(path.absolute())

def handle_sigterm(signum, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

def strip_topic_prefix(topic: str) -> str:
    if ":" in topic:
        return topic.split(":", 1)[1]
    return topic

def simple_items(elem: ET.Element | None) -> dict[str, str]:
    if elem is None:
        return {}

    return {
        item.attrib.get("Name", ""): item.attrib.get("Value", "")
        for item in elem.findall("tt:SimpleItem", NS)
        if item.attrib.get("Name")
    }

def parse_notify(xml: str) -> None:
    root = ET.fromstring(xml)
    for msg in root.findall(".//wsnt:NotificationMessage", NS):
        topic = text(msg, "wsnt:Topic")
        topic = strip_topic_prefix(topic) if topic else None

        message = msg.find("wsnt:Message/tt:Message", NS)

        print("topic:", topic)

        if message is not None:
            print("utc_time:", message.attrib.get("UtcTime"))
            print("operation:", message.attrib.get("PropertyOperation"))
            print("source:", simple_items(message.find("tt:Source", NS)))
            print("data:", simple_items(message.find("tt:Data", NS)))

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    disable_nagle_algorithm = True

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, my_arg=None, **kwargs):
        self.my_arg = my_arg
        super().__init__(*args, **kwargs, directory=getLocation())

    def do_POST(self):
        print(self.path)
        if self.path == "/onvif/events":
            print(f"my arg: {self.my_arg()}")
            print(self.path)
            content_length = int(
                self.headers.get("Content-Length", 0)
            )
            body = self.rfile.read(content_length)
            xml = body.decode("utf-8")
            #print(xml)
            parse_notify(xml)
            self.send_response(200)
            self.end_headers()
        else:
            super().do_POST()

if __name__ == "__main__":
    try:
        handler = partial(Handler, my_arg=my_func)
        with Server(("", PORT), handler) as httpd:
            httpd.serve_forever()
    except Exception as ex:
        print(f"HTTP SERVER ERROR: {ex}")
