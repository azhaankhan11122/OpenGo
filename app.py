#!/usr/bin/env python3
"""
OpenGo - A Minimal, Private GPS Location Tool for iOS.
Zero telemetry. Zero accounts. Runs 100% locally on your Mac.
"""

import sys
import os
import asyncio
import json
import logging
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading
import socket
import urllib.parse

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("opengo")

# Core pymobiledevice3 imports
try:
    from pymobiledevice3.usbmux import list_devices
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.simulate_location import DtSimulateLocation
    from pymobiledevice3.exceptions import (
        NoDeviceConnectedError,
        PasscodeRequiredError,
        NotPairedError,
        NotTrustedError,
        DeveloperModeError,
        DeveloperModeIsNotEnabledError
    )
    PYMD3_AVAILABLE = True
except ImportError as e:
    logger.warning(f"pymobiledevice3 import issue: {e}")
    PYMD3_AVAILABLE = False


import subprocess
import shutil

class GpsEngine:
    """Manages Apple developer location simulation for single or multiple devices."""

    _selected_udid = None

    @staticmethod
    def _devicectl_available():
        return shutil.which("xcrun") is not None

    @staticmethod
    def get_all_devices():
        """Scans and returns all physical iOS devices connected via USB or Wi-Fi."""
        devices = []
        if not GpsEngine._devicectl_available():
            return devices

        try:
            res = subprocess.run(
                ["xcrun", "devicectl", "list", "devices", "--json-output", "-"],
                capture_output=True,
                text=True,
                timeout=6
            )
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                for d in data.get("result", {}).get("devices", []):
                    props = d.get("properties", {})
                    hw = props.get("hardware", {}) or d.get("hardwareProperties", {})
                    conn = props.get("connection", {}) or d.get("connectionProperties", {})
                    state = props.get("state", {}) or d.get("deviceProperties", {})
                    sw = props.get("software", {})

                    platform = hw.get("platform", "")
                    dev_type = hw.get("deviceType", "")
                    reality = hw.get("reality", "")

                    # Filter for physical iOS devices (iPhone/iPad)
                    if platform != "iOS" or reality == "simulated" or dev_type.lower() not in ("iphone", "ipad"):
                        continue

                    udid = hw.get("udid") or d.get("identifier")
                    name = state.get("name") or d.get("deviceProperties", {}).get("name") or "iPhone"
                    version_str = sw.get("osVersionNumber", {}).get("stringValue") or state.get("osVersionNumber", "")
                    marketing_name = hw.get("marketingName") or dev_type
                    transport = conn.get("transportType", "unknown")
                    is_wired = (transport == "wired")
                    conn_state = conn.get("state", "") or conn.get("tunnelState", "")
                    pairing_state = conn.get("pairingState", "")
                    dev_mode_raw = state.get("developerModeStatus", {})
                    dev_mode = "enabled" if (isinstance(dev_mode_raw, dict) and "enabled" in dev_mode_raw) else ("disabled" if (isinstance(dev_mode_raw, dict) and "disabled" in dev_mode_raw) else str(dev_mode_raw).lower())

                    devices.append({
                        "udid": udid,
                        "name": name,
                        "version": version_str,
                        "marketing_name": marketing_name,
                        "transport": transport,
                        "is_wired": is_wired,
                        "conn_state": conn_state,
                        "pairing_state": pairing_state,
                        "developer_mode": dev_mode,
                        "is_selected": False
                    })
        except Exception as e:
            logger.debug(f"devicectl device lookup error: {e}")

        # Determine active selected device:
        # 1. If currently selected UDID is still connected, retain it
        selected = None
        if GpsEngine._selected_udid:
            for dev in devices:
                if dev["udid"] == GpsEngine._selected_udid:
                    selected = dev
                    break

        # 2. Otherwise auto-select: prefer newly connected WIRED (USB) device, then paired wireless device
        if not selected and devices:
            devices.sort(
                key=lambda x: (
                    x["is_wired"],
                    x["developer_mode"] == "enabled",
                    x["pairing_state"] == "paired"
                ),
                reverse=True
            )
            selected = devices[0]
            GpsEngine._selected_udid = selected["udid"]

        for dev in devices:
            dev["is_selected"] = (selected is not None and dev["udid"] == selected["udid"])

        return devices

    @staticmethod
    def get_selected_device(target_udid=None):
        """Returns the specific device by UDID, or the currently active selected device."""
        devices = GpsEngine.get_all_devices()
        if target_udid:
            for dev in devices:
                if dev["udid"] == target_udid:
                    return dev

        for dev in devices:
            if dev.get("is_selected"):
                return dev

        return devices[0] if devices else None

    @staticmethod
    def select_device(udid: str):
        """Switches the active device to the given UDID."""
        GpsEngine._selected_udid = udid
        devices = GpsEngine.get_all_devices()
        selected = GpsEngine.get_selected_device(udid)
        logger.info(f"Active device changed to: {selected['name'] if selected else udid}")
        return {
            "success": True,
            "selected_udid": udid,
            "selected_device": selected,
            "devices": devices
        }

    @staticmethod
    async def get_device_info():
        """Returns summary metadata about connected devices and the selected phone."""
        devices = GpsEngine.get_all_devices()
        if not devices:
            return {
                "connected": False,
                "message": "No iPhone detected (connect via USB)",
                "devices": [],
                "selected_device": None
            }

        sel = GpsEngine.get_selected_device()
        version_str = f" (iOS {sel['version']})" if sel.get("version") else ""
        conn_tag = "USB" if sel.get("is_wired") else "Wi-Fi"
        label = f"{sel['name']}{version_str} [{conn_tag}]"

        return {
            "connected": True,
            "device_name": label,
            "selected_device": sel,
            "devices": devices,
            "device_count": len(devices),
            "model": sel.get("marketing_name", "iPhone"),
            "version": sel.get("version", ""),
            "udid": sel.get("udid", ""),
            "is_wired": sel.get("is_wired", False),
            "developer_mode": sel.get("developer_mode", "unknown")
        }

    @staticmethod
    def _wake_and_pair_device(udid: str):
        """Re-establishes CoreDevice wireless/wired tunnel if it went idle."""
        try:
            logger.info(f"Re-establishing connection link for {udid}...")
            res = subprocess.run(
                ["xcrun", "devicectl", "manage", "pair", "--device", udid, "--timeout", "8"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return res.returncode == 0
        except Exception as e:
            logger.debug(f"Auto-pair error: {e}")
            return False

    @staticmethod
    async def set_location(latitude: float, longitude: float, udid: str = None):
        """Simulates GPS coordinates on the selected or specified iPhone."""
        dev = GpsEngine.get_selected_device(udid)
        if not dev:
            return {"success": False, "message": "No iPhone connected. Connect via USB and unlock."}

        target_udid = dev["udid"]
        dev_name = dev.get("name", "Connected iPhone")
        conn_label = "USB" if dev.get("is_wired") else "Wi-Fi"

        # 1. Try native Apple devicectl first (official CoreDevice for iOS 17, 18, and beyond)
        if GpsEngine._devicectl_available():
            logger.info(f"Setting location via devicectl for {dev_name} ({target_udid}) [{conn_label}] to ({latitude}, {longitude})")
            cmd = [
                "xcrun", "devicectl", "device", "simulate", "location", "coordinate",
                "--device", target_udid,
                f"--latitude={latitude}",
                f"--longitude={longitude}"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=14)

            # If failed, check if re-pairing or wake-up helps
            if res.returncode != 0:
                err_msg = (res.stderr or res.stdout or "").strip()
                logger.info(f"Initial devicectl attempt exited with code {res.returncode}. Output: {err_msg[:120]}")

                # If assertion failed or connection dropped, try re-pair & retry once
                if "4016" in err_msg or "usage assertion" in err_msg or "could not be established" in err_msg or "unavailable" in err_msg:
                    if GpsEngine._wake_and_pair_device(target_udid):
                        logger.info("Re-pair succeeded! Retrying location simulation...")
                        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)

            if res.returncode == 0:
                logger.info(f"devicectl location set successfully on {dev_name}")
                return {"success": True, "message": f"Location shifted to ({latitude:.4f}, {longitude:.4f}) on {dev_name} ({conn_label})"}
            else:
                err_msg = (res.stderr or res.stdout or "").strip()
                logger.warning(f"devicectl failed with {err_msg}")

                # Check device lock state first (error 10003 or 'locked' or 'passcodeRequired')
                if "locked" in err_msg.lower() or "10003" in err_msg or "passcode" in err_msg.lower():
                    return {"success": False, "message": f"Please unlock {dev_name} with your passcode and keep screen on."}

                # Check if Developer Mode is actually turned off in iOS Settings (0xe800011c)
                if "0xe800011c" in err_msg.lower() or "developer mode is not enabled" in err_msg.lower():
                    return {
                        "success": False,
                        "message": f"Developer Mode is turned off on {dev_name}. On iPhone: Settings → Privacy & Security → Developer Mode → Turn ON and restart phone."
                    }

                # Check if Developer Disk Image (Cryptex) failed to mount
                if "developer disk image" in err_msg.lower() or "12040" in err_msg:
                    return {
                        "success": False,
                        "message": f"Cannot mount developer tools on {dev_name}. Unlock your iPhone screen with your passcode so Mac can connect."
                    }

                if "4016" in err_msg or "usage assertion" in err_msg:
                    return {"success": False, "message": f"Please unlock {dev_name} with your passcode."}

                if "could not be established" in err_msg or "connection reset" in err_msg.lower():
                    return {"success": False, "message": f"Could not reach {dev_name}. Ensure device is awake and connected."}

                return {"success": False, "message": f"Location error on {dev_name}: {err_msg[:80]}"}

        # 2. Fallback to pymobiledevice3
        if not PYMD3_AVAILABLE:
            return {"success": False, "message": "Location engine unavailable."}

        try:
            client = await create_using_usbmux(serial=target_udid, connection_type="USB")
            service = DtSimulateLocation(client)
            await service.set(latitude=latitude, longitude=longitude)
            logger.info(f"Successfully set location to ({latitude}, {longitude}) on {dev_name}")
            return {"success": True, "message": f"Location shifted on {dev_name} ({conn_label})"}
        except Exception as e:
            logger.error(f"pymobiledevice3 error: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}

    @staticmethod
    async def reset_location(udid: str = None):
        """Restores hardware GPS on the selected or specified iPhone."""
        dev = GpsEngine.get_selected_device(udid)
        if not dev:
            return {"success": False, "message": "No iPhone connected."}

        target_udid = dev["udid"]
        dev_name = dev.get("name", "Connected iPhone")

        # 1. Try native Apple devicectl first
        if GpsEngine._devicectl_available():
            logger.info(f"Clearing location via devicectl for {dev_name} ({target_udid})")
            cmd = [
                "xcrun", "devicectl", "device", "simulate", "location", "clear",
                "--device", target_udid
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)

            if res.returncode != 0:
                err_msg = (res.stderr or res.stdout or "").strip()
                if "4016" in err_msg or "usage assertion" in err_msg or "could not be established" in err_msg:
                    if GpsEngine._wake_and_pair_device(target_udid):
                        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)

            if res.returncode == 0:
                logger.info(f"devicectl cleared location simulation successfully on {dev_name}")
                return {"success": True, "message": f"Real GPS restored on {dev_name}."}
            else:
                err_msg = (res.stderr or res.stdout or "").strip()
                logger.warning(f"devicectl clear failed: {err_msg}")
                if "locked" in err_msg.lower():
                    return {"success": False, "message": f"Please unlock {dev_name} with passcode."}
                return {"success": False, "message": f"Could not clear location on {dev_name}."}

        # 2. Fallback to pymobiledevice3
        if not PYMD3_AVAILABLE:
            return {"success": False, "message": "Location engine unavailable."}

        try:
            client = await create_using_usbmux(serial=target_udid, connection_type="USB")
            service = DtSimulateLocation(client)
            await service.clear()
            logger.info(f"Successfully cleared simulated location on {dev_name}")
            return {"success": True, "message": f"Real GPS restored on {dev_name}."}
        except Exception as e:
            return {"success": False, "message": f"Error clearing location: {str(e)}"}


def get_local_ip():
    """Finds the Mac's primary local network IP on Wi-Fi."""
    # 1. Native macOS interface query (fastest & works offline)
    for iface in ("en0", "en1", "en2", "bridge0"):
        try:
            res = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True, timeout=1)
            ip = res.stdout.strip()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass

    # 2. Socket routing fallback
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


CURRENT_PORT = 5055
LOCAL_IP = "127.0.0.1"


class WebviewBridge:
    """JS Bridge methods exposed to pywebview and web clients."""

    def get_device_status(self):
        return asyncio.run(GpsEngine.get_device_info())

    def get_device_list(self):
        return {"success": True, "devices": GpsEngine.get_all_devices()}

    def select_device(self, udid):
        return GpsEngine.select_device(udid)

    def shift_location(self, lat, lon, udid=None):
        return asyncio.run(GpsEngine.set_location(float(lat), float(lon), udid))

    def reset_location(self, udid=None):
        return asyncio.run(GpsEngine.reset_location(udid))

    def get_network_info(self):
        ip = get_local_ip()
        return {
            "local_ip": ip,
            "port": CURRENT_PORT,
            "mobile_url": f"http://{ip}:{CURRENT_PORT}"
        }


class RestRequestHandler(SimpleHTTPRequestHandler):
    """Local HTTP Server handler serving the UI and handling JSON API calls."""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_GET(self):
        # Redirect root / to /index.html
        if self.path in ("/", ""):
            self.send_response(302)
            self.send_header("Location", "/index.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            endpoint = self.path[len("/api/"):]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            payload = json.loads(body) if body else {}
            args = payload.get("args", [])

            bridge = WebviewBridge()
            if hasattr(bridge, endpoint):
                method = getattr(bridge, endpoint)
                try:
                    result = method(*args)
                except Exception as e:
                    result = {"success": False, "message": str(e)}
            else:
                result = {"success": False, "message": f"Endpoint '{endpoint}' not found"}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        # Silence routine static asset HTTP access logs
        pass


def find_free_port(start_port=5055):
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return 5055


def start_server(port):
    global CURRENT_PORT, LOCAL_IP
    CURRENT_PORT = port
    LOCAL_IP = get_local_ip()
    # Bind to 0.0.0.0 to enable wireless access from iPhone on local Wi-Fi
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, RestRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main():
    port = find_free_port(5055)
    start_server(port)
    local_url = f"http://127.0.0.1:{port}/index.html"
    mobile_url = f"http://{LOCAL_IP}:{port}/index.html"

    logger.info(f"OpenGo local server started at {local_url}")
    logger.info(f"📱 Wireless access from iPhone: {mobile_url}")
    print("\n" + "=" * 60)
    print(" 📍 OpenGo is Running Wirelessly!")
    print(f" • Mac App URL:       {local_url}")
    print(f" • iPhone Safari URL: {mobile_url}")
    print(" Tip: Open the iPhone URL in Safari and tap 'Add to Home Screen'")
    print("=" * 60 + "\n")

    # Check for pywebview to show native macOS window
    try:
        import webview
        bridge = WebviewBridge()
        window = webview.create_window(
            title="OpenGo",
            url=local_url,
            js_api=bridge,
            width=1020,
            height=720,
            min_size=(750, 520),
            text_select=False
        )
        logger.info("Opening native WebKit window...")
        webview.start()
    except Exception as e:
        logger.warning(f"Native window could not start ({e}). Opening in default browser...")
        import webbrowser
        webbrowser.open(local_url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            print("\nExiting OpenGo...")


if __name__ == "__main__":
    main()
