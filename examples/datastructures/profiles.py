from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import xml.etree.ElementTree as ET


NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
}


def text(elem: ET.Element, path: str) -> Optional[str]:
    found = elem.find(path, NS)
    return found.text.strip() if found is not None and found.text else None


def bool_text(elem: ET.Element, path: str) -> Optional[bool]:
    value = text(elem, path)
    if value is None:
        return None
    return value.lower() == "true"


def int_text(elem: ET.Element, path: str) -> Optional[int]:
    value = text(elem, path)
    return int(value) if value is not None else None


def float_text(elem: ET.Element, path: str) -> Optional[float]:
    value = text(elem, path)
    return float(value) if value is not None else None


def attr(elem: ET.Element, name: str) -> Optional[str]:
    return elem.attrib.get(name)


def bool_attr(elem: ET.Element, name: str) -> Optional[bool]:
    value = attr(elem, name)
    if value is None:
        return None
    return value.lower() == "true"


@dataclass
class Bounds:
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class VideoSourceConfiguration:
    token: Optional[str] = None
    name: Optional[str] = None
    use_count: Optional[int] = None
    source_token: Optional[str] = None
    bounds: Bounds = field(default_factory=Bounds)


@dataclass
class Resolution:
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class RateControl:
    frame_rate_limit: Optional[int] = None
    encoding_interval: Optional[int] = None
    bitrate_limit: Optional[int] = None


@dataclass
class MulticastConfiguration:
    address_type: Optional[str] = None
    ipv4_address: Optional[str] = None
    ipv6_address: Optional[str] = None
    port: Optional[int] = None
    ttl: Optional[int] = None
    auto_start: Optional[bool] = None


@dataclass
class VideoEncoderConfiguration:
    token: Optional[str] = None
    name: Optional[str] = None
    use_count: Optional[int] = None
    encoding: Optional[str] = None
    resolution: Resolution = field(default_factory=Resolution)
    quality: Optional[float] = None
    rate_control: RateControl = field(default_factory=RateControl)
    multicast: MulticastConfiguration = field(default_factory=MulticastConfiguration)
    session_timeout: Optional[str] = None


@dataclass
class AudioSourceConfiguration:
    token: Optional[str] = None
    name: Optional[str] = None
    use_count: Optional[int] = None
    source_token: Optional[str] = None


@dataclass
class AudioEncoderConfiguration:
    token: Optional[str] = None
    name: Optional[str] = None
    use_count: Optional[int] = None
    encoding: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    multicast: MulticastConfiguration = field(default_factory=MulticastConfiguration)
    session_timeout: Optional[str] = None


@dataclass
class PTZConfiguration:
    token: Optional[str] = None
    name: Optional[str] = None
    use_count: Optional[int] = None
    node_token: Optional[str] = None
    default_absolute_pant_tilt_position_space: Optional[str] = None
    default_absolute_zoom_position_space: Optional[str] = None
    default_relative_pan_tilt_translation_space: Optional[str] = None
    default_relative_zoom_translation_space: Optional[str] = None
    default_continuous_pan_tilt_velocity_space: Optional[str] = None
    default_continuous_zoom_velocity_space: Optional[str] = None
    default_ptz_timeout: Optional[str] = None


@dataclass
class VideoAnalyticsConfiguration:
    token: Optional[str] = None
    name: Optional[str] = None
    use_count: Optional[int] = None


@dataclass
class MetadataConfiguration:
    token: Optional[str] = None
    name: Optional[str] = None
    use_count: Optional[int] = None
    ptz_status: Optional[bool] = None
    events: Optional[bool] = None
    multicast: MulticastConfiguration = field(default_factory=MulticastConfiguration)
    session_timeout: Optional[str] = None


@dataclass
class Profile:
    token: Optional[str] = None
    fixed: Optional[bool] = None
    name: Optional[str] = None

    video_source: Optional[VideoSourceConfiguration] = None
    video_encoder: Optional[VideoEncoderConfiguration] = None
    audio_source: Optional[AudioSourceConfiguration] = None
    audio_encoder: Optional[AudioEncoderConfiguration] = None
    ptz: Optional[PTZConfiguration] = None
    video_analytics: Optional[VideoAnalyticsConfiguration] = None
    metadata: Optional[MetadataConfiguration] = None


@dataclass
class GetProfilesResponse:
    profiles: list[Profile] = field(default_factory=list)


def parse_multicast(elem: Optional[ET.Element]) -> MulticastConfiguration:
    if elem is None:
        return MulticastConfiguration()

    return MulticastConfiguration(
        address_type=text(elem, "tt:Address/tt:Type"),
        ipv4_address=text(elem, "tt:Address/tt:IPv4Address"),
        ipv6_address=text(elem, "tt:Address/tt:IPv6Address"),
        port=int_text(elem, "tt:Port"),
        ttl=int_text(elem, "tt:TTL"),
        auto_start=bool_text(elem, "tt:AutoStart"),
    )


def parse_profiles_response(xml: str) -> GetProfilesResponse:
    root = ET.fromstring(xml)

    profile_elems = root.findall(".//trt:GetProfilesResponse/trt:Profiles", NS)
    if not profile_elems:
        raise ValueError("Could not find trt:GetProfilesResponse/trt:Profiles")

    response = GetProfilesResponse()

    for p in profile_elems:
        profile = Profile(
            token=attr(p, "token"),
            fixed=bool_attr(p, "fixed"),
            name=text(p, "tt:Name"),
        )

        video_source = p.find("tt:VideoSourceConfiguration", NS)
        if video_source is not None:
            bounds = video_source.find("tt:Bounds", NS)

            profile.video_source = VideoSourceConfiguration(
                token=attr(video_source, "token"),
                name=text(video_source, "tt:Name"),
                use_count=int_text(video_source, "tt:UseCount"),
                source_token=text(video_source, "tt:SourceToken"),
                bounds=Bounds(
                    x=int(attr(bounds, "x")) if bounds is not None and attr(bounds, "x") else None,
                    y=int(attr(bounds, "y")) if bounds is not None and attr(bounds, "y") else None,
                    width=int(attr(bounds, "width")) if bounds is not None and attr(bounds, "width") else None,
                    height=int(attr(bounds, "height")) if bounds is not None and attr(bounds, "height") else None,
                ),
            )

        video_encoder = p.find("tt:VideoEncoderConfiguration", NS)
        if video_encoder is not None:
            profile.video_encoder = VideoEncoderConfiguration(
                token=attr(video_encoder, "token"),
                name=text(video_encoder, "tt:Name"),
                use_count=int_text(video_encoder, "tt:UseCount"),
                encoding=text(video_encoder, "tt:Encoding"),
                resolution=Resolution(
                    width=int_text(video_encoder, "tt:Resolution/tt:Width"),
                    height=int_text(video_encoder, "tt:Resolution/tt:Height"),
                ),
                quality=float_text(video_encoder, "tt:Quality"),
                rate_control=RateControl(
                    frame_rate_limit=int_text(
                        video_encoder, "tt:RateControl/tt:FrameRateLimit"
                    ),
                    encoding_interval=int_text(
                        video_encoder, "tt:RateControl/tt:EncodingInterval"
                    ),
                    bitrate_limit=int_text(
                        video_encoder, "tt:RateControl/tt:BitrateLimit"
                    ),
                ),
                multicast=parse_multicast(video_encoder.find("tt:Multicast", NS)),
                session_timeout=text(video_encoder, "tt:SessionTimeout"),
            )

        audio_source = p.find("tt:AudioSourceConfiguration", NS)
        if audio_source is not None:
            profile.audio_source = AudioSourceConfiguration(
                token=attr(audio_source, "token"),
                name=text(audio_source, "tt:Name"),
                use_count=int_text(audio_source, "tt:UseCount"),
                source_token=text(audio_source, "tt:SourceToken"),
            )

        audio_encoder = p.find("tt:AudioEncoderConfiguration", NS)
        if audio_encoder is not None:
            profile.audio_encoder = AudioEncoderConfiguration(
                token=attr(audio_encoder, "token"),
                name=text(audio_encoder, "tt:Name"),
                use_count=int_text(audio_encoder, "tt:UseCount"),
                encoding=text(audio_encoder, "tt:Encoding"),
                bitrate=int_text(audio_encoder, "tt:Bitrate"),
                sample_rate=int_text(audio_encoder, "tt:SampleRate"),
                multicast=parse_multicast(audio_encoder.find("tt:Multicast", NS)),
                session_timeout=text(audio_encoder, "tt:SessionTimeout"),
            )

        ptz = p.find("tt:PTZConfiguration", NS)
        if ptz is not None:
            profile.ptz = PTZConfiguration(
                token=attr(ptz, "token"),
                name=text(ptz, "tt:Name"),
                use_count=int_text(ptz, "tt:UseCount"),
                node_token=text(ptz, "tt:NodeToken"),
                default_absolute_pant_tilt_position_space=text(
                    ptz, "tt:DefaultAbsolutePantTiltPositionSpace"
                ),
                default_absolute_zoom_position_space=text(
                    ptz, "tt:DefaultAbsoluteZoomPositionSpace"
                ),
                default_relative_pan_tilt_translation_space=text(
                    ptz, "tt:DefaultRelativePanTiltTranslationSpace"
                ),
                default_relative_zoom_translation_space=text(
                    ptz, "tt:DefaultRelativeZoomTranslationSpace"
                ),
                default_continuous_pan_tilt_velocity_space=text(
                    ptz, "tt:DefaultContinuousPanTiltVelocitySpace"
                ),
                default_continuous_zoom_velocity_space=text(
                    ptz, "tt:DefaultContinuousZoomVelocitySpace"
                ),
                default_ptz_timeout=text(ptz, "tt:DefaultPTZTimeout"),
            )

        analytics = p.find("tt:VideoAnalyticsConfiguration", NS)
        if analytics is not None:
            profile.video_analytics = VideoAnalyticsConfiguration(
                token=attr(analytics, "token"),
                name=text(analytics, "tt:Name"),
                use_count=int_text(analytics, "tt:UseCount"),
            )

        metadata = p.find("tt:MetadataConfiguration", NS)
        if metadata is not None:
            profile.metadata = MetadataConfiguration(
                token=attr(metadata, "token"),
                name=text(metadata, "tt:Name"),
                use_count=int_text(metadata, "tt:UseCount"),
                ptz_status=bool_text(metadata, "tt:PTZStatus/tt:Status"),
                events=metadata.find("tt:Events", NS) is not None,
                multicast=parse_multicast(metadata.find("tt:Multicast", NS)),
                session_timeout=text(metadata, "tt:SessionTimeout"),
            )

        response.profiles.append(profile)

    return response.profiles