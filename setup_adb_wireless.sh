#!/bin/bash

# MCR - Wireless ADB Setup Helper (Android 11+)
# 
# Android 11+ requires a pairing code flow for wireless ADB.
# This script guides you through the process and connects your device.

echo "======================================================"
echo "📱 MCR Wireless ADB Setup Helper (Android 11+)"
echo "======================================================"
echo ""
echo "Before starting, ensure:"
echo "1. Your Android device and this Mac are on the SAME WiFi network."
echo "2. Developer Options are enabled on your device."
echo "3. 'Wireless Debugging' is turned ON in Developer Options."
echo ""
read -p "Press Enter when ready or Ctrl+C to abort..."

echo ""
echo "Step 1: Get Pairing Details"
echo "---------------------------"
echo "On your device, tap on the words 'Wireless debugging' (not just the toggle)."
echo "Then tap 'Pair device with pairing code'."
echo ""
read -p "Enter the IP address and Port shown on that screen (e.g., 192.168.1.10:34567): " PAIRING_IP_PORT

read -p "Enter the 6-digit Wi-Fi pairing code: " PAIRING_CODE

echo ""
echo "Step 2: Pairing Device"
echo "----------------------"
echo "Running: adb pair $PAIRING_IP_PORT"

# Use expect to automate the pairing code prompt, or just run it directly
# adb pair prompts for the code interactively if not provided
adb pair $PAIRING_IP_PORT $PAIRING_CODE

echo ""
echo "Step 3: Connect Device"
echo "----------------------"
echo "Now look at the main 'Wireless debugging' screen (where the toggle is)."
echo "Under 'IP address & Port', you will see a DIFFERENT port number."
echo ""
read -p "Enter that new IP address and Port (e.g., 192.168.1.10:45678): " CONNECT_IP_PORT

echo ""
echo "Running: adb connect $CONNECT_IP_PORT"
adb connect $CONNECT_IP_PORT

echo ""
echo "Step 4: Verify Connection"
echo "-------------------------"
adb devices

echo ""
echo "✅ If you see your device IP listed as 'device', you are ready!"
echo "   You can now start the Appium server:"
echo "   docker compose -f docker-compose.appium.yml up -d"
echo "======================================================"
