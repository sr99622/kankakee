from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Tree, Input, RichLog
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical
from textual.timer import Timer
from textual import events
from dataclasses import is_dataclass, fields
from rich.text import Text
from utils.xml import get_xml_value
from fields import UNUSED_FIELDS, HIDDEN_FIELDS, field_descriptions, resolve_fqn_owner, \
        convert_string_value, join_fqn, is_editable_field, normalize_fqn, ptz_screen
from devices.camera import Camera, discover, set_network_default_gateway, set_hostname_from_dhcp, \
        set_hostname, set_dns, set_ntp, set_network_interfaces, reboot, set_imaging_settings, \
        set_audio_encoder_configuration, set_video_encoder_configuration, subscribe_events, \
        unsubscribe, get_status, continuous_move, move_stop, get_presets, set_preset, \
        remove_preset, goto_preset, operate_preset_tour, remove_preset_tour, create_preset_tour, \
        get_preset_tours, parse_get_preset_tours_response, modify_preset_tour, pull_messages
from datastructures.event import SubscriptionReference, parse_pull_messages_response
from datastructures.ptz import TourSpot
from server import Server, Handler, PORT
from datastructures.ptz import PTZPreset, parse_get_presets_response
from functools import partial, wraps
import traceback
from datetime import datetime, timezone, timedelta
import argparse
import psutil
import socket
import ipaddress
from urllib.parse import unquote_plus, urlparse
from camera_tree import CameraTree
import re
from utils.soap import onvif_post

RESUBSCRIBE_MARGIN_SECONDS = 10

class ObjectBrowser(App):

    def __init__(self, ip_address: str) -> None:
        super().__init__()
        self.ip_address = ip_address

    BINDINGS = [
        ("q", "quit", "Quit"),
        Binding("f2", "edit_selected", "Edit"),
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

    def on_key(self, event: events.Key) -> None:
        node = self.camera_tree.cursor_node
        if not node.data: return
        if not (camera := node.data.get("camera")): return
        profile_token = camera.profiles[0].token
        if not (fqn := node.data.get("fqn")): return

        if fqn == "capabilities.ptz.tours":
            match event.key:
                case 'n':
                    xml = create_preset_tour(camera, profile_token)
                    preset_tour_token = get_xml_value(xml, ".//tptz:CreatePresetTourResponse/tptz:PresetTourToken")
                    body = f"""<tptz:GetPresetTours><tptz:ProfileToken>{profile_token}</tptz:ProfileToken></tptz:GetPresetTours>"""
                    xml = onvif_post(camera.capabilities.ptz.xaddr, body, camera.username, camera.password, camera.time_offset)
                    preset_tours = parse_get_preset_tours_response(xml)
                    for preset_tour in preset_tours:
                        if preset_tour_token == preset_tour.token:
                            camera.capabilities.ptz.tours.append(preset_tour)
                            length = len(camera.capabilities.ptz.tours)
                            self.camera_tree._add_value(node, f"[{length-1}]", preset_tour, camera)
                            node.set_label(f"tours [{length}]")
                            self.camera_tree.refresh()
                            break
        if match := re.fullmatch(r"capabilities\.ptz\.tours\.\[(\d+)\]\.spots\.\[(\d+)\]", fqn):
            tour_index = int(match[1])
            spot_index = int(match[2])
            match event.key:
                case 'd':
                    parent = node.parent
                    self.camera_tree.move_cursor(parent)
                    node.remove()
                    del camera.capabilities.ptz.tours[tour_index].spots[spot_index]
                    length = len(camera.capabilities.ptz.tours[tour_index].spots)
                    if length == 1:
                        parent.allow_expand = False
                    parent.set_label(f"spots: [{length}]")
                    grand_parent = parent.parent
                    grand_parent.set_label(f"[{tour_index}] (* modified)")
                    for i, child in enumerate(parent.children):
                        child.set_label(f"[{i}]")
                        child.data["fqn"] = f"capabilities.ptz.tours.[{tour_index}].spots.[{i}]"

        if match := re.fullmatch(r"capabilities\.ptz\.tours\.\[(\d+)\]\.spots", fqn):
            tour_index = int(match[1])
            preset_tour_token = camera.capabilities.ptz.tours[tour_index].token
            match event.key:
                case 'n':
                    tour_spot = TourSpot("1", "PT25S")
                    camera.capabilities.ptz.tours[tour_index].spots.append(tour_spot)
                    length = len(camera.capabilities.ptz.tours[tour_index].spots)
                    node.allow_expand = True
                    self.camera_tree._add_value(node, f"[{length-1}]", tour_spot, camera)
                    node.set_label(f"spots: [{length}]")
                    node.parent.set_label(f"[{tour_index}] (* modified)")
                    self.camera_tree.refresh()

        if match := re.fullmatch(r"capabilities\.ptz\.tours\.\[(\d+)\]", fqn):
            tour_index = int(match[1])
            preset_tour_token = camera.capabilities.ptz.tours[tour_index].token
            match event.key:
                case 's':
                    operate_preset_tour(camera, profile_token, preset_tour_token, 'Start')
                case 't':
                    operate_preset_tour(camera, profile_token, preset_tour_token, 'Stop')
                case 'd':
                    remove_preset_tour(camera, profile_token, preset_tour_token)
                    parent = node.parent
                    self.camera_tree.move_cursor(parent)
                    node.remove()
                    del camera.capabilities.ptz.tours[tour_index]
                    new_count = len(camera.capabilities.ptz.tours)
                    parent.set_label(f"tours: [{new_count}]")
                    self.camera_tree.refresh()
                case 'w':
                    if node.label.plain.endswith("(* modified)"):
                        print(modify_preset_tour(camera, profile_token, tour_index))
                        node.set_label(f"[{tour_index}]")

        if fqn == "capabilities.ptz.xaddr":
            self.app.debug_log.clear()
            self.app.debug_log.write(ptz_screen)
            self.is_zoom_move = False
            match event.key:
                case 'w':
                    self.app.debug_log.write(f"\nmoving up...")
                    xml = continuous_move(camera, profile_token, 0, 0.5, 0)
                    #print(xml)
                case 's':
                    self.app.debug_log.write(f"\nmoving down...")
                    xml = continuous_move(camera, profile_token, 0, -0.5, 0)
                    #print(xml)
                case 'a':
                    self.app.debug_log.write(f"\npanning right...")
                    xml = continuous_move(camera, profile_token, 0.5, 0, 0)
                    #print(xml)
                case 'd':
                    self.app.debug_log.write(f"\npanning left...")
                    xml = continuous_move(camera, profile_token, -0.5, 0, 0)
                    #print(xml)
                case 'z':
                    self.app.debug_log.write(f"\nzooming in...")
                    xml = continuous_move(camera, profile_token, 0, 0, 0.5)
                    self.is_zoom_move = True 
                    #print(xml)
                case 'x':
                    self.app.debug_log.write(f"\nzooming out...")
                    xml = continuous_move(camera, profile_token, 0, 0, -0.5)
                    self.is_zoom_move = True
                    #print(xml)
                case 'c':
                    self.app.debug_log.write(f"\nstop move")
                    xml = move_stop(camera, profile_token, self.is_zoom_move)
                    #print(xml)
                case 'i':
                    self.app.debug_log.write(f"\ninformation\n")
                    xml = get_status(camera, profile_token)
                    pan_x = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:Position/tt:PanTilt/@x")
                    pan_y = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:Position/tt:PanTilt/@y")
                    zoom_x = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:Position/tt:Zoom/@x")
                    pan_tilt_status = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:MoveStatus/tt:PanTilt")
                    zoom_status = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:MoveStatus/tt:Zoom")
                    self.app.debug_log.write(f"X:    {pan_x}\nY:    {pan_y}\nZOOM: {zoom_x}\nPAN TILT STATUS: {pan_tilt_status}\nZOOM STATUS: {zoom_status}")

        if fqn == "capabilities.ptz.presets":
            match event.key:
                case 'n':
                    try:
                        xml = set_preset(camera, profile_token)
                        token = get_xml_value(xml, ".//tptz:SetPresetResponse/tptz:PresetToken")
                        body = f"""<tptz:GetPresets><tptz:ProfileToken>{profile_token}</tptz:ProfileToken></tptz:GetPresets>"""
                        xml = onvif_post(camera.capabilities.ptz.xaddr, body, camera.username, camera.password, camera.time_offset)
                        presets = parse_get_presets_response(xml)
                        for preset in presets:
                            if token == preset.token:
                                camera.capabilities.ptz.presets.append(preset)
                                length = len(camera.capabilities.ptz.presets)
                                self.camera_tree._add_value(node, f"[{length-1}]", preset, camera)
                                node.set_label(f"presets: [{length}]")
                                self.camera_tree.refresh()
                                break
                    except Exception as ex:
                        print(f"ADD PRESET ERROR: {ex}")

        if match := re.fullmatch(r"capabilities\.ptz\.presets\.\[(\d+)\]", fqn):
            index = int(match[1])
            preset_token = camera.capabilities.ptz.presets[index].token
            match event.key:
                case 'p':
                    print(set_preset(camera, profile_token, preset_token))
                case 'd':
                    print(remove_preset(camera, profile_token, preset_token))
                    if node := self.camera_tree.cursor_node:
                        parent = node.parent
                        self.camera_tree.move_cursor(parent)
                        node.remove()
                        new_count = len(camera.capabilities.ptz.presets)
                        parent.set_label(f"presets: [{new_count}]")
                        self.camera_tree.refresh()
                case 'g':
                    print(goto_preset(camera, profile_token, preset_token))

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

            elif fqn.startswith("capabilities.ptz.tours.[*].spots.[*]"):
                print("FOUND A TOUR SPOT EDIT")
                parent = self.editing_node.parent.parent.parent
                print(f"PARENT: {parent.label}")
                if data := parent.data:
                    print(data["fqn"])
                    if match := re.fullmatch(r"capabilities\.ptz\.tours\.\[(\d+)\]", data["fqn"]):
                        tour_index = int(match.group(1))
                        #preset_tour_token = camera.capabilities.ptz.tours[tour_index].token
                        parent.set_label(f"[{tour_index}] (* modified)")


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

    def on_mount(self) -> None:
        self.httpd = None
        self.run_worker(self.discover_worker, thread=True)
        print(f"self.httpd {self.httpd}")
        self.find_adapters()
        print(self.ips)
        print("object browser constructor")
        self.loop_callback = self.set_interval(5, self.main_loop)

    def on_unmount(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
        for child in self.camera_tree.root.children:
            print(f"camera: {child.label}")
            if not child.data:
                continue
            if camera := child.data.get("camera"):
                for reference in camera.subscription_references:
                    print(unsubscribe(camera, reference.xaddr))
                    #dt = datetime.fromisoformat(termination_time.replace("Z", "+00:00"))

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

    def main_loop(self) -> None:
        #...
        print("hello from the main loop")
        for child in self.camera_tree.root.children:
            if child.data and (camera := child.data.get("camera")):
                for reference in camera.subscription_references:
                    xml = pull_messages(camera, reference.xaddr)
                    print(f"OMG: {xml}")
                    if not (response := parse_pull_messages_response(xml)): continue
                    for notification in response.notifications:
                        print(notification.topic)
                        print(notification.message.utc_time)
                        print(notification.message.property_operation)
                        print(notification.message.source)
                        print(notification.message.data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-ip", "--ip_address", default="0.0.0.0", help="Local IP address binding for ONVIF discover/event callback")
    args = parser.parse_args()
    app = ObjectBrowser(args.ip_address)
    app.run() 
