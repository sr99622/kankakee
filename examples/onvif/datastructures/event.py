from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import xml.etree.ElementTree as ET
from utils.xml import int_attr, bool_attr, attr, text_list, bool_text, NS

WSTOP_NS = "http://docs.oasis-open.org/wsn/t-1"
WSTOP_TOPIC_ATTR = f"{{{WSTOP_NS}}}topic"

@dataclass
class ServiceCapabilities:
    ws_subscription_policy_support: Optional[bool] = None
    ws_pausable_subscription_manager_interface_support: Optional[bool] = None
    max_notification_producers: Optional[int] = None
    max_pull_points: Optional[int] = None
    persistent_notification_storage: Optional[bool] = None
    event_broker_protocols: Optional[str] = None
    max_event_brokers: Optional[int] = None
    metadata_over_mqtt: Optional[bool] = None

@dataclass
class TopicNamespaceLocation:
    uri: Optional[str] = None

@dataclass
class TopicSet:
    raw_xml: Optional[str] = None
    topics: list[str] = field(default_factory=list)

@dataclass
class EventProperties:
    topic_set: list[str] = field(default_factory=list)
    topic_namespace_location: list[str] = field(default_factory=list)
    message_content_filter_dialect: list[str] = field(default_factory=list)
    message_content_schema_location: list[str] = field(default_factory=list)
    fixed_topic_set: Optional[bool] = None
    producer_properties_filter_dialect: list[str] = field(default_factory=list)
    topic_expression_dialect: list[str] = field(default_factory=list)

def parse_service_capabilities_response(xml: str) -> ServiceCapabilities:
    root = ET.fromstring(xml)

    elem = root.find(
        ".//tev:GetServiceCapabilitiesResponse/tev:Capabilities",
        NS,
    )
    if elem is None:
        raise ValueError(
            "Could not find tev:GetServiceCapabilitiesResponse/tev:Capabilities"
        )

    return ServiceCapabilities(
        ws_subscription_policy_support=bool_attr(
            elem, "WSSubscriptionPolicySupport"
        ),
        ws_pausable_subscription_manager_interface_support=bool_attr(
            elem, "WSPausableSubscriptionManagerInterfaceSupport"
        ),
        max_notification_producers=int_attr(
            elem, "MaxNotificationProducers"
        ),
        max_pull_points=int_attr(
            elem, "MaxPullPoints"
        ),
        persistent_notification_storage=bool_attr(
            elem, "PersistentNotificationStorage"
        ),
        event_broker_protocols=attr(
            elem, "EventBrokerProtocols"
        ),
        max_event_brokers=int_attr(
            elem, "MaxEventBrokers"
        ),
        metadata_over_mqtt=bool_attr(
            elem, "MetadataOverMQTT"
        ),
    )

def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag

def is_topic_node(elem: ET.Element) -> bool:
    return elem.attrib.get(WSTOP_TOPIC_ATTR) == "true"

def has_topic_child(elem: ET.Element) -> bool:
    for child in list(elem):
        if strip_ns(child.tag) == "MessageDescription":
            continue
        if is_topic_node(child):
            return True
        if has_topic_child(child):
            return True
    return False

def collect_topic_paths(elem: ET.Element, prefix: str = "") -> list[str]:
    topics: list[str] = []
    for child in list(elem):
        name = strip_ns(child.tag)
        if name == "MessageDescription":
            continue
        path = f"{prefix}/{name}" if prefix else name
        if is_topic_node(child) and not has_topic_child(child):
            topics.append(path)
        topics.extend(collect_topic_paths(child, path))
    return topics

def parse_topic_set(elem: Optional[ET.Element]) -> list[str]:
    if elem is None:
        return []
    return collect_topic_paths(elem)

def parse_event_properties_response(xml: str) -> EventProperties:
    root = ET.fromstring(xml)
    elem = root.find(
        ".//tev:GetEventPropertiesResponse",
        NS,
    )
    if elem is None:
        raise ValueError("Could not find tev:GetEventPropertiesResponse")

    return EventProperties(
        topic_namespace_location=text_list(
            elem,
            "tev:TopicNamespaceLocation",
        ),
        topic_set=parse_topic_set(
            elem.find("wstop:TopicSet", NS),
        ),
        message_content_filter_dialect=text_list(
            elem,
            "tev:MessageContentFilterDialect",
        ),
        message_content_schema_location=text_list(
            elem,
            "tev:MessageContentSchemaLocation",
        ),
        fixed_topic_set=bool_text(
            elem,
            "tev:FixedTopicSet",
        ),
        producer_properties_filter_dialect=text_list(
            elem,
            "tev:ProducerPropertiesFilterDialect",
        ),
        topic_expression_dialect=text_list(
            elem,
            "tev:TopicExpressionDialect",
        ),
    )