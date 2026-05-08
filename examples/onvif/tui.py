from dataclasses import dataclass, asdict
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Header, Footer, ListView, ListItem, Label, Static
from devices.camera import Camera, discover
import json
from dataclasses import asdict, is_dataclass
from textual.widgets import TextArea

'''
class DetailPanel(Static):
    def show_object(self, obj: object) -> None:
        data = asdict(obj)

        text = ""
        for key, value in data.items():
            text += f"{key}: {value}\n"

        self.update(text)
'''

class DetailPanel(TextArea):
    def __init__(self) -> None:
        super().__init__(
            text="Select a camera",
            read_only=True,
            language="json",
        )

    def show_object(self, obj: object) -> None:
        if is_dataclass(obj):
            data = asdict(obj)
        else:
            data = obj

        text = json.dumps(
            data,
            indent=2,
            default=str,
        )

        self.text = text
        self.cursor_location = (0, 0)


class ObjectBrowser(App):
    CSS = """
    Horizontal {
        height: 1fr;
    }

    ListView {
        width: 35%;
        border: solid green;
    }

    DetailPanel {
        width: 65%;
        border: solid blue;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        self.objects = []

        yield Header()

        with Horizontal():
            self.list_view = ListView()
            #self.detail_panel = DetailPanel("Discovering cameras...")
            self.detail_panel = DetailPanel()
            self.detail_panel.text = "Discovering cameras..."

            yield self.list_view
            yield self.detail_panel

        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self.discover_worker, thread=True)

    def discover_worker(self) -> None:
        def camera_filled(camera: Camera) -> None:
            self.call_from_thread(self.add_camera, camera)

        discover("10.1.1.76", camera_filled=camera_filled)

    def get_camera_ip(self, camera: Camera) -> str:
        ip = ""
        for interface in camera.network_interfaces:
            if interface.ipv4.dhcp:
                ip = interface.ipv4.from_dhcp.address
            else:
                for manual in interface.ipv4.manual:
                    ip += manual.address + " "
        return ip.strip()

    def add_camera(self, camera: Camera) -> None:
        self.objects.append(camera)

        self.list_view.append(
            ListItem(Label(f"{camera.name}  ({self.get_camera_ip(camera)})"))
        )

        if len(self.objects) == 1:
            self.list_view.index = 0
            self.detail_panel.show_object(camera)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        index = event.list_view.index

        if index is not None and index < len(self.objects):
            self.detail_panel.show_object(self.objects[index])


if __name__ == "__main__":
    app = ObjectBrowser()
    app.run()