# input_handler.py — USB keypad listener using evdev (Linux) with keyboard fallback

import asyncio
import logging
import threading
import sys
from typing import Optional

import config

logger = logging.getLogger(__name__)

# Keys we care about
WATCHED_KEYS = {
    config.KEY_T1_UP,
    config.KEY_T1_DOWN,
    config.KEY_T2_UP,
    config.KEY_T2_DOWN,
    config.KEY_REPLAY,
}


class InputHandler:
    """
    Listens for keypad input and dispatches to game_state.handle_key().

    On Linux (Pi): uses evdev to read raw input events from all keyboard
    devices. This captures input from both USB keypads simultaneously,
    regardless of whether they're in focus.

    On macOS/Windows (dev): falls back to stdin / pynput if available,
    so the app can be tested without a Pi.
    """

    def __init__(self) -> None:
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._game_state = None  # set via set_game_state()

    def set_game_state(self, gs) -> None:
        self._game_state = gs

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self) -> None:
        self._running = True
        if sys.platform.startswith("linux"):
            self._start_evdev()
        else:
            self._start_keyboard_fallback()

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Linux — evdev (production, Pi)
    # ------------------------------------------------------------------

    def _start_evdev(self) -> None:
        """
        Spawn a thread per keyboard device found, watching all simultaneously.
        Both keypads send the same key codes so no device discrimination needed.
        """
        try:
            import evdev
        except ImportError:
            logger.error("evdev not installed. Run: pip install evdev")
            return

        devices = self._find_keyboard_devices(evdev)
        if not devices:
            logger.warning("No keyboard devices found via evdev. Check USB keypads are connected.")
            return

        logger.info(f"Monitoring {len(devices)} input device(s): {[d.name for d in devices]}")

        for device in devices:
            t = threading.Thread(
                target=self._evdev_thread,
                args=(device,),
                daemon=True,
                name=f"Input-{device.name[:20]}",
            )
            t.start()

    def _find_keyboard_devices(self, evdev):
        """Return all evdev devices that have the number keys we need."""
        from evdev import ecodes
        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                # Check if device has EV_KEY and at least one of our watched keys
                if ecodes.EV_KEY in caps:
                    key_codes = caps[ecodes.EV_KEY]
                    needed = {
                        ecodes.KEY_1, ecodes.KEY_2,
                        ecodes.KEY_3, ecodes.KEY_4,
                        ecodes.KEY_5,
                    }
                    if needed.intersection(set(key_codes)):
                        devices.append(dev)
            except Exception:
                pass
        return devices

    def _evdev_thread(self, device) -> None:
        """Blocking read loop for a single evdev device."""
        from evdev import ecodes, categorize, events as evdev_events
        try:
            device.grab()  # Exclusive access — prevents keys reaching other apps
        except Exception as e:
            logger.warning(f"Could not grab device {device.name}: {e}")

        try:
            for event in device.read_loop():
                if not self._running:
                    break
                if event.type == 1:  # EV_KEY
                    # value 1 = key down, 0 = key up, 2 = repeat
                    if event.value == 1:
                        key_name = f"KEY_{self._code_to_num(event.code)}"
                        if key_name in WATCHED_KEYS:
                            self._dispatch(key_name)
        except OSError:
            logger.warning(f"Device {device.name} disconnected")
        finally:
            try:
                device.ungrab()
            except Exception:
                pass

    @staticmethod
    def _code_to_num(code: int) -> Optional[str]:
        """Map evdev key code to the digit string (2=KEY_1 means key '1' etc.)."""
        from evdev import ecodes
        mapping = {
            ecodes.KEY_1: "1",
            ecodes.KEY_2: "2",
            ecodes.KEY_3: "3",
            ecodes.KEY_4: "4",
            ecodes.KEY_5: "5",
        }
        return mapping.get(code)

    # ------------------------------------------------------------------
    # Non-Linux fallback (dev/testing on macOS/Windows)
    # ------------------------------------------------------------------

    def _start_keyboard_fallback(self) -> None:
        """
        On non-Linux platforms: try pynput, fall back to stdin line-reading.
        Useful for development — press 1-5 in the terminal.
        """
        try:
            from pynput import keyboard as pynput_kb

            def on_press(key):
                try:
                    char = key.char
                    if char in ("1", "2", "3", "4", "5"):
                        self._dispatch(f"KEY_{char}")
                except AttributeError:
                    pass  # Special key, ignore

            listener = pynput_kb.Listener(on_press=on_press)
            listener.daemon = True
            listener.start()
            logger.info("Input: using pynput keyboard listener (dev mode)")

        except ImportError:
            logger.info("Input: using stdin line reader (dev mode). Type 1-5 + Enter.")
            t = threading.Thread(target=self._stdin_loop, daemon=True, name="InputStdin")
            t.start()

    def _stdin_loop(self) -> None:
        while self._running:
            try:
                line = sys.stdin.readline().strip()
                if line in ("1", "2", "3", "4", "5"):
                    self._dispatch(f"KEY_{line}")
            except EOFError:
                break

    # ------------------------------------------------------------------
    # Dispatch key to game state (thread-safe asyncio scheduling)
    # ------------------------------------------------------------------

    def _dispatch(self, key: str) -> None:
        if self._game_state is None or self._loop is None:
            return
        # Schedule the coroutine on the event loop from a non-async thread
        asyncio.run_coroutine_threadsafe(
            self._game_state.handle_key(key),
            self._loop,
        )


# Singleton
input_handler = InputHandler()
