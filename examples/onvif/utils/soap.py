from __future__ import annotations

import os
import base64
import hashlib
import requests
from datetime import datetime, timezone, timedelta


SOAP_ENV_NS = "http://www.w3.org/2003/05/soap-envelope"
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"

DEVICE_NS = "http://www.onvif.org/ver10/device/wsdl"
MEDIA_NS = "http://www.onvif.org/ver10/media/wsdl"
SCHEMA_NS = "http://www.onvif.org/ver10/schema"
IMAGING_NS = "http://www.onvif.org/ver20/imaging/wsdl"


def create_wsse_header_data(password: str, offset_seconds: int) -> tuple[str, str, str]:
    nonce_raw = os.urandom(20)
    nonce_b64 = base64.b64encode(nonce_raw).decode("ascii")
    created_dt = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    created = created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    digest_raw = hashlib.sha1(nonce_raw + created.encode("utf-8") + password.encode("utf-8")).digest()
    password_digest = base64.b64encode(digest_raw).decode("ascii")
    return password_digest, nonce_b64, created


def build_wsse_header(username: str, password: str, time_offset: int) -> str:
    password_digest, nonce, created = create_wsse_header_data(password, time_offset)

    return f"""
<SOAP-ENV:Header>
  <wsse:Security SOAP-ENV:mustUnderstand="1">
    <wsse:UsernameToken>
      <wsse:Username>{username}</wsse:Username>
      <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password>
      <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce>
      <wsu:Created>{created}</wsu:Created>
    </wsse:UsernameToken>
  </wsse:Security>
</SOAP-ENV:Header>
""".strip()


def build_soap_envelope(
    body: str,
    username: str,
    password: str,
    time_offset: int,
    service: str,
    include_tt: bool = False,
) -> str:
    if service == "device":
        service_ns = f'xmlns:tds="{DEVICE_NS}"'
    elif service == "media":
        service_ns = f'xmlns:trt="{MEDIA_NS}"'
    elif service == "imaging":
        service_ns = f'xmlns:timg="{IMAGING_NS}"'
    else:
        raise ValueError(f"Unknown ONVIF service: {service}")

    tt_ns = f' xmlns:tt="{SCHEMA_NS}"' if include_tt else ""

    header = build_wsse_header(username, password, time_offset)

    return f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV="{SOAP_ENV_NS}" {service_ns}{tt_ns} xmlns:wsse="{WSSE_NS}" xmlns:wsu="{WSU_NS}">{header}<SOAP-ENV:Body>{body}</SOAP-ENV:Body></SOAP-ENV:Envelope>"""


def onvif_post(
    url: str,
    body: str,
    username: str,
    password: str,
    time_offset: int,
    service: str,
    include_tt: bool = False,
    timeout: int = 5,
) -> bytes:
    soap = build_soap_envelope(
        body=body,
        username=username,
        password=password,
        time_offset=time_offset,
        service=service,
        include_tt=include_tt,
    )

    response = requests.post(url, data=soap, timeout=timeout)
    response.raise_for_status()
    return response.content