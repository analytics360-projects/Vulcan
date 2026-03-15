"""Camera Manager service — ONVIF discovery, VMS sync, PTZ control, RTSP management."""
import asyncio
import hashlib
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx

from config import logger
from modules.camera_manager.models import (
    AnalysisPriority, CameraAddRequest, CameraSource, CameraSourceType,
    CameraStatus, CameraStatusResponse, CameraUpdateRequest,
    DiscoveredCamera, OnvifCredentials, OnvifDiscoveryRequest,
    OnvifDiscoveryResponse, PTZAction, PTZCommand, PTZPreset, PTZResponse,
    VMSCameraInfo, VMSSyncRequest, VMSSyncResponse,
)


class CameraManagerService:
    """Manages camera registry, ONVIF discovery, VMS integration, and PTZ."""

    def __init__(self):
        self._cameras: Dict[str, CameraSource] = {}
        self._ptz_presets: Dict[str, List[PTZPreset]] = {}

    # ── Camera Registry ──

    def add_camera(self, req: CameraAddRequest) -> CameraSource:
        """Register a new camera source."""
        cam_id = hashlib.md5(
            f"{req.source_type}:{req.rtsp_url or req.name}:{time.time()}".encode()
        ).hexdigest()[:12]

        camera = CameraSource(
            id=cam_id,
            name=req.name,
            source_type=req.source_type,
            rtsp_url=req.rtsp_url,
            location=req.location,
            lat=req.lat,
            lng=req.lng,
            subcentro_id=req.subcentro_id,
            zone=req.zone,
            priority=req.priority,
            onvif=req.onvif,
            milestone_camera_guid=req.milestone_camera_guid,
            sense_camera_id=req.sense_camera_id,
            ptz_capable=req.onvif is not None,
            status=CameraStatus.OFFLINE,
        )
        if req.analysis_config:
            camera.analysis_config.update(req.analysis_config)

        # Set FPS based on priority
        fps_map = {
            AnalysisPriority.CRITICAL: 15,
            AnalysisPriority.HIGH: 10,
            AnalysisPriority.MEDIUM: 5,
            AnalysisPriority.LOW: 2,
            AnalysisPriority.DISABLED: 0,
        }
        camera.analysis_config["fps_target"] = fps_map.get(req.priority, 5)

        self._cameras[cam_id] = camera
        logger.info(f"Camera registered: {cam_id} ({req.name}) [{req.source_type}]")
        return camera

    def update_camera(self, camera_id: str, req: CameraUpdateRequest) -> Optional[CameraSource]:
        """Update camera configuration."""
        cam = self._cameras.get(camera_id)
        if not cam:
            return None
        if req.name is not None:
            cam.name = req.name
        if req.priority is not None:
            cam.priority = req.priority
            fps_map = {
                AnalysisPriority.CRITICAL: 15, AnalysisPriority.HIGH: 10,
                AnalysisPriority.MEDIUM: 5, AnalysisPriority.LOW: 2,
                AnalysisPriority.DISABLED: 0,
            }
            cam.analysis_config["fps_target"] = fps_map.get(req.priority, 5)
        if req.analysis_config is not None:
            cam.analysis_config.update(req.analysis_config)
        if req.location is not None:
            cam.location = req.location
        if req.lat is not None:
            cam.lat = req.lat
        if req.lng is not None:
            cam.lng = req.lng
        if req.zone is not None:
            cam.zone = req.zone
        return cam

    def remove_camera(self, camera_id: str) -> bool:
        """Remove a camera from the registry."""
        if camera_id in self._cameras:
            del self._cameras[camera_id]
            self._ptz_presets.pop(camera_id, None)
            logger.info(f"Camera removed: {camera_id}")
            return True
        return False

    def get_camera(self, camera_id: str) -> Optional[CameraSource]:
        return self._cameras.get(camera_id)

    def list_cameras(self) -> List[CameraSource]:
        return list(self._cameras.values())

    def get_status(self) -> CameraStatusResponse:
        cams = list(self._cameras.values())
        return CameraStatusResponse(
            cameras=cams,
            total=len(cams),
            online=sum(1 for c in cams if c.status == CameraStatus.ONLINE),
            analyzing=sum(1 for c in cams if c.status == CameraStatus.ANALYZING),
            offline=sum(1 for c in cams if c.status == CameraStatus.OFFLINE),
            error=sum(1 for c in cams if c.status == CameraStatus.ERROR),
        )

    def set_camera_status(self, camera_id: str, status: CameraStatus):
        cam = self._cameras.get(camera_id)
        if cam:
            cam.status = status

    # ── ONVIF Discovery ──

    async def discover_onvif(self, req: OnvifDiscoveryRequest) -> OnvifDiscoveryResponse:
        """Discover ONVIF cameras on the network via WS-Discovery."""
        start_ms = int(time.time() * 1000)
        discovered: List[DiscoveredCamera] = []

        # WS-Discovery probe message
        probe_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"'
            ' xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
            ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
            ' xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
            '<e:Header>'
            '<w:MessageID>uuid:probe-centinela</w:MessageID>'
            '<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
            '<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
            '</e:Header>'
            '<e:Body>'
            '<d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe>'
            '</e:Body>'
            '</e:Envelope>'
        )

        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(req.timeout_seconds)

            # Send WS-Discovery probe to multicast
            sock.sendto(probe_xml.encode(), ("239.255.255.250", 3702))

            endpoints: List[str] = []
            try:
                while True:
                    data, addr = sock.recvfrom(65535)
                    try:
                        root = ET.fromstring(data.decode())
                        # Extract XAddrs from ProbeMatch
                        for elem in root.iter():
                            if "XAddrs" in elem.tag and elem.text:
                                for xaddr in elem.text.split():
                                    if xaddr not in endpoints:
                                        endpoints.append(xaddr)
                    except ET.ParseError:
                        pass
            except socket.timeout:
                pass
            finally:
                sock.close()

            # Probe each discovered endpoint for details
            for xaddr in endpoints:
                cam = await self._probe_onvif_device(xaddr, req.username, req.password)
                if cam:
                    discovered.append(cam)

        except Exception as e:
            logger.error(f"ONVIF discovery error: {e}")

        elapsed = int(time.time() * 1000) - start_ms
        return OnvifDiscoveryResponse(
            cameras=discovered,
            total_found=len(discovered),
            scan_duration_ms=elapsed,
        )

    async def _probe_onvif_device(
        self, xaddr: str, username: str, password: str
    ) -> Optional[DiscoveredCamera]:
        """Probe a single ONVIF device for capabilities."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(xaddr)
            host = parsed.hostname or ""
            port = parsed.port or 80

            # GetDeviceInformation SOAP request
            get_info_xml = self._build_soap_request(
                username, password,
                "http://www.onvif.org/ver10/device/wsdl/GetDeviceInformation",
                "<tds:GetDeviceInformation xmlns:tds='http://www.onvif.org/ver10/device/wsdl'/>",
            )

            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                resp = await client.post(xaddr, content=get_info_xml, headers={
                    "Content-Type": "application/soap+xml; charset=utf-8"
                })

            manufacturer = model = firmware = serial = ""
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for elem in root.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if tag == "Manufacturer" and elem.text:
                        manufacturer = elem.text
                    elif tag == "Model" and elem.text:
                        model = elem.text
                    elif tag == "FirmwareVersion" and elem.text:
                        firmware = elem.text
                    elif tag == "SerialNumber" and elem.text:
                        serial = elem.text

            # Get RTSP stream URI
            rtsp_url = await self._get_onvif_stream_uri(xaddr, username, password)

            # Check PTZ capability
            ptz_capable = await self._check_ptz_capability(xaddr, username, password)

            return DiscoveredCamera(
                host=host,
                port=port,
                manufacturer=manufacturer,
                model=model,
                firmware=firmware,
                serial=serial,
                rtsp_url=rtsp_url,
                profiles=["Profile S"],
                ptz_capable=ptz_capable,
                resolution="1920x1080",
            )
        except Exception as e:
            logger.warning(f"Failed to probe ONVIF device {xaddr}: {e}")
            return None

    async def _get_onvif_stream_uri(self, xaddr: str, username: str, password: str) -> str:
        """Get RTSP stream URI from ONVIF media service."""
        try:
            media_url = xaddr.replace("/onvif/device_service", "/onvif/media_service")
            get_profiles_xml = self._build_soap_request(
                username, password,
                "http://www.onvif.org/ver10/media/wsdl/GetProfiles",
                "<trt:GetProfiles xmlns:trt='http://www.onvif.org/ver10/media/wsdl'/>",
            )
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                resp = await client.post(media_url, content=get_profiles_xml, headers={
                    "Content-Type": "application/soap+xml; charset=utf-8"
                })

            if resp.status_code != 200:
                return ""

            # Extract first profile token
            root = ET.fromstring(resp.text)
            profile_token = ""
            for elem in root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag == "Profiles":
                    profile_token = elem.get("token", "")
                    break

            if not profile_token:
                return ""

            # GetStreamUri
            get_uri_xml = self._build_soap_request(
                username, password,
                "http://www.onvif.org/ver10/media/wsdl/GetStreamUri",
                f"""<trt:GetStreamUri xmlns:trt='http://www.onvif.org/ver10/media/wsdl'>
                    <trt:StreamSetup>
                        <tt:Stream xmlns:tt='http://www.onvif.org/ver10/schema'>RTP-Unicast</tt:Stream>
                        <tt:Transport xmlns:tt='http://www.onvif.org/ver10/schema'>
                            <tt:Protocol>RTSP</tt:Protocol>
                        </tt:Transport>
                    </trt:StreamSetup>
                    <trt:ProfileToken>{profile_token}</trt:ProfileToken>
                </trt:GetStreamUri>""",
            )
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                resp = await client.post(media_url, content=get_uri_xml, headers={
                    "Content-Type": "application/soap+xml; charset=utf-8"
                })

            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for elem in root.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if tag == "Uri" and elem.text and "rtsp" in elem.text:
                        return elem.text
            return ""
        except Exception as e:
            logger.warning(f"Failed to get ONVIF stream URI: {e}")
            return ""

    async def _check_ptz_capability(self, xaddr: str, username: str, password: str) -> bool:
        """Check if camera supports PTZ."""
        try:
            get_caps_xml = self._build_soap_request(
                username, password,
                "http://www.onvif.org/ver10/device/wsdl/GetCapabilities",
                "<tds:GetCapabilities xmlns:tds='http://www.onvif.org/ver10/device/wsdl'>"
                "<tds:Category>PTZ</tds:Category></tds:GetCapabilities>",
            )
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                resp = await client.post(xaddr, content=get_caps_xml, headers={
                    "Content-Type": "application/soap+xml; charset=utf-8"
                })
            return resp.status_code == 200 and "PTZ" in resp.text
        except Exception:
            return False

    def _build_soap_request(self, username: str, password: str, action: str, body: str) -> str:
        """Build ONVIF SOAP request with WS-Security if credentials provided."""
        import hashlib
        import base64
        from datetime import datetime, timezone

        security_header = ""
        if username and password:
            nonce = base64.b64encode(hashlib.sha1(str(time.time()).encode()).digest()).decode()
            created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            # WS-Security UsernameToken
            digest = base64.b64encode(
                hashlib.sha1(
                    (base64.b64decode(nonce).decode("latin-1") + created + password).encode("latin-1")
                ).digest()
            ).decode()
            security_header = f"""
            <Security xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
                <UsernameToken>
                    <Username>{username}</Username>
                    <Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</Password>
                    <Nonce>{nonce}</Nonce>
                    <Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">{created}</Created>
                </UsernameToken>
            </Security>"""

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
            ' xmlns:a="http://www.w3.org/2005/08/addressing">'
            f'<s:Header><a:Action>{action}</a:Action>{security_header}</s:Header>'
            f'<s:Body>{body}</s:Body>'
            '</s:Envelope>'
        )

    # ── PTZ Control ──

    async def ptz_command(self, cmd: PTZCommand) -> PTZResponse:
        """Execute PTZ command via ONVIF."""
        cam = self._cameras.get(cmd.camera_id)
        if not cam:
            return PTZResponse(success=False, message="Camera not found")
        if not cam.onvif:
            return PTZResponse(success=False, message="Camera has no ONVIF credentials")
        if not cam.ptz_capable:
            return PTZResponse(success=False, message="Camera does not support PTZ")

        xaddr = f"http://{cam.onvif.host}:{cam.onvif.port}/onvif/ptz_service"

        try:
            if cmd.action == PTZAction.MOVE:
                return await self._ptz_continuous_move(xaddr, cam.onvif, cmd)
            elif cmd.action == PTZAction.STOP:
                return await self._ptz_stop(xaddr, cam.onvif)
            elif cmd.action == PTZAction.ZOOM:
                return await self._ptz_continuous_move(xaddr, cam.onvif, cmd)
            elif cmd.action == PTZAction.HOME:
                return await self._ptz_goto_home(xaddr, cam.onvif)
            elif cmd.action == PTZAction.PRESET:
                return await self._ptz_goto_preset(xaddr, cam.onvif, cmd.preset_name)
            return PTZResponse(success=False, message=f"Unknown action: {cmd.action}")
        except Exception as e:
            return PTZResponse(success=False, message=str(e))

    async def _ptz_continuous_move(
        self, url: str, creds: OnvifCredentials, cmd: PTZCommand
    ) -> PTZResponse:
        body = (
            f"<ptz:ContinuousMove xmlns:ptz='http://www.onvif.org/ver20/ptz/wsdl'>"
            f"<ptz:ProfileToken>Profile_1</ptz:ProfileToken>"
            f"<ptz:Velocity>"
            f"<tt:PanTilt xmlns:tt='http://www.onvif.org/ver10/schema' x='{cmd.pan}' y='{cmd.tilt}'/>"
            f"<tt:Zoom xmlns:tt='http://www.onvif.org/ver10/schema' x='{cmd.zoom}'/>"
            f"</ptz:Velocity></ptz:ContinuousMove>"
        )
        soap = self._build_soap_request(
            creds.username, creds.password,
            "http://www.onvif.org/ver20/ptz/wsdl/ContinuousMove", body,
        )
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.post(url, content=soap, headers={
                "Content-Type": "application/soap+xml; charset=utf-8"
            })
        return PTZResponse(success=resp.status_code == 200, message="Move command sent")

    async def _ptz_stop(self, url: str, creds: OnvifCredentials) -> PTZResponse:
        body = (
            "<ptz:Stop xmlns:ptz='http://www.onvif.org/ver20/ptz/wsdl'>"
            "<ptz:ProfileToken>Profile_1</ptz:ProfileToken>"
            "<ptz:PanTilt>true</ptz:PanTilt><ptz:Zoom>true</ptz:Zoom>"
            "</ptz:Stop>"
        )
        soap = self._build_soap_request(
            creds.username, creds.password,
            "http://www.onvif.org/ver20/ptz/wsdl/Stop", body,
        )
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.post(url, content=soap, headers={
                "Content-Type": "application/soap+xml; charset=utf-8"
            })
        return PTZResponse(success=resp.status_code == 200, message="Stop command sent")

    async def _ptz_goto_home(self, url: str, creds: OnvifCredentials) -> PTZResponse:
        body = (
            "<ptz:GotoHomePosition xmlns:ptz='http://www.onvif.org/ver20/ptz/wsdl'>"
            "<ptz:ProfileToken>Profile_1</ptz:ProfileToken>"
            "</ptz:GotoHomePosition>"
        )
        soap = self._build_soap_request(
            creds.username, creds.password,
            "http://www.onvif.org/ver20/ptz/wsdl/GotoHomePosition", body,
        )
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.post(url, content=soap, headers={
                "Content-Type": "application/soap+xml; charset=utf-8"
            })
        return PTZResponse(success=resp.status_code == 200, message="Going to home position")

    async def _ptz_goto_preset(
        self, url: str, creds: OnvifCredentials, preset_name: str
    ) -> PTZResponse:
        body = (
            "<ptz:GotoPreset xmlns:ptz='http://www.onvif.org/ver20/ptz/wsdl'>"
            "<ptz:ProfileToken>Profile_1</ptz:ProfileToken>"
            f"<ptz:PresetToken>{preset_name}</ptz:PresetToken>"
            "</ptz:GotoPreset>"
        )
        soap = self._build_soap_request(
            creds.username, creds.password,
            "http://www.onvif.org/ver20/ptz/wsdl/GotoPreset", body,
        )
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.post(url, content=soap, headers={
                "Content-Type": "application/soap+xml; charset=utf-8"
            })
        return PTZResponse(success=resp.status_code == 200, message=f"Going to preset {preset_name}")

    # ── VMS Integration ──

    async def sync_milestone(self, req: VMSSyncRequest) -> VMSSyncResponse:
        """Sync cameras from Milestone XProtect via REST API."""
        cameras: List[VMSCameraInfo] = []
        try:
            auth = (req.username, req.password) if req.username else None
            headers = {}
            if req.api_token:
                headers["Authorization"] = f"Bearer {req.api_token}"

            async with httpx.AsyncClient(timeout=15.0, verify=False, auth=auth) as client:
                # Milestone REST API v1
                resp = await client.get(
                    f"{req.server_url}/api/rest/v1/cameras",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data if isinstance(data, list) else data.get("array", data.get("cameras", []))
                    for item in items:
                        cam_id = item.get("id", item.get("guid", ""))
                        name = item.get("name", item.get("displayName", "Unknown"))
                        enabled = item.get("enabled", True)
                        # Build RTSP URL from Milestone recording server
                        server = req.server_url.replace("https://", "").replace("http://", "").split(":")[0]
                        rtsp_url = f"rtsp://{server}:554/live/{cam_id}/media.smp"
                        cameras.append(VMSCameraInfo(
                            vms_id=cam_id,
                            name=name,
                            rtsp_url=rtsp_url,
                            recording=True,
                            enabled=enabled,
                            hardware_model=item.get("hardwareModelName", ""),
                            location=item.get("description", ""),
                            groups=item.get("groups", []),
                        ))
        except Exception as e:
            logger.error(f"Milestone sync error: {e}")

        return self._finalize_vms_sync(cameras, req, CameraSourceType.MILESTONE)

    async def sync_sense(self, req: VMSSyncRequest) -> VMSSyncResponse:
        """Sync cameras from Senstar Symphony via API."""
        cameras: List[VMSCameraInfo] = []
        try:
            headers = {}
            if req.api_token:
                headers["Authorization"] = f"Bearer {req.api_token}"
            auth = (req.username, req.password) if req.username else None

            async with httpx.AsyncClient(timeout=15.0, verify=False, auth=auth) as client:
                resp = await client.get(
                    f"{req.server_url}/api/cameras",
                    headers=headers,
                )
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, dict):
                        items = items.get("cameras", items.get("data", []))
                    for item in items:
                        cam_id = str(item.get("id", item.get("cameraId", "")))
                        name = item.get("name", "Unknown")
                        rtsp_url = item.get("rtspUrl", item.get("streamUrl", ""))
                        if not rtsp_url:
                            server = req.server_url.replace("https://", "").replace("http://", "").split(":")[0]
                            rtsp_url = f"rtsp://{server}:554/stream/{cam_id}"
                        cameras.append(VMSCameraInfo(
                            vms_id=cam_id,
                            name=name,
                            rtsp_url=rtsp_url,
                            recording=item.get("recording", False),
                            enabled=item.get("enabled", True),
                            hardware_model=item.get("model", ""),
                            location=item.get("location", ""),
                        ))
        except Exception as e:
            logger.error(f"Sense sync error: {e}")

        return self._finalize_vms_sync(cameras, req, CameraSourceType.SENSE)

    def _finalize_vms_sync(
        self, cameras: List[VMSCameraInfo], req: VMSSyncRequest, source_type: CameraSourceType
    ) -> VMSSyncResponse:
        """Auto-add cameras if requested, compute sync stats."""
        existing_vms_ids = set()
        for cam in self._cameras.values():
            if cam.source_type == source_type:
                if source_type == CameraSourceType.MILESTONE:
                    existing_vms_ids.add(cam.milestone_camera_guid)
                else:
                    existing_vms_ids.add(cam.sense_camera_id)

        already = sum(1 for c in cameras if c.vms_id in existing_vms_ids)
        newly_added = 0

        if req.auto_add:
            for vms_cam in cameras:
                if vms_cam.vms_id not in existing_vms_ids and vms_cam.enabled:
                    add_req = CameraAddRequest(
                        name=vms_cam.name,
                        source_type=source_type,
                        rtsp_url=vms_cam.rtsp_url,
                        location=vms_cam.location,
                        milestone_camera_guid=vms_cam.vms_id if source_type == CameraSourceType.MILESTONE else "",
                        sense_camera_id=vms_cam.vms_id if source_type == CameraSourceType.SENSE else "",
                    )
                    self.add_camera(add_req)
                    newly_added += 1

        return VMSSyncResponse(
            cameras=cameras,
            total_in_vms=len(cameras),
            already_registered=already,
            newly_added=newly_added,
        )

    # ── RTSP Health Check ──

    async def health_check_all(self) -> Dict[str, str]:
        """Check connectivity of all registered cameras."""
        results = {}
        for cam_id, cam in self._cameras.items():
            if not cam.rtsp_url:
                cam.status = CameraStatus.ERROR
                results[cam_id] = "no_rtsp_url"
                continue
            try:
                # Quick RTSP OPTIONS probe via TCP
                from urllib.parse import urlparse
                parsed = urlparse(cam.rtsp_url)
                host = parsed.hostname or ""
                port = parsed.port or 554

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=3.0
                )
                writer.write(f"OPTIONS {cam.rtsp_url} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
                await writer.drain()
                data = await asyncio.wait_for(reader.read(1024), timeout=3.0)
                writer.close()

                if b"RTSP/1.0 200" in data:
                    if cam.status != CameraStatus.ANALYZING:
                        cam.status = CameraStatus.ONLINE
                    results[cam_id] = "online"
                else:
                    cam.status = CameraStatus.ERROR
                    results[cam_id] = "rtsp_error"
            except Exception:
                cam.status = CameraStatus.OFFLINE
                results[cam_id] = "offline"

        return results


# Singleton
camera_manager_service = CameraManagerService()
