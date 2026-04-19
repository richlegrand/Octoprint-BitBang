"""OctoPrint-BitBang plugin.

Remote OctoPrint access with live H.264 video via BitBang WebRTC.
No account, no subscription, no port forwarding. One shareable link.
"""

__plugin_name__ = "BitBang"
__plugin_pythoncompat__ = ">=3.7,<4"

try:
    import threading
    import octoprint.plugin

    from .proxy import ReverseProxy
    from .octoprint_adapter import OctoPrintBitBang
    from .camera import detect_camera

    import flask
    import json
    import asyncio
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaRelay

    class BitBangPlugin(
        octoprint.plugin.StartupPlugin,
        octoprint.plugin.ShutdownPlugin,
        octoprint.plugin.SettingsPlugin,
        octoprint.plugin.TemplatePlugin,
        octoprint.plugin.AssetPlugin,
        octoprint.plugin.BlueprintPlugin,
    ):
        def __init__(self):
            super().__init__()
            self._adapter = None
            self._thread = None
            self._local_pcs = set()  # track local WebRTC peer connections

        def on_after_startup(self):
            if not self._settings.get_boolean(["enabled"]):
                self._logger.info("BitBang disabled in settings")
                return
            self._start_bitbang()

        def _start_bitbang(self):
            port = self._settings.global_get(["server", "port"]) or 5000
            proxy_app = ReverseProxy(f"localhost:{port}")

            camera = detect_camera(logger=self._logger)
            if camera:
                self._logger.info(f"Camera: {camera['type']}")
            else:
                self._logger.info("No camera detected, HTTP-only mode")

            pin = self._settings.get(["pin"]) or None

            self._adapter = OctoPrintBitBang(
                proxy_app,
                camera_source=camera,
                ws_target=f"localhost:{port}",
                program_name="octoprint",
                pin=pin,
            )

            self._thread = threading.Thread(
                target=self._adapter.run,
                daemon=True,
                name="BitBangThread",
            )
            self._thread.start()

            url = f"https://bitba.ng/{self._adapter.uid}"
            self._settings.set(["url"], url)
            self._settings.save()
            self._logger.info(f"BitBang remote access: {url}")

        # -- Local WebRTC video signaling --

        @octoprint.plugin.BlueprintPlugin.route("/offer", methods=["POST"])
        @octoprint.plugin.BlueprintPlugin.csrf_exempt()
        def local_offer(self):
            """Exchange WebRTC SDP for local H.264 video streaming."""
            if not self._adapter or not self._adapter.player or not self._adapter.player.video:
                return flask.jsonify({"error": "no camera"}), 503

            offer_sdp = flask.request.json.get("sdp")
            offer_type = flask.request.json.get("type", "offer")
            if not offer_sdp:
                return flask.jsonify({"error": "missing sdp"}), 400

            # Run the async WebRTC handshake in the adapter's event loop
            loop = self._adapter._loop
            if not loop:
                return flask.jsonify({"error": "not ready"}), 503

            future = asyncio.run_coroutine_threadsafe(
                self._handle_local_offer(offer_sdp, offer_type), loop
            )
            try:
                answer = future.result(timeout=10)
                return flask.jsonify(answer)
            except Exception as e:
                self._logger.error(f"Local WebRTC offer failed: {e}")
                return flask.jsonify({"error": str(e)}), 500

        async def _handle_local_offer(self, offer_sdp, offer_type):
            pc = RTCPeerConnection()
            self._local_pcs.add(pc)

            @pc.on("connectionstatechange")
            async def on_state():
                if pc.connectionState in ("failed", "closed"):
                    self._local_pcs.discard(pc)
                    await pc.close()

            # Add camera video track
            pc.addTrack(self._adapter.relay.subscribe(self._adapter.player.video))

            # Set remote offer and create answer
            offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            return {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type,
            }

        def on_shutdown(self):
            pass  # Daemon thread exits with OctoPrint

        def get_settings_defaults(self):
            return {
                "enabled": True,
                "pin": "",
                "url": "",
            }

        def get_template_configs(self):
            return [
                {"type": "settings", "custom_bindings": False},
                {"type": "navbar", "custom_bindings": False},
            ]

        def get_assets(self):
            return {
                "js": ["js/bitbang.js"],
            }

    __plugin_implementation__ = BitBangPlugin()

except ImportError:
    # OctoPrint not installed - standalone CLI mode
    pass
