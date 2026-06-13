import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.preflight import PreFlightDiagnostic

def main():
    print("\n" + "="*50)
    print(" 🚀 INVESTOR PITCH: PRE-FLIGHT DIAGNOSTIC")
    print("="*50 + "\n")
    
    diagnostic = PreFlightDiagnostic()
    results = diagnostic.run_all()
    
    all_passed = True
    for check, (success, message) in results.items():
        icon = "✅" if success else "❌"
        if not success:
            all_passed = False
        print(f"{icon} {check:12}: {message}")
        
    print("\n" + "="*50)
    if all_passed:
        print(" 🌟 READY FOR PITCH DEMO! SYSTEM GREEN 🌟")
    else:
        print(" ⚠️  SYSTEM BLOCKED: ACTION REQUIRED ⚠️")
    print("="*50 + "\n")
    
    if not all_passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
