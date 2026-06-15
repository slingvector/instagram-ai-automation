import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("--- Step 1: Raw os.environ ---")
print(f"APPIUM_HOST: {os.getenv('APPIUM_HOST')}")

print("\n--- Step 2: load_dotenv() ---")
load_dotenv()
print(f"APPIUM_HOST: {os.getenv('APPIUM_HOST')}")

print("\n--- Step 3: src.publishing_edge.config ---")
from src.publishing_edge.config import APPIUM_HOST
print(f"APPIUM_HOST: {APPIUM_HOST}")
