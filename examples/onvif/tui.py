from dataclasses import dataclass, asdict
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, ListView, ListItem, Label, Tree, Input, Log
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from devices.camera import Camera, discover, set_network_default_gateway
import json
from dataclasses import asdict, is_dataclass, fields
from rich.text import Text

EDITABLE_STYLE = "#66cc66"

class CameraTree(Tree):
    def __init__(self) -> None:
        super().__init__("Cameras")
        self.show_root = True

    BINDINGS = [
        ("]", "toggle_recursive", "Open/close all"),
    ]


    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        self.app.debug_log.write_line(f"TESTING: {event.node}")

    def _make_editable_label(self, field: str, value: str) -> Text:
        label = Text()
        label.append("✎  ", style="#66cc66")
        label.append(f"{field}: ")
        label.append(str(value))
        return label

    def action_toggle_recursive(self) -> None:
        node = self.cursor_node

        if node is None:
            return

        if node.is_expanded:
            self._collapse_recursive(node)
        else:
            self._expand_recursive(node)

    def _expand_recursive(self, node: TreeNode) -> None:
        node.expand()

        for child in node.children:
            self._expand_recursive(child)

    def _collapse_recursive(self, node: TreeNode) -> None:
        for child in node.children:
            self._collapse_recursive(child)

        node.collapse()        

    def add_camera(self, camera: Camera) -> None:
        #self.app.debug_log.write_line(f"camera found: {camera.name}")
        label = camera.name
        camera_node = self.root.add(label, expand=False)

        for field in fields(camera):
            value = getattr(camera, field.name)

            if field.name == "network_gateway":
                node = camera_node.add_leaf(self._make_editable_label(field.name, str(value)))
                node.data = {
                    "camera": camera,
                    "field": "network_gateway",
                }
            else:
                self._add_value(camera_node, field.name, value)

        if len(self.root.children) == 1:
            self.root.expand()

    def _add_value(self, parent, name: str, value: object) -> None:
        if value is None:
            parent.add_leaf(Text(f"{name}: None", style="dim"))
            return

        if is_dataclass(value):
            node = parent.add(name, expand=False)
            for field in fields(value):
                child_value = getattr(value, field.name)
                self._add_value(node, field.name, child_value)

        elif isinstance(value, list):
            if not value:
                # dim / grey text for empty lists
                label = Text(f"{name}: list[0]", style="dim")
                parent.add_leaf(label)
                return
            node = parent.add(f"{name}: list[{len(value)}]", expand=False)
            for index, item in enumerate(value):
                self._add_value(node, f"[{index}]", item)

        elif isinstance(value, dict):
            node = parent.add(f"{name}: dict[{len(value)}]", expand=False)
            for key, item in value.items():
                self._add_value(node, str(key), item)

        else:
            parent.add_leaf(f"{name}: {value}")

class ObjectBrowser(App):
    BINDINGS = [
        ("q", "quit", "Quit"),
        Binding("e", "edit_selected", "Edit"),
        Binding("escape", "cancel_edit", "Cancel edit"),
    ]

    CSS = """
    #main {
        height: 1fr;
    }

    CameraTree {
        width: 70%;
        height: 1fr;
        border: solid green;
        padding: 1 2;
    }

    #debug_log {
        width: 30%;
        height: 1fr;
        border: solid blue;
        padding: 1;
    }

    #edit_box {
        dock: bottom;
        height: 3;
        border: solid yellow;
        padding: 0 1;
    }

    .hidden {
        display: none;
    }
    """

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self.edit_input:
            return
        new_value = event.value.strip()
        self.editing_camera.network_gateway = new_value
        #self.editing_node.label = f"network_gateway: {new_value}"
        self.editing_node.set_label(self.camera_tree._make_editable_label("network_gateway", str(new_value)))
        self.edit_input.add_class("hidden")
        self.set_focus(self.camera_tree)

        # Later you can call your XML command here:
        # set_network_gateway(self.editing_camera, new_value)
        needs_reboot = set_network_default_gateway(self.editing_camera)
        if needs_reboot:
            print("NEEDS REBOOT")

    def action_cancel_edit(self) -> None:
        if self.edit_input.has_class("hidden"):
            return

        self.edit_input.add_class("hidden")
        self.set_focus(self.camera_tree)

    def action_edit_selected(self) -> None:
        node = self.camera_tree.cursor_node
        if node is None:
            return

        data = getattr(node, "data", None)
        if not data or data.get("field") != "network_gateway":
            return

        camera = data["camera"]
        self.editing_node = node
        self.editing_camera = camera
        self.editing_field = "network_gateway"
        self.edit_input.value = camera.network_gateway or ""
        self.edit_input.remove_class("hidden")
        self.set_focus(self.edit_input)

    def compose(self) -> ComposeResult:
        self.camera_tree = CameraTree()
        self.edit_input = Input(id="edit_box", placeholder="New value")
        self.edit_input.add_class("hidden")
        self.debug_log = Log(id="debug_log", highlight=True)

        yield Header()
        with Horizontal(id="main"):
            yield self.camera_tree
            yield self.debug_log
        yield self.edit_input
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self.discover_worker, thread=True)

    def discover_worker(self) -> None:
        def camera_filled(camera: Camera) -> None:
            self.call_from_thread(self.camera_tree.add_camera, camera)

        discover("10.1.1.76", camera_filled=camera_filled)

if __name__ == "__main__":
    app = ObjectBrowser()
    app.run()