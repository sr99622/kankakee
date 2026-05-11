from dataclasses import dataclass, asdict
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, ListView, ListItem, Label, Tree, Input, RichLog, Log
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from devices.camera import Camera, discover, set_network_default_gateway, set_hostname_from_dhcp, \
        set_hostname
import json
from dataclasses import asdict, is_dataclass, fields
from rich.text import Text
from fields import field_descriptions, EDITABLE_FIELDS

EDITABLE_STYLE = "#66cc66"

class CameraTree(Tree):
    def __init__(self) -> None:
        super().__init__("Cameras")
        self.show_root = True

    BINDINGS = [
        ("]", "toggle_recursive", "Open/close all"),
    ]

    def join_fqn(self, parent_fqn: str | None, field_name: str) -> str:
        if parent_fqn:
            return f"{parent_fqn}.{field_name}"
        return field_name

    def get_fqn(self, node: TreeNode) -> str:
        parts = []
        current = node
        while current is not None:
            parent = current.parent
            if parent is None:
                break
            data = getattr(current, "data", None)
            if data and "field" in data:
                parts.append(data["field"])
            current = parent
        return ".".join(reversed(parts))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        self.app.debug_log.clear()
        if event.node.data:
            if desc := field_descriptions.get(event.node.data["fqn"]):
                self.app.debug_log.write(desc)

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
        label = camera.name
        camera_node = self.root.add(label, expand=False)

        for field in fields(camera):
            value = getattr(camera, field.name)
            self._add_value(camera_node, field.name, value, camera)


        if len(self.root.children) == 1:
            self.root.expand()

    def _add_value(self, parent, name: str, value: object, camera: Camera) -> None:

        fqn = self.join_fqn(self.get_fqn(parent), name)

        if fqn in EDITABLE_FIELDS:
            node = parent.add_leaf(self._make_editable_label(name, str(value)))
            node.data = {"camera": camera, "field": name, "fqn": fqn}
            return

        if value is None:
            node = parent.add_leaf(Text(f"{name}: None", style="dim"))
            node.data = {"camera": camera, "field": name, "fqn": fqn}
            return

        if is_dataclass(value):
            node = parent.add(name, expand=False)
            node.data = {"camera": camera, "field": name, "fqn": fqn}
            for field in fields(value):
                child_value = getattr(value, field.name)
                self._add_value(node, field.name, child_value, camera)

        elif isinstance(value, list):
            if not value:
                # dim / grey text for empty lists
                label = Text(f"{name}: list[0]", style="dim")
                node = parent.add_leaf(label)
                node.data = {"camera": camera, "field": name, "fqn": fqn}
                return
            node = parent.add(f"{name}: list[{len(value)}]", expand=False)
            node.data = {"camera": camera, "field": name, "fqn": fqn}
            for index, item in enumerate(value):
                self._add_value(node, f"[{index}]", item, camera)

        elif isinstance(value, dict):
            node = parent.add(f"{name}: dict[{len(value)}]", expand=False)
            node.data = {"camera": camera, "field": name, "fqn": fqn}
            for key, item in value.items():
                self._add_value(node, str(key), item, camera)

        else:
            node = parent.add_leaf(f"{name}: {value}")
            node.data = {"camera": camera, "field": name, "fqn": fqn}

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
        width: 60%;
        height: 1fr;
        border: solid green;
        padding: 1 2;
    }

    #debug_log {
        width: 40%;
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

    def resolve_fqn_owner(self, root: object, fqn: str) -> tuple[object, str]:
        parts = fqn.split(".")
        owner = root

        for part in parts[:-1]:
            owner = getattr(owner, part)

        field_name = parts[-1]
        return owner, field_name
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self.edit_input:
            return
        
        self.debug_log.write(self.editing_node.data["fqn"])

        match self.editing_node.data["fqn"]:
            case "network_gateway":
                new_value = event.value.strip()
                old_value = self.editing_camera.network_gateway
                self.editing_camera.network_gateway = new_value

                try:
                    msg = "Updated successfully."
                    if "RebootNeeded" in set_network_default_gateway(self.editing_camera):
                        msg += " Please reboot the camera to enact the update.\n"              
                    self.debug_log.write(msg)
                except Exception as ex:
                    self.editing_camera.network_gateway = old_value
                    self.debug_log.write(ex)
                    #return
                self.editing_node.set_label(self.camera_tree._make_editable_label("network_gateway", str(self.editing_camera.network_gateway)))

            case "hostname.from_dhcp":
                new_value = event.value.strip()
                old_value = str(self.editing_camera.hostname.from_dhcp)
                self.editing_camera.hostname.from_dhcp = bool(new_value.lower() == "true")
                try:
                    msg = "Updated Successfully."
                    if "RebootNeeded" in set_hostname_from_dhcp(self.editing_camera):
                        msg += " Please reboot the camera to enact the update\n"
                    self.debug_log.write(msg)
                except Exception as ex:
                    self.editing_camera.hostname.from_dhcp = bool(old_value)
                    self.debug_log.write(ex)
                    #return
                self.editing_node.set_label(self.camera_tree._make_editable_label("from_dhcp", str(self.editing_camera.hostname.from_dhcp)))

            case "hostname.name":
                new_value = event.value.strip()
                old_value = str(self.editing_camera.hostname.name)
                self.editing_camera.hostname.name = new_value
                try:
                    set_hostname(self.editing_camera)
                    self.debug_log.write("Updated successfully.")
                except Exception as ex:
                    self.editing_camera.hostname.name = old_value
                    self.debug_log.write(ex)
                    #return
                self.editing_node.set_label(self.camera_tree._make_editable_label("name", str(self.editing_camera.hostname.name)))

        self.edit_input.add_class("hidden")
        self.set_focus(self.camera_tree)


    def action_cancel_edit(self) -> None:
        if self.edit_input.has_class("hidden"):
            return

        self.edit_input.add_class("hidden")
        self.set_focus(self.camera_tree)

    def action_edit_selected(self) -> None:

        node = self.camera_tree.cursor_node
        if node is None or not node.data:
            return

        self.debug_log.write(f"action edit selected: {node.data["fqn"]}")
        fqn = node.data["fqn"]
        camera = node.data["camera"]
        owner, field_name = self.resolve_fqn_owner(camera, fqn)

        self.editing_node = node
        self.editing_camera = camera
        self.editing_field = field_name
        self.edit_input.value = str(getattr(owner, field_name) or "")
        self.edit_input.remove_class("hidden")
        self.set_focus(self.edit_input)

    def compose(self) -> ComposeResult:
        self.camera_tree = CameraTree()
        self.edit_input = Input(id="edit_box", placeholder="New value")
        self.edit_input.add_class("hidden")
        self.debug_log = RichLog(id="debug_log", highlight=True, wrap=True)
        #self.debug_log = Log(id="debug_log", highlight=True)

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