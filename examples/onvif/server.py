from utils.xml import text, NS
from lxml import etree
import http.server
import socketserver
import os
import signal
import sys
from pathlib import Path
from functools import partial

PORT = 8800

def my_func(arg: list[dict[str, str]]):
    for item in arg:
        print(item)

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

def simple_items(elem: etree._Element | None) -> dict[str, str]:
    if elem is None:
        return {}

    return {
        item.attrib.get("Name", ""): item.attrib.get("Value", "")
        for item in elem.findall("tt:SimpleItem", NS)
        if item.attrib.get("Name")
    }

def parse_notify(ip_address: str, xml: str) -> list[dict[str, str]]:
    root = etree.fromstring(xml.encode("utf-8"))
    output = []
    for msg in root.findall(".//wsnt:NotificationMessage", NS):
        topic = text(msg, "wsnt:Topic")
        topic = strip_topic_prefix(topic) if topic else None
        alarm = {"ip_address": ip_address, "topic": topic}
        message = msg.find("wsnt:Message/tt:Message", NS)
        if message is not None:
            alarm["utc_time"] = message.attrib.get("UtcTime")
            alarm["operation"] = message.attrib.get("PropertyOperation")
            alarm["source"] = simple_items(message.find("tt:Source", NS))
            alarm["data"] = simple_items(message.find("tt:Data", NS)) 
            output.append(alarm)
    return output

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    disable_nagle_algorithm = True

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, my_arg=None, **kwargs):
        self.my_arg = my_arg
        super().__init__(*args, **kwargs)

    def do_POST(self):
        print("DO POST")
        if self.path == "/onvif/events":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            xml = body.decode("utf-8")
            alarms = parse_notify(self.client_address[0], xml)
            self.my_arg(alarms) if self.my_arg else ...
            self.send_response(200)
            self.end_headers()

if __name__ == "__main__":
    try:
        handler = partial(Handler, my_arg=my_func)
        with Server(("", PORT), handler) as httpd:
            httpd.serve_forever()
    except Exception as ex:
        print(f"HTTP SERVER ERROR: {ex}")
