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

    function addFullscreenButton(video) {
        var wrapper = document.createElement("div");
        wrapper.style.cssText = "position:relative;display:inline-block;width:100%;pointer-events:auto";

        var btn = document.createElement("button");
        btn.className = "btn btn-mini";
        btn.style.cssText = "position:absolute;top:8px;right:8px;z-index:10;opacity:0.6;cursor:pointer;pointer-events:auto";
        btn.innerHTML = '<i class="fas fa-expand"></i>';
        btn.title = "Fullscreen";
        btn.onmouseover = function () { btn.style.opacity = "1"; };
        btn.onmouseout = function () { btn.style.opacity = "0.6"; };
        btn.onclick = function () {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                var el = video.requestFullscreen ? video : wrapper;
                var fn = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
                if (fn) {
                    fn.call(el).catch(function (err) {
                        console.log("[BitBang] Fullscreen failed:", err);
                    });
                }
            }
        };

        video.parentNode.insertBefore(wrapper, video);
        wrapper.appendChild(video);
        wrapper.appendChild(btn);
    }

    function replaceWebcam(video) {
        var img = document.getElementById("webcam_image");
        if (!img) return false;
        video.style.width = "100%";
        video.style.backgroundColor = "#000";
        img.parentNode.replaceChild(video, img);
        addFullscreenButton(video);
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
