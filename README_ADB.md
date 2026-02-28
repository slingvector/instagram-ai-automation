# MCR Publishing Edge - Wireless ADB Setup

To connect a new Android 11+ device wirelessly:

1. Connect your Android device and this Mac to the **SAME WiFi network**.
2. Go to Developer Options -> **Wireless Debugging**.
3. Run the helper script:
   ```bash
   ./setup_adb_wireless.sh
   ```
4. Follow the on-screen prompts to enter the IP:Port for pairing and connecting.
5. Once connected (`adb devices` shows your device), start Appium:
   ```bash
   docker compose -f docker-compose.appium.yml up -d
   ```
