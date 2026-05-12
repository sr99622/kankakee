from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Tree, Input, RichLog
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from devices.camera import Camera, discover, set_network_default_gateway, set_hostname_from_dhcp, \
        set_hostname, set_dns, set_ntp
from dataclasses import asdict, is_dataclass, fields
from rich.text import Text
from fields import field_descriptions, EDITABLE_FIELDS, resolve_fqn_owner, convert_string_value, \
        join_fqn, analyze_field_type
from typing import Any, get_args, get_origin, Union, Optional
import types
import ipaddress
import re

class CameraTree(Tree):
    def __init__(self) -> None:
        super().__init__("Cameras")
        self.show_root = True

    BINDINGS = [
        ("]", "toggle_recursive", "Open/close all"),
    ]


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

        fqn = join_fqn(self.get_fqn(parent), name)

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

    #edit_area {
        dock: bottom;
        height: 12;
        border: solid yellow;
    }

    .hidden {
        display: none;
    }
    """

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self.edit_input:
            return
        
        self.debug_log.write(f"ON INPUT SUBMITTED: {self.editing_node.data["fqn"]}")

        try:
            self.debug_log.write(f"editing field type: {self.editing_field_type}")

            base_type, is_optional, is_list = analyze_field_type(self.editing_field_type)
            if is_list:
                self.debug_log.write(f"list field, item type = {base_type}")
            else:
                self.debug_log.write(f"scalar field, type = {base_type}, optional = {is_optional}")

            old_value = getattr(self.editing_owner, self.editing_field)

            self.debug_log.write(f"OLD VALUE: {old_value}")

            self.debug_log.write(f"EVENT VALUE: {event.value.strip()}")
            self.debug_log.write(f"CONVERTED STRING VALUE: {convert_string_value(event.value.strip(), self.editing_field_type)}")

            setattr(self.editing_owner, self.editing_field, convert_string_value(event.value.strip(), self.editing_field_type))


            msg = "Updated successfully.\n"

            match self.editing_node.data["fqn"]:
                case "network_gateway":
                    if "RebootNeeded" in set_network_default_gateway(self.editing_camera):
                        msg += "Please reboot the camera to enact the update.\n"              
                case "hostname.from_dhcp":
                    if "RebootNeeded" in set_hostname_from_dhcp(self.editing_camera):
                        msg += "Please reboot the camera to enact the update\n"
                case "hostname.name":
                    set_hostname(self.editing_camera)
                case "dns.from_dhcp":
                    set_dns(self.editing_camera)
                case "dns.dns_manual":
                    set_dns(self.editing_camera)
                case "ntp.from_dhcp":
                    self.debug_log.write(set_ntp(self.editing_camera))
                case "ntp.ntp_manual":
                    self.debug_log.write(set_ntp(self.editing_camera))

            self.debug_log.write(msg)
        except Exception as ex:
            setattr(self.editing_owner, self.editing_field, old_value)
            self.debug_log.write(f"Update Failure:\n\n{ex}")

        self.editing_node.set_label(self.camera_tree._make_editable_label(self.editing_field, str(getattr(self.editing_owner, self.editing_field))))
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
        owner, field_name, field_type = resolve_fqn_owner(camera, fqn)
        self.debug_log.write(f"FIELD TYPE: {field_type}")

        self.editing_node = node
        self.editing_camera = camera
        self.editing_owner = owner
        self.editing_field = field_name
        self.editing_field_type = field_type
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