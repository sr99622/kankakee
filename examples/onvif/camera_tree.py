from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Tree, Input, RichLog
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical
from textual.timer import Timer
from dataclasses import is_dataclass, fields
from rich.text import Text
from utils.xml import get_xml_value
from fields import UNUSED_FIELDS, HIDDEN_FIELDS, field_descriptions, resolve_fqn_owner, \
        convert_string_value, join_fqn, is_editable_field, normalize_fqn
from devices.camera import Camera, discover, set_network_default_gateway, set_hostname_from_dhcp, \
        set_hostname, set_dns, set_ntp, set_network_interfaces, reboot, set_imaging_settings, \
        set_audio_encoder_configuration, set_video_encoder_configuration, subscribe_events, \
        unsubscribe, create_pull_point_subscription
from datastructures.event import SubscriptionReference
from server import Server, Handler, PORT
from functools import partial, wraps
import traceback
from datetime import datetime, timezone, timedelta
import argparse
import psutil
import socket
import ipaddress
from urllib.parse import unquote_plus, urlparse
import re

RESUBSCRIBE_MARGIN_SECONDS = 10

class ConfirmRebootScreen(ModalScreen[bool]):
    def __init__(self, camera_name: str) -> None:
        super().__init__()
        self.camera_name = camera_name

    def compose(self):
        with Vertical(id="confirm_dialog"):
            yield Label(f"Reboot camera '{self.camera_name}'?")
            yield Button("Cancel", id="cancel", variant="primary")
            yield Button("Reboot", id="reboot", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "reboot")


class CameraTree(Tree):
    def __init__(self) -> None:
        super().__init__("Cameras")
        self.show_root = True

    BINDINGS = [
        ("]", "toggle_recursive", "Branch"),
        ("r", "reboot", "Reboot"),
        ("v", "event", "Event"),
        ("u", "pull", "Pull"),
    ]


    def action_event(self) -> None:
        if node := self.cursor_node:
            if node.parent.label.plain.startswith("topic_set:"):
                camera = node.data["camera"]
                event = node.label.plain.split(":")[1].strip()
                if node.label.plain.startswith(" * "):
                    print("--------------------unsubscribe", flush=True)
                    if reference := self.app.get_reference_for_event(camera):
                        reference.resubscribe_timer.stop()
                        self.app.debug_log.write(reference.xaddr)
                        self.app.debug_log.write(unsubscribe(camera, reference.xaddr))
                        camera.subscription_references.remove(reference)
                        if not len(camera.subscription_references) and self.app.httpd:
                            self.app.httpd.shutdown()
                            self.app.httpd = None
                    else:
                        print("Here we go again")
                    label = node.label.plain[3:]
                else:
                    self.app.resubscribe_event(camera, event)
                    label = f" * {node.label}"
                node.set_label(label)

    def action_pull(self) -> None:
        print("ACTION PULL")
        if not (node := self.cursor_node): return
        if not node.data: return
        if not (camera := node.data.get("camera")): return
        print(f"service: {camera.capabilities.events.xaddr}")
        event = node.label.plain.split(":")[1].strip()
        if node.label.plain.startswith(" * "):
            print("unsubscribe", flush=True)
            node.set_label(node.label.plain[3:])
            for reference in camera.subscription_references:
                print(reference, flush=True)
                print(unsubscribe(camera, reference.xaddr), flush=True)
                camera.subscription_references.remove(reference)
        else:
            print("subscribe", flush=True)
            xml = create_pull_point_subscription(camera)
            print(xml)
            address = get_xml_value(xml,
                ".//tev:CreatePullPointSubscriptionResponse/"
                "tev:SubscriptionReference/"
                "wsa5:Address",
            )

            termination_time = get_xml_value(
                xml,
                ".//tev:CreatePullPointSubscriptionResponse/"
                "wsnt:TerminationTime",
            )

            print(address)
            print(termination_time)
            #xaddr = get_xml_value("//s:Body", xml)
            #print(f"XADDR: {xaddr}")
            camera.subscription_references.append(SubscriptionReference(xaddr=address, termination_time=termination_time))

            node.set_label(f" * {node.label}")

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
        if not event.node.data: return
        if not (fqn := event.node.data.get("fqn")): return

        sfqn = re.sub(r"\[\d+\]", "[*]", fqn)
        
        self.app.debug_log.clear()
        self.app.debug_log.write(fqn)
        if desc := field_descriptions.get(sfqn):
            self.app.debug_log.write(desc)
        #if fqn.startswith("capabilities.ptz.presets.["):
        #if re.fullmatch(r"capabilities\.ptz\.presets\.\[\d+\]", fqn):
        #    self.app.debug_log.write("To assign the current postion to this preset\nuse the 'p' key")


    def _make_editable_label(self, field: str, value: str) -> Text:
        label = Text()
        label.append("✎  ", style="#66cc66")
        label.append(f"{field}: ")
        label.append(str(value))
        return label

    def action_reboot(self) -> None:
        if node := self.cursor_node:
            if node.parent.parent is None:
                if not node.data:
                    self.app.debug_log.write(f"Error: missing node data for camera")
                    return

                camera = node.data["camera"]
                self.app.push_screen(
                    ConfirmRebootScreen(camera.name),
                    lambda confirmed: self._do_reboot(camera) if confirmed else None,
                )

            else:
                self.app.debug_log.write(f"Reboot action can only be performed when a camera node is selected")

    def _do_reboot(self, camera: Camera) -> None:
        try:
            xml = reboot(camera)
            msg = get_xml_value(xml, "//s:Body//tds:SystemRebootResponse//tds:Message")
            self.app.debug_log.write(f"{camera.name}: {msg}")
        except Exception as ex:
            self.app.debug_log.write(f"{ex}")

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
        camera_node.data = { "camera": camera }
        for field in fields(camera):
            value = getattr(camera, field.name)
            self._add_value(camera_node, field.name, value, camera)
        if len(self.root.children) == 1:
            self.root.expand()

    def _add_value(self, parent: TreeNode, name: str, value: object, camera: Camera) -> None:

        fqn = join_fqn(self.get_fqn(parent), name)

        if fqn in HIDDEN_FIELDS:
            return

        if is_editable_field(fqn) and value is not None:
            node = parent.add_leaf(self._make_editable_label(name, str(value)))
            node.data = {"camera": camera, "field": name, "fqn": fqn}
            return

        if value is None:
            if fqn in UNUSED_FIELDS:
                return
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
                if fqn in UNUSED_FIELDS:
                    return
                label = Text(f"{name}: list[0]", style="dim")
                node = parent.add_leaf(label)
                node.data = {"camera": camera, "field": name, "fqn": fqn}
                return
            node = parent.add(f"{name}: [{len(value)}]", expand=False)
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


