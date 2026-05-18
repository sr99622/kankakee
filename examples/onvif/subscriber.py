import asyncio
from devices.camera import get_camera
from server import parse_notify
from devices.camera import subscribe_events
from utils.xml import get_xml_value


class Subscriber:
    def __init__(
        self,
        xaddr: str,
        username: str,
        password: str,
        name: str = "camera",
        callback=None,
        host: str = "0.0.0.0",
        port: int = 8800,
    ) -> None:

        self.xaddr = xaddr
        self.username = username
        self.password = password
        self.name = name

        self.callback = callback

        self.host = host
        self.port = port

        self.camera = None
        self.server = None

    def query(self):
        self.camera = get_camera(
            self.username,
            self.password,
            self.xaddr,
            self.name,
        )

        return self.camera

    def subscribe(self, event: str):
        if self.camera is None:
            raise RuntimeError("Call query() before subscribe().")

        xml = subscribe_events(self.camera, event)

        if xml is None:
            raise RuntimeError("subscribe_events() returned None")

        subscription_reference = get_xml_value(
            xml,
            "//s:Body//wsnt:SubscribeResponse//wsnt:SubscriptionReference//wsa:Address",
        )

        termination_time = get_xml_value(
            xml,
            "//s:Body//wsnt:SubscribeResponse//wsnt:TerminationTime",
        )

        print(f"subscription_reference: {subscription_reference}")
        print(f"termination_time: {termination_time}")

        return subscription_reference, termination_time


    async def start_server(self):

        self.server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
        )

        addr = self.server.sockets[0].getsockname()

        print(f"SERVER LISTENING ON {addr}")

    async def stop_server(self):

        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):

        try:
            headers = await reader.readuntil(b"\r\n\r\n")

            header_text = headers.decode("utf-8", errors="ignore")

            request_line, *header_lines = header_text.split("\r\n")

            method, path, version = request_line.split()

            parsed_headers = {}

            for line in header_lines:
                if ":" in line:
                    k, v = line.split(":", 1)
                    parsed_headers[k.strip().lower()] = v.strip()

            content_length = int(
                parsed_headers.get("content-length", 0)
            )

            body = await reader.readexactly(content_length)

            xml = body.decode("utf-8", errors="ignore")

            peer = writer.get_extra_info("peername")

            ip_address = peer[0]

            events = parse_notify(ip_address, xml)

            if self.callback:
                self.callback(events)

            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Length: 0\r\n"
                "Connection: close\r\n"
                "\r\n"
            )

            writer.write(response.encode())

            await writer.drain()

        except Exception as ex:
            print(f"SERVER ERROR: {ex}")

        finally:
            writer.close()
            await writer.wait_closed()

async def main():

    subscriber = Subscriber(
        xaddr="http://10.1.1.78/onvif/device_service",
        username="admin",
        password="admin123",
        callback=my_func,
    )

    subscriber.query()

    await subscriber.start_server()

    subscriber.subscribe("VideoSource/MotionAlarm")

    print("PRESS CTRL+C TO EXIT")

    try:
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        print("SHUTTING DOWN")

    finally:
        await subscriber.stop_server()

def my_func(events):

    print("EVENTS RECEIVED")

    for event in events:
        print(event)


if __name__ == "__main__":
    asyncio.run(main())