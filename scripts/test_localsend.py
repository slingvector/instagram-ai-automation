import os
import time
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG)

load_dotenv()

from src.utils.localsend_service import LocalSendService, AdbHelper

def run_test():
    test_file = "data/test_localsend_file.txt"
    with open(test_file, "w") as f:
        f.write("Hello! This is an automated LocalSend relay test.")

    ip = os.getenv("LOCALSEND_TARGET_IP", "192.168.1.240")
    alias = os.getenv("LOCALSEND_ALIAS", "Cute Lettuce")
    adb_port = os.getenv("ADB_PORT", "5555")

    print(f"==========================================")
    print(f"Testing LocalSend to {ip} (alias: {alias})")
    print(f"ADB Port: {adb_port}")
    print(f"==========================================\n")

    service = LocalSendService(target_ip=ip, target_alias=alias)
    success = service.push([test_file])

    if success:
        print("\n✅ LocalSend push Succeeded!")
    else:
        print("\n❌ LocalSend push Failed!")

if __name__ == "__main__":
    run_test()
