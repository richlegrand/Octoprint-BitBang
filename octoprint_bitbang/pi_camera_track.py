"""aiortc video track backed by picamera2 (Raspberry Pi CSI camera).

Captures frames from picamera2 and yields them as aiortc VideoFrames.
aiortc handles software H.264 encoding downstream.
"""

import asyncio
import fractions

from aiortc import MediaStreamTrack
from av import VideoFrame


class PiCameraTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, size=(640, 480), framerate=30):
        super().__init__()
        from picamera2 import Picamera2

        self.picam2 = Picamera2()
        config = self.picam2.create_video_configuration(
            main={"size": size, "format": "RGB888"}
        )
        self.picam2.configure(config)
        self.picam2.start()

        self.framerate = framerate
        self._timestamp = 0
        self._time_base = fractions.Fraction(1, 90000)
        self._ticks_per_frame = int(90000 / framerate)

    async def recv(self):
        loop = asyncio.get_event_loop()
        array = await loop.run_in_executor(None, self.picam2.capture_array)
        frame = VideoFrame.from_ndarray(array, format="bgr24")
        frame.pts = self._timestamp
        frame.time_base = self._time_base
        self._timestamp += self._ticks_per_frame
        return frame

    def stop(self):
        super().stop()
        try:
            self.picam2.stop()
            self.picam2.close()
        except Exception:
            pass
