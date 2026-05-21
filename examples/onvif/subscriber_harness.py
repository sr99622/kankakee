from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Static, Tree
from textual import work
from subscriber import Subscriber


class SubscriberHarness(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #form {
        height: auto;
        padding: 0 1;
        border: solid green;
    }

    #main {
        height: 1fr;
    }

    #topics {
        width: 1fr;
        border: solid blue;
    }

    #log {
        width: 1fr;
        border: solid yellow;
    }

    Input {
        height: 3;
        margin: 0;
    }

    Button {
        height: 3;
        min-height: 3;
        margin-top: 1;
    }
    """


    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="form"):
            yield Input(
                value="http://10.1.1.253/onvif/device_service",
                placeholder="Device service XAddr",
                id="xaddr",
            )
            yield Input(value="admin", placeholder="Username", id="username")
            yield Input(value="admin123", placeholder="Password", password=True, id="password")
            yield Button("Query Camera Events", id="query", variant="primary")

        with Horizontal(id="main"):
            yield Tree("Available Events", id="topics")
            yield RichLog(id="log", wrap=True)

        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "query":
            print("THIS IS A TEST")
            self.query_camera_events()

    def query_camera_events(self) -> None:
        xaddr = self.query_one("#xaddr", Input).value
        username = self.query_one("#username", Input).value
        password = self.query_one("#password", Input).value

        log = self.query_one("#log", RichLog)
        log.write(f"Querying camera: {xaddr}")

        self._query_worker(xaddr, username, password)

    @work(thread=True)
    def _query_worker(self, xaddr: str, username: str, password: str) -> None:
        log = self.query_one("#log", RichLog)
        tree = self.query_one("#topics", Tree)

        try:
            subscriber = Subscriber(
                xaddr=xaddr,
                username=username,
                password=password,
                name="test camera",
            )

            camera = subscriber.query()

            self.call_from_thread(log.write, "Camera query successful")
            self.call_from_thread(tree.root.remove_children)

            if not getattr(camera, "event_properties", None):
                self.call_from_thread(log.write, "No event_properties found on camera")
                return

            topic_set = getattr(camera.event_properties, "topic_set", None)

            if not topic_set:
                self.call_from_thread(log.write, "No topics found")
                return

            for topic in topic_set:
                self.call_from_thread(tree.root.add_leaf, str(topic))

            self.call_from_thread(tree.root.expand)
            self.call_from_thread(log.write, f"Loaded {len(topic_set)} event topics")

        except Exception as ex:
            self.call_from_thread(log.write, f"ERROR: {ex}")

if __name__ == "__main__":
    SubscriberHarness().run()