from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Header, Footer, Input, RichLog
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from textual.timer import Timer
from textual import events
from utils.xml import get_xml_value
from fields import UNUSED_FIELDS, HIDDEN_FIELDS, field_descriptions, resolve_fqn_owner, \
        convert_string_value, is_editable_field, normalize_fqn, analyze_field_type
from devices.camera import Camera, discover, set_network_default_gateway, set_hostname_from_dhcp, \
        set_hostname, set_dns, set_ntp, set_network_interfaces, reboot, set_imaging_settings, \
        set_audio_encoder_configuration, set_video_encoder_configuration, \
        unsubscribe, get_status, continuous_move, move_stop, set_preset, \
        remove_preset, goto_preset, operate_preset_tour, remove_preset_tour, create_preset_tour, \
        parse_get_preset_tours_response, modify_preset_tour, pull_messages, \
        set_relay_output_settings, set_relay_output_state, subscribe_event, \
        get_local_date_and_time, set_system_date_and_time, create_pull_point_subscription, \
        get_time_offset, get_local_date_and_time_as_utc, start_multicast_streaming, \
        stop_multicast_streaming, find_camera_manually
from datastructures.event import SubscriptionReference, SubscriptionType, parse_pull_messages_response
from datastructures.ptz import TourSpot
from server import Server, Handler, PORT
from datastructures.ptz import parse_get_presets_response
from functools import partial
import traceback
from datetime import datetime, timezone
import argparse
import psutil
import socket
import ipaddress
from urllib.parse import urlparse
from camera_tree import CameraTree
import re
from utils.soap import onvif_post

RESUBSCRIBE_MARGIN_SECONDS = 10

class ObjectBrowser(App):

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.ip_address = args.ip_address
        self.manual = args.manual
        self.username = args.username
        self.password = args.password

        if self.manual:
            print(f"FOUND MANUAL ADDRESS: {self.manual}")

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

    def unsubscribe_events(self, camera: Camera):
        for reference in camera.subscription_references:
            if reference.resubscribe_timer: reference.resubscribe_timer.stop()
            unsubscribe(camera, reference.xaddr)
        camera.subscription_references.clear()

    def schedule_resubscribe_event(self, camera: Camera, event: str, delay: float) -> Timer:
        return self.set_timer(
            max(1.0, delay),
            lambda: self.run_worker(
                lambda: self.resubscribe_event(camera, event),
                thread=True,
            ),
        )
 
    def resubscribe_event(self, camera: Camera, event: str | None = None) -> None:
        try:
            if not self.httpd:
                print("starting http worker thread")
                self.run_worker(self.http_server_worker, thread=True)

            ip_obj = ipaddress.ip_address(urlparse(camera.xaddr).hostname)
            ip_address = self.ip_address
            if ip_address == "0.0.0.0":
                ip_address = self.find_local_subnet_matches(ip_obj)

            xml = subscribe_event(camera, ip_address, event)
            subscription_reference = get_xml_value(xml, "//s:Body//wsnt:SubscribeResponse//wsnt:SubscriptionReference//wsa:Address")
            termination_time = get_xml_value(xml, "//s:Body//wsnt:TerminationTime")
            dt = datetime.fromisoformat(termination_time.replace("Z", "+00:00"))
            delay = (dt - datetime.now(timezone.utc)).total_seconds() - camera.time_offset - RESUBSCRIBE_MARGIN_SECONDS

            if not (len(camera.subscription_references)):
                resubscribe_timer = self.schedule_resubscribe_event(camera, event, delay)
            else:
                resubscribe_timer = self.call_from_thread(self.schedule_resubscribe_event, camera, event, delay)

            reference = SubscriptionReference(
                xaddr=subscription_reference, 
                event=event, 
                subscription_type=SubscriptionType.PUSH,
                termination_time=termination_time,
                resubscribe_timer=resubscribe_timer
            )

            camera.subscription_references.append(reference)

        except Exception as ex:
            self.debug_log.write(f"resubscribe event error: {ex}\n{traceback.format_exc()}")

    def update_tree_time(self, camera: Camera, node: TreeNode) -> None:
        expanded = self.camera_tree.capture_expanded_nodes(node)
        node.remove_children()
        self.camera_tree._add_value(node, "date_time_type", camera.system_date_and_time.date_time_type, camera)
        self.camera_tree._add_value(node, "daylight_savings", camera.system_date_and_time.daylight_savings, camera)
        self.camera_tree._add_value(node, "time_zone", camera.system_date_and_time.time_zone, camera)
        self.camera_tree._add_value(node, "utc_date_time", camera.system_date_and_time.utc_date_time, camera)
        self.camera_tree._add_value(node, "local_date_time", camera.system_date_and_time.local_date_time, camera)
        self.camera_tree.restore_expanded_nodes(node, expanded)

    def show_system_date_and_time(self, camera: Camera) -> None:
        c = camera.system_date_and_time
        u = c.utc_date_time
        l = c.local_date_time

        local = ""
        if l:
            local = f"local date time: {l.date.year}-{l.date.month:02}-{l.date.day:02} {l.time.hour:02}:{l.time.minute:02}:{l.time.second:02}"

        time_str = f"""
Camera Time:

time zone: {c.time_zone.tz} 
daylight savings: {c.daylight_savings}
date time type: {c.date_time_type}
utc date time: {u.date.year}-{u.date.month:02}-{u.date.day:02} {u.time.hour:02}:{u.time.minute:02}:{u.time.second:02} 
{local} 
"""
        self.debug_log.write(time_str)

    def on_key(self, event: events.Key) -> None:
        node = self.camera_tree.cursor_node
        if not node.data: return
        if not (camera := node.data.get("camera")): return
        if not len(camera.profiles): return
        
        profile_token = camera.profiles[0].token

        if node.label.plain == camera.name and event.key == 'r':
            try:
                xml = reboot(camera)
                msg = get_xml_value(xml, "//s:Body//tds:SystemRebootResponse//tds:Message")
                self.app.debug_log.write(f"{camera.name}: {msg}")
            except Exception as ex:
                self.app.debug_log.write(f"{ex}")
            return

        if not (fqn := node.data.get("fqn")): return

        #print(f"FQN: {fqn}")
        try:
            if fqn == 'system_date_and_time':
                match event.key:
                    case 'u':
                        set_system_date_and_time(camera, get_local_date_and_time_as_utc())
                        get_time_offset(camera)
                        self.show_system_date_and_time(camera)
                        self.update_tree_time(camera, node)
                    case 't':
                        get_time_offset(camera)
                        self.show_system_date_and_time(camera)
                        self.update_tree_time(camera, node)
                    case 's':
                        self.debug_log.write("synchronizing camera time to computer time ...")
                        set_system_date_and_time(camera, get_local_date_and_time())
                        get_time_offset(camera)
                        self.show_system_date_and_time(camera)
                        self.update_tree_time(camera, node)
                    case 'w':
                        if node.label.plain.endswith("(* modified)"):
                            sdt = get_local_date_and_time()
                            sdt.date_time_type = camera.system_date_and_time.date_time_type
                            sdt.daylight_savings = camera.system_date_and_time.daylight_savings
                            sdt.time_zone.tz = camera.system_date_and_time.time_zone.tz
                            set_system_date_and_time(camera, sdt)
                            get_time_offset(camera)
                            self.show_system_date_and_time(camera)
                            self.update_tree_time(camera, node)
                            node.set_label("system_date_and_time")
                            self.debug_log.write("\nsystem_date_and_time has been updated successfully")

            if found := re.fullmatch(r"profiles\.\[(\d+)\]", fqn):
                index = int(found[1])
                profile_token = camera.profiles[index].token
                match event.key:
                    case 's':
                        start_multicast_streaming(camera, profile_token)
                        self.debug_log.write("Multicast streaming started")
                    case 't':
                        stop_multicast_streaming(camera, profile_token)
                        self.debug_log.write("Multicast streaming stopped")

            if found := re.fullmatch(r"capabilities\.events\.event_properties\.topic_set\.\[(\d+)\]", fqn):
                index = int(found[1])
                topic = camera.capabilities.events.event_properties.topic_set[index]
                match event.key:
                    case 'space' | 'enter':
                        if node.label.plain.startswith("*"):
                            node.set_label(f"[{index}]: {topic}")
                        else:
                            node.set_label(f"* [{index}]: {topic}")
                        node.parent.set_label(f"topic_set: [{len(camera.capabilities.events.event_properties.topic_set)}] (* modified)")

            if fqn == "capabilities.events.event_properties.topic_set": 
                match event.key:
                    case 'u':
                        self.unsubscribe_events(camera)
                        for i, child in enumerate(node.children):
                            topic = camera.capabilities.events.event_properties.topic_set[i]
                            child.set_label(f"[{i}]: {topic}")
                        node.set_label(f"topic_set: [{len(camera.capabilities.events.event_properties.topic_set)}]")
                    case 'R':
                        self.unsubscribe_events(camera)
                        self.resubscribe_event(camera)
                        node.set_label(f"topic_set: [{len(camera.capabilities.events.event_properties.topic_set)}] (receive ALL)")
                    case 'r':
                        if node.label.plain.endswith("(* modified)"):
                            self.unsubscribe_events(camera)
                            for i, child in enumerate(node.children):
                                if child.label.plain.startswith("*"):
                                    topic = camera.capabilities.events.event_properties.topic_set[i]
                                    self.resubscribe_event(camera, topic)
                            status = "" if not len(camera.subscription_references) else " (receive)"
                            node.set_label(f"topic_set: [{len(camera.capabilities.events.event_properties.topic_set)}]{status}")
                    case 'P':
                        self.unsubscribe_events(camera)
                        xml = create_pull_point_subscription(camera)
                        address = get_xml_value(xml, ".//tev:CreatePullPointSubscriptionResponse/tev:SubscriptionReference/wsa5:Address")
                        termination_time = get_xml_value(xml, ".//tev:CreatePullPointSubscriptionResponse/wsnt:TerminationTime")
                        reference = SubscriptionReference(
                            xaddr=address,
                            subscription_type=SubscriptionType.PULL,
                            termination_time=termination_time
                        )
                        camera.subscription_references.append(reference)
                        node.set_label(f"topic_set: [{len(camera.capabilities.events.event_properties.topic_set)}] (pull ALL)")
                    case 'p':
                        if node.label.plain.endswith("(* modified)"):
                            self.unsubscribe_events(camera)
                            for i, child in enumerate(node.children):
                                if child.label.plain.startswith("*"):
                                    topic = camera.capabilities.events.event_properties.topic_set[i]
                                    xml = create_pull_point_subscription(camera, topic)
                                    address = get_xml_value(xml, ".//tev:CreatePullPointSubscriptionResponse/tev:SubscriptionReference/wsa5:Address")
                                    termination_time = get_xml_value(xml, ".//tev:CreatePullPointSubscriptionResponse/wsnt:TerminationTime")
                                    reference = SubscriptionReference(
                                        xaddr=address,
                                        subscription_type=SubscriptionType.PULL,
                                        termination_time=termination_time
                                    )
                                    camera.subscription_references.append(reference)
                            status = "" if not len(camera.subscription_references) else " (pull)"
                            node.set_label(f"topic_set: [{len(camera.capabilities.events.event_properties.topic_set)}]{status}")

            if found := re.fullmatch(r"capabilities\.device_io\.relay_outputs\.\[(\d+)\]", fqn):  
                index = int(found[1])
                relay_output = camera.capabilities.device_io.relay_outputs[index]
                match event.key:
                    case 'w':
                        if node.label.plain.endswith("(* modified)"):
                            set_relay_output_settings(camera, relay_output)
                            node.set_label(f"[{index}]")
                    case 'a':
                        self.debug_log.write("RELAY ACTIVATE")
                        set_relay_output_state(camera, relay_output, "active")
                    case 'i':
                        self.debug_log.write("RELAY DEACTIVATE")
                        set_relay_output_state(camera, relay_output, "inactive")

            if fqn == "capabilities.ptz.presets":
                # add a new preset
                match event.key:
                    case 'n':
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

            if found := re.fullmatch(r"capabilities\.ptz\.presets\.\[(\d+)\]", fqn):
                # modify, delete or goto preset
                index = int(found[1])
                preset = camera.capabilities.ptz.presets[index]
                match event.key:
                    case 's':
                        set_preset(camera, profile_token, preset)
                    case 'd':
                        remove_preset(camera, profile_token, preset)
                        if node := self.camera_tree.cursor_node:
                            parent = node.parent
                            self.camera_tree.move_cursor(parent)
                            node.remove()
                            new_count = len(camera.capabilities.ptz.presets)
                            parent.set_label(f"presets: [{new_count}]")
                            self.camera_tree.refresh()
                    case 'g':
                        goto_preset(camera, profile_token, preset)
    
            if fqn == "capabilities.ptz.tours":
                # add a new tour
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

            if found := re.fullmatch(r"capabilities\.ptz\.tours\.\[(\d+)\]\.spots\.\[(\d+)\]", fqn):
                # delete a tour
                tour_index = int(found[1])
                spot_index = int(found[2])
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

            if found := re.fullmatch(r"capabilities\.ptz\.tours\.\[(\d+)\]\.spots", fqn):
                # add a new spot
                tour_index = int(found[1])
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

            if found := re.fullmatch(r"capabilities\.ptz\.tours\.\[(\d+)\]", fqn):
                # start, stop, delete or write to canera
                tour_index = int(found[1])
                preset_tour = camera.capabilities.ptz.tours[tour_index]
                match event.key:
                    case 's':
                        operate_preset_tour(camera, profile_token, preset_tour, 'Start')
                    case 't':
                        operate_preset_tour(camera, profile_token, preset_tour, 'Stop')
                    case 'd':
                        remove_preset_tour(camera, profile_token, preset_tour)
                        parent = node.parent
                        self.camera_tree.move_cursor(parent)
                        node.remove()
                        del camera.capabilities.ptz.tours[tour_index]
                        new_count = len(camera.capabilities.ptz.tours)
                        parent.set_label(f"tours: [{new_count}]")
                        self.camera_tree.refresh()
                    case 'w':
                        if node.label.plain.endswith("(* modified)"):
                            modify_preset_tour(camera, profile_token, preset_tour)
                            node.set_label(f"[{tour_index}]")

            if fqn == "capabilities.ptz.xaddr":
                self.is_zoom_move = False
                match event.key:
                    case 'w':
                        self.debug_log.write(f"\nmoving up...")
                        continuous_move(camera, profile_token, 0, 0.5, 0)
                    case 's':
                        self.debug_log.write(f"\nmoving down...")
                        continuous_move(camera, profile_token, 0, -0.5, 0)
                    case 'a':
                        self.debug_log.write(f"\npanning right...")
                        continuous_move(camera, profile_token, 0.5, 0, 0)
                    case 'd':
                        self.debug_log.write(f"\npanning left...")
                        continuous_move(camera, profile_token, -0.5, 0, 0)
                    case 'z':
                        self.debug_log.write(f"\nzooming in...")
                        continuous_move(camera, profile_token, 0, 0, 0.5)
                        self.is_zoom_move = True 
                    case 'x':
                        self.debug_log.write(f"\nzooming out...")
                        continuous_move(camera, profile_token, 0, 0, -0.5)
                        self.is_zoom_move = True
                    case 'c':
                        self.debug_log.write(f"\nstop move")
                        move_stop(camera, profile_token, self.is_zoom_move)
                    case 'i':
                        self.debug_log.write(f"\ninformation\n")
                        xml = get_status(camera, profile_token)
                        pan_x = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:Position/tt:PanTilt/@x")
                        pan_y = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:Position/tt:PanTilt/@y")
                        zoom_x = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:Position/tt:Zoom/@x")
                        pan_tilt_status = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:MoveStatus/tt:PanTilt")
                        zoom_status = get_xml_value(xml, ".//tptz:GetStatusResponse/tptz:PTZStatus/tt:MoveStatus/tt:Zoom")
                        self.debug_log.write(f"X:    {pan_x}\nY:    {pan_y}\nZOOM: {zoom_x}\nPAN TILT STATUS: {pan_tilt_status}\nZOOM STATUS: {zoom_status}")

        except Exception as ex:
            self.debug_log.write(f"exception editing field: {fqn} - {ex}")


    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self.edit_input:
            return

        try:
            old_value = getattr(self.editing_owner, self.editing_field)
            setattr(self.editing_owner, self.editing_field, convert_string_value(event.value.strip(), self.editing_field_type))

            msg = "\n"
            fqn = normalize_fqn(self.editing_node.data["fqn"])

            if fqn == "network_gateway":
                if "RebootNeeded" in set_network_default_gateway(self.editing_camera):
                    msg += "Updated successfully, please reboot the camera to enact the update\n"

            elif fqn == "hostname.from_dhcp":
                if "RebootNeeded" in set_hostname_from_dhcp(self.editing_camera):
                    msg += "Updated successfully, please reboot the camera to enact the update\n"

            elif fqn == "hostname.name":
                set_hostname(self.editing_camera)
                msg = "Updated successfully.\n"

            elif fqn.startswith("dns."):
                set_dns(self.editing_camera)
                msg = "Updated successfully.\n"

            elif fqn.startswith("ntp."):
                self.debug_log.write(set_ntp(self.editing_camera))
                msg = "Updated successfully.\n"

            elif fqn.startswith("network_interfaces.[*].ipv4"):
                index = self.editing_indicies[-1]
                interface = self.editing_camera.network_interfaces[index]
                manual = interface.ipv4.manual
                if "RebootNeeded" in set_network_interfaces(self.editing_camera, interface, manual):
                    msg += "Updated successfully, please reboot the camera to enact the update\n"

            elif fqn.startswith("profiles.[*].imaging_settings"):
                index = self.editing_indicies[0]
                profile = self.editing_camera.profiles[index]
                set_imaging_settings(self.editing_camera, profile.video_source.source_token, profile.imaging_settings)
                msg = "Updated successfully.\n"

            elif fqn.startswith("profiles.[*].audio_encoder"):
                index = self.editing_indicies[0]
                profile = self.editing_camera.profiles[index]
                set_audio_encoder_configuration(self.editing_camera, profile.audio_encoder)
                msg = "Updated successfully.\n"

            elif fqn.startswith("profiles.[*].video_encoder"):
                index = self.editing_indicies[0]
                profile = self.editing_camera.profiles[index]
                set_video_encoder_configuration(self.editing_camera, profile.video_encoder)
                msg = "Updated successfully.\n"

            elif fqn.startswith("capabilities.ptz.tours.[*].spots.[*]"):
                parent = self.editing_node.parent.parent.parent
                index = self.editing_indicies[0]
                parent.set_label(f"[{index}] (* modified)")
                msg = f"{fqn}\nhas been modified, navigate to\n{parent.label.plain}\nand use the 'w' key to commit the change"

            elif fqn.startswith("capabilities.ptz.tours.[*]"):
                parent = self.editing_node.parent
                index = self.editing_indicies[0]
                parent.set_label(f"[{index}] (* modified)")
                msg = f"{fqn}\nhas been modified, navigate to\n{parent.label.plain}\nand use the 'w' key to commit the change"

            elif fqn.startswith("capabilities.device_io.relay_outputs.[*].properties"):
                parent = self.editing_node.parent.parent
                index = self.editing_indicies[0]
                parent.set_label(f"[{index}] (* modified)")
                msg = f"{fqn}\nhas been modified, navigate to\n{parent.label.plain}\nand use the 'w' key to commit the change"

            elif fqn.startswith("system_date_and_time"):
                search_node = self.editing_node
                while search_node.parent.label.plain != "system_date_and_time" and search_node.parent.label.plain != "system_date_and_time (* modified)":
                    search_node = search_node.parent
                search_node.parent.set_label("system_date_and_time (* modified)")
                msg = f"{fqn}\nhas been modified, navigate to\nsystem_date_and_time (* modified)\nand use the 'w' key to commit the change"

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

        fqn = node.data["fqn"]

        if not is_editable_field(fqn): 
            return

        camera = node.data["camera"]
        owner, field_name, field_type, indices = resolve_fqn_owner(camera, fqn)
        base_type, is_optional, is_list = analyze_field_type(field_type)
        default_value = "False" if base_type is bool else ""

        self.editing_node = node
        self.editing_camera = camera
        self.editing_owner = owner
        self.editing_field = field_name
        self.editing_field_type = field_type
        self.editing_indicies = indices

        self.edit_input.value = str(getattr(owner, field_name) or default_value)
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

    def find_adapters(self) -> list[str]:
        ips = []
        VIRTUAL_KEYWORDS = {'docker', 'veth', 'vboxnet', 'vmware', 'virtual', 'wsl'}
        for interface, addrs in psutil.net_if_addrs().items():
            if any(keyword in interface.lower() for keyword in VIRTUAL_KEYWORDS):
                continue
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    if ipaddress.ip_address(addr.address).is_loopback or ipaddress.ip_address(addr.address).is_link_local:
                        continue
                    ips.append(addr.address)
        return ips

    def handle_camera_events(self, alarms: list[dict[str, str]]) -> None:
        for alarm in alarms:
            for key, value in alarm.items():
                self.debug_log.write(f"{key}: {value}")
            self.debug_log.write("\n")

    def on_camera_events_from_thread(self, alarms: list[dict[str, str]]) -> None:
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
        self.find_adapters()
        self.loop_callback = self.set_interval(5, self.main_loop)

    def on_unmount(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
        for child in self.camera_tree.root.children:
            if not child.data:
                continue
            if camera := child.data.get("camera"):
                for reference in camera.subscription_references:
                    unsubscribe(camera, reference.xaddr)

    def on_error(self, xaddr: str, ex: Exception) -> None:
        for child in self.camera_tree.root.children:
            if not child.data:
                continue
            if camera := child.data.get("camera"):
                if camera.xaddr == xaddr:
                    for grand_child in child.children:
                        if grand_child.label.plain.startswith("last_error"):
                            self.debug_log.write(f"Error with camera at {camera.name}: {ex}")
                            grand_child.set_label("last_error: ** Error")
                            self.camera_tree.refresh()
                            break

    def discover_worker(self) -> None:
        def camera_filled(camera: Camera) -> None:
            self.call_from_thread(self.camera_tree.add_camera, camera)

        def get_camera_credentials(camera: Camera) -> None:
            """
            if camera.name == "ANV-L7012R":
                camera.username = "admin"
                camera.password = "Admin123"
            else:
                camera.username = "admin"
                camera.password = "admin123"
            """
            camera.username = self.username
            camera.password = self.password

        try:
            if self.manual:
                find_camera_manually(self.manual, get_camera_credentials, on_error=self.on_error, camera_filled=camera_filled)
            else:
                ips = self.find_adapters()
                print(f"found adapters with ips: {ips}")
                discover(self.ip_address, get_camera_credentials, on_error=self.on_error, camera_filled=camera_filled)
        except Exception as ex:
            self.debug_log.write(f"Discovery error: {ex}")
            self.debug_log.write(traceback.format_exc())

    def main_loop(self) -> None:
        for child in self.camera_tree.root.children:
            if not child.data: return
            if not (camera := child.data.get("camera")): return
            for reference in camera.subscription_references:
                if reference.subscription_type == SubscriptionType.PULL:
                    xml = pull_messages(camera, reference.xaddr)
                    if not (response := parse_pull_messages_response(xml)): continue
                    for notification in response.notifications:
                        self.debug_log.write(notification)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--ip_address", default="0.0.0.0", help="Local IP address binding for ONVIF discover/event callback")
    parser.add_argument("-m", "--manual", default=None, help="Camera IP address for manual camera discovery")
    parser.add_argument("-u", "--username", default="", help="username for camera authentication")
    parser.add_argument("-p", "--password", default="", help="password for camera authentication")
    args = parser.parse_args()
    app = ObjectBrowser(args)
    app.run() 
