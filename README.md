# 📍 OpenGo

A minimal, clean, and 100% private GPS location pinpointing tool for iOS devices on macOS.

No logins. No subscriptions. No background analytics or telemetry. Just pure, direct location simulation using Apple's official Developer CoreDevice protocols.

---

## ✨ Features

- **🎯 Minimalist & Focused**: No unnecessary routing bloat or complicated routes—just click on the map and pinpoint your exact location.
- **🔒 100% Local & Private**: Runs completely on your Mac over local USB or Wi-Fi sync. Zero telemetry, zero analytics, zero accounts.
- **⚡ Native Developer Protocol**: Utilizes Apple's high-speed `devicectl` (CoreDevice) for iOS 17 and iOS 18+, with automatic fallback for older iOS versions.
- **🗺️ Interactive Map**: Minimalist dark-themed map with OpenStreetMap and Esri Satellite layers (no API keys required).
- **🔍 Quick Search**: Search any city, address, or landmark worldwide, or directly enter exact coordinates (`latitude, longitude`).
- **🔄 Instant Reset**: One click to immediately clear the simulated location and restore real satellite GPS.
- **🍏 Native macOS App**: Packaged as a first-class macOS `.app` bundle that you can launch directly from Spotlight (`Cmd + Space`), Launchpad, or the Applications folder.

---

## 📋 Prerequisites

1. **macOS**: Apple Silicon (M1/M2/M3/M4) or Intel Mac running macOS 12+.
2. **Xcode Command Line Tools**: Needed for Apple's `xcrun devicectl`.
   ```bash
   xcode-select --install
   ```
3. **iPhone Developer Mode Enabled**:
   - On your iPhone, open **Settings** → **Privacy & Security** → scroll to **Developer Mode**.
   - Toggle it **ON** and follow the prompt to restart your device.
   - When plugging into your Mac, tap **Trust This Computer**.

---

## 🚀 Quick Start

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/azhaankhan11122/OpenGo.git
cd OpenGo

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Launch OpenGo

```bash
./run.sh
```

---

## 📦 Build as a Native macOS App

To build a standalone `.app` bundle that installs into `/Applications` (so you can find it with Spotlight `Cmd + Space`):

```bash
./build_app.sh
```

Once built, open Spotlight (`Cmd + Space`), type **OpenGo**, and press Enter!

---

## 📱 Wireless iPhone Mode (Cable-Free Control)

You do **not** need to keep your iPhone plugged in with a cable to shift location!

### How to use OpenGo wirelessly:
1. **Enable Network Connection in Xcode (One-time setup)**:
   - Connect your iPhone to your Mac via USB once.
   - Open **Xcode** → **Window** → **Devices and Simulators** (`Cmd + Shift + 2`).
   - Select your iPhone and check the box: **"Connect via network"**.
   - You can now unplug the cable! Your iPhone and Mac just need to be on the same Wi-Fi network (or iPhone Personal Hotspot).

2. **Open on your iPhone**:
   - Launch OpenGo on your Mac.
   - Click the **📱 Wireless** button in the app (or look at the URL printed in the terminal).
   - Point your iPhone Camera at the QR code (or type the `http://<mac-ip>:5055` URL into Safari).

3. **Install as a Full-Screen iPhone App (PWA)**:
   - In Safari on your iPhone, tap the **Share** button (⎋).
   - Scroll down and tap **"Add to Home Screen"**.
   - OpenGo will appear as a native app icon on your iPhone home screen!
   - Tap it anytime to open full-screen, drop a pin, and shift your location without ever touching your Mac!

---

## 🛠️ How It Works Under The Hood

Unlike commercial tools that bundle closed-source binaries, inject invasive drivers, or require third-party servers:
- **OpenGo** interfaces directly with the native Apple CoreDevice service on iOS (`com.apple.dt.simulatelocation`).
- For modern iOS 17 and 18 releases, it executes commands via Apple's native `devicectl` architecture with zero DDI mounting delays (<200ms latency).
- Location requests are handled 100% locally through a lightweight WebKit bridge.

---

## 🗺️ Roadmap & Upcoming Features

- [ ] **Saved Favorites**: Bookmark frequently used locations locally with custom labels.
- [ ] **Natural Micro-Drift**: Subtle 1–2m GPS variance toggle to simulate natural satellite jitter and bypass static mock-location detection.
- [ ] **Altitude Simulation**: Elevation matching for hilly or mountainous coordinates.
- [ ] **macOS Menu Bar Mode**: Lightweight tray icon for one-click location shifting without keeping the main map window open.
- [ ] **Pre-built `.dmg` Releases**: Direct downloadable standalone disk images.

---

## 📄 License

MIT License. Free and open source for everyone.
