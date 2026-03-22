# camera.py — Rolling frame buffer from USB camera at 120fps

import threading
import time
import logging
from collections import deque
from typing import Optional, List

import cv2
import numpy as np

import config

logger = logging.getLogger(__name__)


class CameraBuffer:
    """
    Continuously captures frames from the USB camera in a background thread.
    Maintains a rolling deque of JPEG-compressed frames.

    Each entry in the deque is raw JPEG bytes (compressed at capture time
    to keep memory usage low — ~15-25KB per frame at 720p quality 70).

    Total buffer: 720 frames × ~20KB avg = ~14MB
    """

    def __init__(self) -> None:
        self._deque: deque = deque(maxlen=config.BUFFER_MAXFRAMES)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cap: Optional[cv2.VideoCapture] = None
        self.camera_ok = False  # True once first frame received

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background capture thread."""
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="CameraCapture")
        self._thread.start()
        logger.info("Camera capture thread started")

    def stop(self) -> None:
        """Signal the capture thread to stop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        if self._cap:
            self._cap.release()
        logger.info("Camera capture stopped")

    def snapshot(self) -> List[bytes]:
        """
        Return a copy of the current rolling buffer as a list of JPEG bytes.
        Oldest frame first. Safe to call from any thread.
        """
        with self._lock:
            return list(self._deque)

    def latest_frame_jpeg(self) -> Optional[bytes]:
        """Return the most recent frame as JPEG bytes, or None if empty."""
        with self._lock:
            if not self._deque:
                return None
            return self._deque[-1]

    # ------------------------------------------------------------------
    # Capture loop (runs in background thread)
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        self._cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_V4L2)

        if not self._cap.isOpened():
            # Fallback: try without backend hint (works on macOS for dev)
            self._cap = cv2.VideoCapture(config.CAMERA_INDEX)

        if not self._cap.isOpened():
            logger.error(
                f"Could not open camera at index {config.CAMERA_INDEX}. "
                "Replay will be unavailable. Check USB camera connection."
            )
            return

        # Request target resolution and framerate
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS, config.CAMERA_FPS)

        # Use MJPEG codec from camera if available — offloads encoding from CPU
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        actual_fps = self._cap.get(cv2.CAP_PROP_FPS)
        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"Camera opened: {actual_w}x{actual_h} @ {actual_fps:.1f}fps")

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY]

        frame_interval = 1.0 / max(actual_fps, 1.0)
        last_time = time.monotonic()

        consecutive_failures = 0

        while self._running:
            ret, frame = self._cap.read()

            if not ret:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    logger.error("Camera read failed 30+ consecutive times — camera disconnected?")
                    self.camera_ok = False
                time.sleep(0.01)
                continue

            consecutive_failures = 0
            self.camera_ok = True

            # Resize to target resolution if camera returned different size
            if frame.shape[1] != config.CAMERA_WIDTH or frame.shape[0] != config.CAMERA_HEIGHT:
                frame = cv2.resize(
                    frame,
                    (config.CAMERA_WIDTH, config.CAMERA_HEIGHT),
                    interpolation=cv2.INTER_LINEAR,
                )

            # Compress to JPEG
            success, jpeg_buf = cv2.imencode(".jpg", frame, encode_params)
            if not success:
                continue

            jpeg_bytes = jpeg_buf.tobytes()

            with self._lock:
                self._deque.append(jpeg_bytes)

            # Pace the loop to avoid busy-spinning faster than the camera
            now = time.monotonic()
            elapsed = now - last_time
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            last_time = time.monotonic()

        self._cap.release()


# Singleton instance
camera = CameraBuffer()
