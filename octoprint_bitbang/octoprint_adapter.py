"""OctoPrint BitBang adapter - extends BitBangASGI with camera video track.

Subclasses BitBangASGI to add a camera video track alongside async HTTP
reverse proxy. Fully async -- no WSGI thread pool.
Camera source is auto-detected or explicitly configured.
"""

from bitbang import BitBangASGI
from aiortc.contrib.media import MediaPlayer, MediaRelay

from .camera import detect_camera


class OctoPrintBitBang(BitBangASGI):
    """BitBang adapter with camera video for OctoPrint remote access.

    Extends BitBangASGI to capture video from the best available camera
    source and share it with all connected clients using MediaRelay.
    Falls back to HTTP-only mode if no camera is found.
    """

    def __init__(self, app, camera_source=None, ws_target=None, **kwargs):
        super().__init__(app, **kwargs)
        self.ws_target = ws_target  # host:port for WebSocket bridging
        self.relay = MediaRelay()
        self.player = None
        self._init_camera(camera_source)

    def _init_camera(self, camera_source):
        """Initialize camera from explicit source or auto-detect."""
        source = camera_source or detect_camera()
        if not source:
            print("No camera - running in HTTP-only mode")
            return

        if source["type"] == "rtsp":
            # H.264 passthrough from camera-streamer (zero CPU)
            try:
                self.player = MediaPlayer(
                    source["url"],
                    format=source.get("format"),
                    options=source.get("options", {}),
                    decode=source.get("decode", True),
                )
                print(f"Opened RTSP camera: {source['url']}")
            except Exception as e:
                print(f"Warning: Could not open RTSP source: {e}")

        elif source["type"] == "usb":
            # USB webcam (software H.264 encode via aiortc)
            try:
                self.player = MediaPlayer(
                    source["device"],
                    format=source.get("format"),
                    options=source.get("options", {}),
                )
                print(f"Opened USB camera: {source['device']}")
            except Exception as e:
                print(f"Warning: Could not open camera '{source['device']}': {e}")

        elif source["type"] == "picamera2":
            # Pi CSI camera - placeholder for Phase 3
            print("picamera2 detected but not yet supported - HTTP-only mode")

    def setup_peer_connection(self, pc, client_id):
        """Add camera video track to peer connection."""
        if self.player and self.player.video:
            pc.addTrack(self.relay.subscribe(self.player.video))
            print(f"Added camera video track for {client_id}")

    def get_stream_metadata(self):
        """Return stream name for video track."""
        if self.player and self.player.video:
            return {"0": "camera"}
        return {}

    async def close(self):
        """Close peer connections and media player."""
        await super().close()
        if self.player:
            if self.player.video:
                self.player.video.stop()
            self.player = None
