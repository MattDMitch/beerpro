#!/usr/bin/env python3
# main.py — Beer Pro entry point

import asyncio
import logging
import signal
import sys

import uvicorn

import config
from camera import camera
from input_handler import input_handler
from game_state import state
import wifi_manager

# sd_notify is used to tell systemd the service is ready (for WatchdogSec)
# It's a no-op when not running under systemd (dev mode)
try:
    from systemd.daemon import notify as sd_notify
except ImportError:
    def sd_notify(msg): pass  # noqa: E704

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def print_banner():
    banner = r"""
  ____                 ____
 |  _ \               |  _ \ _ __ ___
 | |_) | ___  ___ _ __| |_) | '__/ _ \
 |  _ < / _ \/ _ \ '__|  __/| | | (_) |
 |_| \_\\___/\___/_|  |_|   |_|  \___/

  Beer Pro — Scoreboard & Replay System
  ----------------------------------------
  Access at: http://{ip}:{port}
  WiFi SSID:  {ssid}
  Keys: [1] T1+ [2] T1- [3] T2+ [4] T2- [5] Replay
""".format(ip=config.WIFI_IP, port=config.PORT, ssid=config.WIFI_SSID)
    print(banner)


async def main():
    print_banner()

    # Check WiFi configuration state and inform game_state
    configured = wifi_manager.is_configured()
    if not configured:
        logger.info("WiFi not configured — starting in setup mode")
        state.set_setup_mode(True)
    else:
        logger.info(f"WiFi configured (SSID: {wifi_manager.saved_ssid()})")

    # Start camera buffer in background thread
    logger.info("Starting camera capture...")
    camera.start()

    # Wire up input handler with game state + asyncio loop
    loop = asyncio.get_running_loop()
    input_handler.set_game_state(state)
    input_handler.set_loop(loop)
    input_handler.start()
    logger.info("Input handler started")

    # Configure uvicorn
    uv_config = uvicorn.Config(
        app="server:app",
        host=config.HOST,
        port=config.PORT,
        log_level="warning",     # Suppress uvicorn access logs by default
        loop="asyncio",
        reload=False,
    )
    server = uvicorn.Server(uv_config)

    # Handle graceful shutdown on SIGINT/SIGTERM
    def _shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        camera.stop()
        input_handler.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info(f"Beer Pro running on http://{config.HOST}:{config.PORT}")

    # Notify systemd that the service is ready (enables watchdog keepalive)
    sd_notify("READY=1")

    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
