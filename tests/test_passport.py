import sys
import os

# Ensure the src folder is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ingestion.services.digital_passport_service import DigitalPassportService
import logging
logging.basicConfig(level=logging.INFO)

def test_passport():
    service = DigitalPassportService()
    
    # Create a dummy video file
    with open("dummy_video.mp4", "wb") as f:
        f.write(b"fake video data 12345")
        
    caption = "Test automated Web3 minting #nft !!"
    
    print("Minting Digital Passport for dummy video...")
    tx_hash = service.generate_and_mint_passport("dummy_video.mp4", caption)
    
    print(f"\nResult Transaction Hash: {tx_hash}")
    os.remove("dummy_video.mp4")

if __name__ == "__main__":
    test_passport()
