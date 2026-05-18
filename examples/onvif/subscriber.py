from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from devices.camera import get_camera, subscribe_events
from devices.camera import Camera
from server import parse_notify
from utils.xml import get_xml_value


RESUBSCRIBE_MARGIN_SECONDS = 10


@dataclass
class Subscription:
    xaddr: str
    event: str
    termination_time: str
    task: Optional[asyncio.Task] = None


class Subscriber:
    def __init__(
        self,
        xaddr: str,
        username: str,
        password: str,
        name: str = "camera",
        callback: Optional[Callable[[list[dict[str, str]]], None]] = None,
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

        self.camera: Optional[Camera] = None
        self.server: Optional[asyncio.AbstractServer] = None
        self.subscriptions: dict[str, Subscription] = {}

    def query(self) -> Camera:
        self.camera = get_camera(
            self.username,
            self.password,
            self.xaddr,
            self.name,
        )

        if self.camera is None:
            raise RuntimeError("get_camera() returned None")

        return self.camera

    async def start_server(self) -> None:
        if self.server is not None:
            return

        self.server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
        )

        addr = self.server.sockets[0].getsockname()
        print(f"SERVER LISTENING ON {addr}")

    async def stop_server(self) -> None:
        if self.server is None:
            return

        print("STOPPING SERVER")

        self.server.close()
        await self.server.wait_closed()

        self.server = None

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            header_text = headers.decode("utf-8", errors="ignore")

            request_line, *header_lines = header_text.split("\r\n")
            method, path, _version = request_line.split()

            parsed_headers: dict[str, str] = {}

            for line in header_lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    parsed_headers[key.strip().lower()] = value.strip()

            content_length = int(parsed_headers.get("content-length", 0))
            body = await reader.readexactly(content_length)

            xml = body.decode("utf-8", errors="ignore")

            peer = writer.get_extra_info("peername")
            ip_address = peer[0] if peer else ""

            events = parse_notify(ip_address, xml)

            if self.callback:
                self.callback(events)

            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Length: 0\r\n"
                "Connection: close\r\n"
                "\r\n"
            )

            writer.write(response.encode("ascii"))
            await writer.drain()

        except Exception as ex:
            print(f"SERVER ERROR: {ex}")

            response = (
                "HTTP/1.1 500 Internal Server Error\r\n"
                "Content-Length: 0\r\n"
                "Connection: close\r\n"
                "\r\n"
            )

            writer.write(response.encode("ascii"))
            await writer.drain()

        finally:
            writer.close()
            await writer.wait_closed()

    def subscribe(self, event: str) -> Subscription:
        if self.camera is None:
            raise RuntimeError("Call query() first")

        print(f"SUBSCRIBE START: {event}")

        xml = subscribe_events(self.camera, event)

        if xml is None:
            raise RuntimeError("subscribe_events returned None")

        subscription_reference = get_xml_value(
            xml,
            "//s:Body//wsnt:SubscribeResponse//wsnt:SubscriptionReference//wsa:Address",
        )

        termination_time = get_xml_value(
            xml,
            "//s:Body//wsnt:TerminationTime",
        )

        print(f"SUBSCRIBE SUCCESS: {event}")
        print(f"SUBSCRIPTION XADDR: {subscription_reference}")
        print(f"TERMINATION TIME: {termination_time}")

        subscription = Subscription(
            xaddr=subscription_reference,
            event=event,
            termination_time=termination_time,
        )

        task = asyncio.create_task(
            self.resubscribe_loop(subscription),
            name=f"resubscribe:{event}",
        )

        subscription.task = task
        self.subscriptions[event] = subscription

        return subscription

    async def resubscribe_loop(self, subscription: Subscription) -> None:
        while True:
            try:
                dt = datetime.fromisoformat(
                    subscription.termination_time.replace("Z", "+00:00")
                )

                delay = (
                    (dt - datetime.now(timezone.utc)).total_seconds()
                    - self.camera.time_offset
                    - RESUBSCRIBE_MARGIN_SECONDS
                )

                delay = max(1.0, delay)

                print()
                print(f"RESUBSCRIBE WAIT: {subscription.event}")
                print(f"CURRENT TIME: {datetime.now(timezone.utc)}")
                print(f"TERMINATION TIME: {dt}")
                print(f"CAMERA TIME OFFSET: {self.camera.time_offset}")
                print(f"DELAY: {delay}")
                print()

                await asyncio.sleep(delay)

                print(f"RESUBSCRIBE EXECUTE: {subscription.event}")

                xml = await asyncio.to_thread(
                    subscribe_events,
                    self.camera,
                    subscription.event,
                )

                if xml is None:
                    print("RESUBSCRIBE FAILED: subscribe_events returned None")
                    await asyncio.sleep(5)
                    continue

                subscription.xaddr = get_xml_value(
                    xml,
                    "//s:Body//wsnt:SubscribeResponse//wsnt:SubscriptionReference//wsa:Address",
                )

                subscription.termination_time = get_xml_value(
                    xml,
                    "//s:Body//wsnt:TerminationTime",
                )

                print(f"RESUBSCRIBE SUCCESS: {subscription.event}")
                print(f"NEW SUBSCRIPTION XADDR: {subscription.xaddr}")
                print(f"NEW TERMINATION TIME: {subscription.termination_time}")

            except asyncio.CancelledError:
                print(f"RESUBSCRIBE CANCELLED: {subscription.event}")
                raise

            except Exception as ex:
                print(f"RESUBSCRIBE ERROR: {subscription.event}")
                print(ex)
                await asyncio.sleep(5)


def my_func(events: list[dict[str, str]]) -> None:
    print("EVENTS RECEIVED")

    for event in events:
        print(event)


async def main() -> None:
    subscriber = Subscriber(
        xaddr="http://10.1.1.253/onvif/device_service",
        username="admin",
        password="admin123",
        callback=my_func,
    )

    camera = subscriber.query()

    print(f"CAMERA: {camera.name}")
    print(f"XADDR: {camera.xaddr}")
    print(f"TIME OFFSET: {camera.time_offset}")

    if camera.event_properties:
        print("AVAILABLE TOPICS:")
        for topic in camera.event_properties.topic_set:
            print(f"  {topic}")

    await subscriber.start_server()

    subscriber.subscribe("VideoSource/MotionAlarm")

    print("RUNNING. PRESS CTRL+C TO EXIT.")

    try:
        await asyncio.Event().wait()

    finally:
        for subscription in subscriber.subscriptions.values():
            if subscription.task:
                subscription.task.cancel()

        await subscriber.stop_server()


if __name__ == "__main__":
    asyncio.run(main())