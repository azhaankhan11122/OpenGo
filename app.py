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
    """Manages the raw Apple developer location simulation service."""

    @staticmethod
    def _devicectl_available():
        return shutil.which("xcrun") is not None

    @staticmethod
    def _get_devicectl_device():
        """Finds the connected physical iOS device via devicectl."""
        try:
            res = subprocess.run(
                ["xcrun", "devicectl", "list", "devices", "--json-output", "-"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                devices = data.get("result", {}).get("devices", [])
                candidates = []
                for d in devices:
                    props = d.get("properties", {})
                    hw = props.get("hardware", {}) or d.get("hardwareProperties", {})
                    conn = props.get("connection", {}) or d.get("connectionProperties", {})
                    state = props.get("state", {}) or d.get("deviceProperties", {})
                    sw = props.get("software", {})
                    
                    platform = hw.get("platform", "")
                    dev_type = hw.get("deviceType", "")
                    pairing_state = conn.get("pairingState", "")
                    conn_state = conn.get("state", "") or conn.get("tunnelState", "")
                    
                    if platform == "iOS":
                        udid = hw.get("udid") or d.get("identifier")
                        name = state.get("name") or "Connected iOS Device"
                        version_str = sw.get("osVersionNumber", {}).get("stringValue") or state.get("osVersionNumber", "")
                        candidates.append({
                            "udid": udid,
                            "name": name,
                            "version": version_str,
                            "marketing_name": hw.get("marketingName") or dev_type or "iPhone",
                            "is_iphone": dev_type.lower() == "iphone",
                            "is_paired": pairing_state == "paired",
                            "is_connected": conn_state == "connected",
                        })
                
                # Priority: paired physical iPhone > any iPhone > any paired iOS device > any iOS candidate
                candidates.sort(key=lambda x: (x["is_paired"], x["is_iphone"], x["is_connected"]), reverse=True)
                if candidates:
                    return candidates[0]
        except Exception as e:
            logger.debug(f"devicectl device lookup error: {e}")
        return None

    @staticmethod
    async def get_device_info():
        """Returns metadata about the currently connected USB device."""
        # 1. Try native Apple devicectl first (official CoreDevice support for iOS 17 & 18)
        if GpsEngine._devicectl_available():
            dev = GpsEngine._get_devicectl_device()
            if dev:
                version_str = f" (iOS {dev['version']})" if dev['version'] else ""
                return {
                    "connected": True,
                    "device_name": f"{dev['name']}{version_str}",
                    "model": dev['marketing_name'],
                    "version": dev['version'],
                    "udid": dev['udid']
                }

        # 2. Try pymobiledevice3 fallback
        if not PYMD3_AVAILABLE:
            return {"connected": False, "message": "No iPhone connected via USB"}

        try:
            client = await create_using_usbmux(connection_type="USB")
            vals = await client.get_value()
            name = vals.get("DeviceName", "Connected iPhone")
            version = vals.get("ProductVersion", "")
            model = vals.get("ProductType", "iPhone")
            return {
                "connected": True,
                "device_name": f"{name} (iOS {version})",
                "model": model,
                "version": version
            }
        except NoDeviceConnectedError:
            return {"connected": False, "message": "No iPhone connected via USB"}
        except PasscodeRequiredError:
            return {"connected": False, "message": "Please unlock your iPhone"}
        except (NotPairedError, NotTrustedError):
            return {"connected": False, "message": "Please tap 'Trust This Computer' on iPhone"}
        except Exception as e:
            return {"connected": False, "message": f"Connection check: {str(e)}"}

    @staticmethod
    async def set_location(latitude: float, longitude: float):
        """Simulates GPS coordinates on the connected iPhone."""
        # 1. Try native Apple devicectl first (flawless on iOS 17 and 18)
        if GpsEngine._devicectl_available():
            dev = GpsEngine._get_devicectl_device()
            if dev and dev.get("udid"):
                udid = dev["udid"]
                logger.info(f"Setting location via devicectl for {dev['name']} ({udid}) to ({latitude}, {longitude})")
                res = subprocess.run([
                    "xcrun", "devicectl", "device", "simulate", "location", "coordinate",
                    "--device", udid,
                    f"--latitude={latitude}",
                    f"--longitude={longitude}"
                ], capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    logger.info(f"devicectl location set successfully: {res.stdout.strip()}")
                    return {"success": True, "message": f"Location shifted to ({latitude:.4f}, {longitude:.4f})"}
                else:
                    err_msg = (res.stderr or res.stdout or "").strip()
                    logger.warning(f"devicectl failed with {err_msg}")
                    if "4016" in err_msg or "usage assertion" in err_msg:
                        return {"success": False, "message": "Please unlock your iPhone screen with passcode."}
                    if "could not be established" in err_msg or "Connection reset" in err_msg:
                        return {"success": False, "message": "Could not reach iPhone. Ensure device is awake and on same Wi-Fi."}

        # 2. Fallback to pymobiledevice3
        if not PYMD3_AVAILABLE:
            return {"success": False, "message": "Location engine unavailable."}

        try:
            client = await create_using_usbmux(connection_type="USB")
            service = DtSimulateLocation(client)
            await service.set(latitude=latitude, longitude=longitude)
            logger.info(f"Successfully set location to ({latitude}, {longitude})")
            return {"success": True, "message": f"Location shifted to ({latitude:.4f}, {longitude:.4f})"}
        except Exception as e:
            logger.error(f"pymobiledevice3 error: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}

    @staticmethod
    async def reset_location():
        """Restores hardware GPS on the connected iPhone."""
        # 1. Try native Apple devicectl first
        if GpsEngine._devicectl_available():
            dev = GpsEngine._get_devicectl_device()
            if dev and dev.get("udid"):
                udid = dev["udid"]
                logger.info(f"Clearing location via devicectl for {dev['name']}")
                res = subprocess.run([
                    "xcrun", "devicectl", "device", "simulate", "location", "clear",
                    "--device", udid
                ], capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    logger.info("devicectl cleared location simulation successfully.")
                    return {"success": True, "message": "Real GPS restored."}
                else:
                    err_msg = (res.stderr or res.stdout or "").strip()
                    logger.warning(f"devicectl clear failed: {err_msg}")
                    if "4016" in err_msg or "usage assertion" in err_msg:
                        return {"success": False, "message": "Please unlock your iPhone screen with passcode."}

        # 2. Fallback to pymobiledevice3
        if not PYMD3_AVAILABLE:
            return {"success": False, "message": "Location engine unavailable."}

        try:
            client = await create_using_usbmux(connection_type="USB")
            service = DtSimulateLocation(client)
            await service.clear()
            logger.info("Successfully cleared simulated location")
            return {"success": True, "message": "Real GPS restored."}
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

    def shift_location(self, lat, lon):
        return asyncio.run(GpsEngine.set_location(float(lat), float(lon)))

    def reset_location(self):
        return asyncio.run(GpsEngine.reset_location())

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
