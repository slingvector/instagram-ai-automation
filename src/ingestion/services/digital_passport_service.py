import logging
import hashlib
from typing import Optional
from pathlib import Path

from src.ingestion.repositories.web3_repository import Web3Repository

logger = logging.getLogger(__name__)

class DigitalPassportService:
    """
    Business logic layer for generating immutable Proof of Authenticity for generated Reels.
    Reads the raw video file and caption, generates a cryptographic SHA-256 hash, 
    and passes it to the Web3Repository to stamp on-chain.
    """

    def __init__(self, web3_repo: Optional[Web3Repository] = None):
        self.repo = web3_repo or Web3Repository()

    def generate_and_mint_passport(self, video_path: str, caption_text: str) -> str:
        """
        Reads the video bytes and the caption, creates a combined SHA-256 hash, 
        and instructs the blockchain repository to permanently inscribe it.
        """
        logger.info(f"Generating Digital Passport for video: {video_path}")
        
        if not Path(video_path).exists():
            logger.error(f"Video file not found at {video_path}")
            return ""

        try:
            # 1. Generate SHA-256 Hash of the Video File
            sha256_hash = hashlib.sha256()
            with open(video_path, "rb") as f:
                # Read in chunks to avoid memory spikes with large MP4 files
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            video_hash = sha256_hash.hexdigest()

            # 2. Combine with the text caption
            combined_string = f"{video_hash}:{caption_text}"
            final_passport_hash = hashlib.sha256(combined_string.encode('utf-8')).hexdigest()
            
            logger.info(f"Generated Cryptographic Passport Hash: {final_passport_hash}")

            # 3. Mint / Inscribe on Testnet
            tx_receipt = self.repo.inscribe_hash_on_chain(final_passport_hash)
            return tx_receipt
            
        except Exception as e:
            logger.error(f"Failed to generate Digital Passport: {e}")
            return ""
