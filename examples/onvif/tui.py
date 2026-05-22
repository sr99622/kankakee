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
        unsubscribe
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
        ("]", "toggle_recursive", "Open/close all"),
        ("r", "reboot", "Reboot Selected"),
        ("v", "event", "Event"),
    ]

    def get_reference_for_event(self, camera: Camera, event: str) -> SubscriptionReference:
        for reference in camera.subscription_references:
            if reference.event == event:
                return reference

    def schedule_resubscribe_event(self, camera: Camera, event: str, delay: float) -> Timer:
        return self.set_timer(
            max(1.0, delay),
            lambda: self.run_worker(
                lambda: self.resubscribe_event(camera, event),
                thread=True,
            ),
        )

    def find_local_subnet_matches(self, remote_target_ip: str) -> str:
        target = ipaddress.IPv4Address(remote_target_ip)

        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                # Look only for active IPv4 configurations with a valid netmask
                if addr.family == socket.AF_INET and addr.netmask:
                    try:
                        network = ipaddress.IPv4Interface(f"{addr.address}/{addr.netmask}").network
                        if target in network:
                            print(f"Match found! {remote_target_ip} is on the same subnet as interface '{interface}' ({addr.address})")
                            return addr.address
                    except ValueError:
                        continue

    def resubscribe_event(self, camera: Camera, event: str) -> None:
        try:
            print("resubscribe_event")
            if self.app.httpd:
                print("HAVE HTTPD")
            else:
                print("starting http worker thread")
                self.app.run_worker(self.app.http_server_worker, thread=True)

            if reference := self.get_reference_for_event(camera, event):
                camera.subscription_references.remove(reference)
                self.app.call_from_thread(self.app.debug_log.write, "RESUBSCRIBE EVENT")

            print(f"self.app.ip_address: {self.app.ip_address}")
            print(f"event under consideration: {event}")
            ip_obj = ipaddress.ip_address(urlparse(camera.xaddr).hostname)
            print(f"camera ip: {ip_obj}")
            ip_address = self.app.ip_address
            if ip_address == "0.0.0.0":
                ip_address = self.find_local_subnet_matches(ip_obj)
            print(f"event listener address: {ip_address}")

            xml = subscribe_events(camera, event, ip_address)
            print(xml, flush=True)
            subscription_reference = get_xml_value(xml, "//s:Body//wsnt:SubscribeResponse//wsnt:SubscriptionReference//wsa:Address")
            termination_time = get_xml_value(xml, "//s:Body//wsnt:TerminationTime")
            dt = datetime.fromisoformat(termination_time.replace("Z", "+00:00"))
            delay = (dt - datetime.now(timezone.utc)).total_seconds() - camera.time_offset - RESUBSCRIBE_MARGIN_SECONDS

            if reference is None:
                resubscribe_timer = self.schedule_resubscribe_event(camera, event, delay)
            else:
                resubscribe_timer = self.app.call_from_thread(self.schedule_resubscribe_event, camera, event, delay)

            reference = SubscriptionReference(
                xaddr=subscription_reference, 
                event=event, 
                termination_time=termination_time,
                resubscribe_timer=resubscribe_timer
            )

            camera.subscription_references.append(reference)
        except Exception as ex:
            #self.app.debug_log.write, f"resubscribe event errror: {ex}"
            #self.app.debug_log.write, traceback.format_exc()
            print(f"resubscribe event error: {ex}\n{traceback.format_exc()}")

    def action_event(self) -> None:
        if node := self.cursor_node:
            if node.parent.label.plain.startswith("topic_set:"):
                camera = node.data["camera"]
                event = node.label.plain.split(":")[1].strip()
                if node.label.plain.startswith(" * "):
                    print("unsubscribe", flush=True)
                    if reference := self.get_reference_for_event(camera, event):
                        print(f"found event: {event}")
                        reference.resubscribe_timer.stop()
                        self.app.debug_log.write(reference.xaddr)
                        self.app.debug_log.write(unsubscribe(camera, reference.xaddr))
                        camera.subscription_references.remove(reference)
                        print(f"subscription_references count: {len(camera.subscription_references)}")
                        if not len(camera.subscription_references) and self.app.httpd:
                            self.app.httpd.shutdown()
                            self.app.httpd = None
                    label = node.label.plain[3:]
                else:
                    self.resubscribe_event(camera, event)
                    label = f" * {node.label}"
                node.set_label(label)

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
        if event.node.data and event.node.data.get("fqn"):
            self.app.debug_log.write(event.node.data["fqn"])
            if desc := field_descriptions.get(event.node.data["fqn"]):
                self.app.debug_log.write(desc)

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

class ObjectBrowser(App):

    def __init__(self, ip_address: str) -> None:
        super().__init__()
        self.ip_address = ip_address

    BINDINGS = [
        ("q", "quit", "Quit"),
        Binding("e", "edit_selected", "Edit"),
        Binding("escape", "cancel_edit", "Cancel"),
    ]

    CSS = """
    #main {
        height: 1fr;
    }

    CameraTree {
        width: 50%;
        height: 1fr;
        border: solid green;
        padding: 1 2;
    }

    #debug_log {
        width: 50%;
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

    #confirm_dialog {
        width: 50;
        height: auto;
        border: solid red;
        padding: 1 2;
        background: $surface;
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

            #base_type, is_optional, is_list = analyze_field_type(self.editing_field_type)
            old_value = getattr(self.editing_owner, self.editing_field)
            setattr(self.editing_owner, self.editing_field, convert_string_value(event.value.strip(), self.editing_field_type))

            msg = "Updated successfully.\n"
            fqn = normalize_fqn(self.editing_node.data["fqn"])

            if fqn == "network_gateway":
                if "RebootNeeded" in set_network_default_gateway(self.editing_camera):
                    msg += "Please reboot the camera to enact the update.\n"

            elif fqn == "hostname.from_dhcp":
                if "RebootNeeded" in set_hostname_from_dhcp(self.editing_camera):
                    msg += "Please reboot the camera to enact the update\n"

            elif fqn == "hostname.name":
                set_hostname(self.editing_camera)

            elif fqn.startswith("dns."):
                set_dns(self.editing_camera)

            elif fqn.startswith("ntp."):
                self.debug_log.write(set_ntp(self.editing_camera))

            elif fqn.startswith("network_interfaces.[*].ipv4"):
                index = self.editing_indicies[-1]
                interface = self.editing_camera.network_interfaces[index]
                manual = interface.ipv4.manual
                if "RebootNeeded" in set_network_interfaces(self.editing_camera, interface, manual):
                    msg += "Please reboot the camera to enact the update\n"

            elif fqn.startswith("profiles.[*].imaging_settings"):
                index = self.editing_indicies[-1]
                profile = self.editing_camera.profiles[index]
                set_imaging_settings(self.editing_camera, profile.video_source.source_token, profile.imaging_settings)

            elif fqn.startswith("profiles.[*].audio_encoder"):
                index = self.editing_indicies[-1]
                profile = self.editing_camera.profiles[index]
                set_audio_encoder_configuration(self.editing_camera, profile.audio_encoder)

            elif fqn.startswith("profiles.[*].video_encoder"):
                index = self.editing_indicies[-1]
                profile = self.editing_camera.profiles[index]
                set_video_encoder_configuration(self.editing_camera, profile.video_encoder)

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
        owner, field_name, field_type, indices = resolve_fqn_owner(camera, fqn)
        self.debug_log.write(f"FIELD TYPE: {field_type}")

        self.editing_node = node
        self.editing_camera = camera
        self.editing_owner = owner
        self.editing_field = field_name
        self.editing_field_type = field_type
        self.editing_indicies = indices
        self.edit_input.value = str(getattr(owner, field_name) or "")
        self.edit_input.remove_class("hidden")
        self.set_focus(self.edit_input)

    def compose(self) -> ComposeResult:
        self.camera_tree = CameraTree()
        self.edit_input = Input(id="edit_box", placeholder="New value")
        self.edit_input.add_class("hidden")
        self.debug_log = RichLog(id="debug_log", highlight=True, wrap=True)

        yield Header()
        with Horizontal(id="main"):
            yield self.camera_tree
            yield self.debug_log
        yield self.edit_input
        yield Footer()

    def find_adapters(self) -> None:
        self.ips = []
        VIRTUAL_KEYWORDS = {'docker', 'veth', 'vboxnet', 'vmware', 'virtual', 'wsl'}
        for interface, addrs in psutil.net_if_addrs().items():
            if any(keyword in interface.lower() for keyword in VIRTUAL_KEYWORDS):
                continue
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    if ipaddress.ip_address(addr.address).is_loopback:
                        continue
                    self.ips.append(addr.address)

    def on_mount(self) -> None:
        self.httpd = None
        self.run_worker(self.discover_worker, thread=True)
        print(f"self.httpd {self.httpd}")
        #self.run_worker(self.http_server_worker, thread=True)
        self.find_adapters()
        print(self.ips)

    def handle_camera_events(self, alarms: list[dict[str, str]]) -> None:
        for alarm in alarms:
            self.debug_log.write(str(alarm))

    def on_camera_events_from_thread(self, alarms: list[dict[str, str]]) -> None:
        print(f"on_camera_events_from_thread: {alarms}")
        self.call_from_thread(self.handle_camera_events, alarms)

    def http_server_worker(self) -> None:
        print("http_server_worker starting", flush=True)
        try:
            handler = partial(Handler, my_arg=self.on_camera_events_from_thread)

            with Server((self.ip_address, PORT), handler) as httpd:
                print(f"http server worker start at {self.ip_address}:{PORT}, flush=True")
                self.httpd = httpd
                httpd.serve_forever()

        except Exception as ex:
            print(f"exception in server worker{ex}")
            self.call_from_thread(
                self.debug_log.write,
                f"HTTP SERVER ERROR: {ex}\n{traceback.format_exc()}",
            )

        finally:
            self.httpd = None

    def on_unmount(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()

    def discover_worker(self) -> None:
        def camera_filled(camera: Camera) -> None:
            self.call_from_thread(self.camera_tree.add_camera, camera)

        def get_camera_credentials(camera: Camera) -> None:
            if camera.name == "ANV-L7012R":
                camera.username = "admin"
                camera.password = "Admin123"
            else:
                camera.username = "admin"
                camera.password = "admin123"

        try:
            discover(self.ip_address, get_camera_credentials, camera_filled=camera_filled)
        except Exception as ex:
            self.debug_log.write(f"Discovery error: {ex}")
            self.debug_log.write(traceback.format_exc())

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-ip", "--ip_address", default="0.0.0.0", help="Local IP address binding for ONVIF discover/event callback")
    args = parser.parse_args()
    app = ObjectBrowser(args.ip_address)
    app.run() 
