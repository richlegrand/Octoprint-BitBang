/*
 * OctoPrint-BitBang - H.264 video for OctoPrint
 *
 * Two modes:
 * - Remote (via BitBang): replaces MJPEG <img> with <video> wired to
 *   BitBang's WebRTC stream (bootstrap.js handles the track)
 * - Local (direct access): creates a WebRTC peer connection to the
 *   plugin's /offer endpoint for H.264 video on the LAN
 */
(function () {
    var isBitBang = navigator.serviceWorker && navigator.serviceWorker.controller;

    function replaceWebcam(video) {
        var img = document.getElementById("webcam_image");
        if (!img) return false;
        video.style.width = "100%";
        img.parentNode.replaceChild(video, img);
        return true;
    }

    if (isBitBang) {
        // Remote mode: bootstrap.js wires the track via data-bitbang-stream
        function injectRemote() {
            var video = document.createElement("video");
            video.setAttribute("data-bitbang-stream", "camera");
            video.autoplay = true;
            video.playsinline = true;
            video.muted = true;
            replaceWebcam(video);
        }

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", injectRemote);
        } else {
            injectRemote();
        }

        var observer = new MutationObserver(function () {
            if (document.getElementById("webcam_image")) {
                injectRemote();
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });

    } else {
        // Local mode: direct WebRTC to the plugin's signaling endpoint
        function startLocalVideo() {
            var video = document.createElement("video");
            video.autoplay = true;
            video.playsinline = true;
            video.muted = true;
            if (!replaceWebcam(video)) return;

            var pc = new RTCPeerConnection();

            pc.ontrack = function (event) {
                video.srcObject = event.streams[0];
            };

            // Need to add a transceiver to receive video
            pc.addTransceiver("video", { direction: "recvonly" });

            pc.createOffer().then(function (offer) {
                return pc.setLocalDescription(offer);
            }).then(function () {
                return fetch("/plugin/bitbang/offer", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        sdp: pc.localDescription.sdp,
                        type: pc.localDescription.type
                    })
                });
            }).then(function (response) {
                return response.json();
            }).then(function (answer) {
                if (answer.error) {
                    console.log("[BitBang] Local video not available:", answer.error);
                    return;
                }
                return pc.setRemoteDescription(answer);
            }).catch(function (err) {
                console.log("[BitBang] Local video failed:", err);
            });
        }

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", startLocalVideo);
        } else {
            startLocalVideo();
        }

        var observer = new MutationObserver(function () {
            if (document.getElementById("webcam_image")) {
                startLocalVideo();
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }
})();
