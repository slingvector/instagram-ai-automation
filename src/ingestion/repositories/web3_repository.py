import logging
import os
from web3 import Web3
from web3.middleware import geth_poa_middleware
from typing import Optional

logger = logging.getLogger(__name__)

class Web3Repository:
    """
    Repository layer for interacting with EVM-compatible blockchains
    (e.g., Polygon Amoy Testnet or Ethereum Sepolia).
    Follows SRP by handling only the raw node connection and transaction signing.
    """

    def __init__(self, rpc_url: Optional[str] = None, private_key: Optional[str] = None):
        self.rpc_url = rpc_url or os.getenv("WEB3_RPC_URL")
        self.private_key = private_key or os.getenv("WEB3_PRIVATE_KEY")
        
        if not self.rpc_url or not self.private_key:
            logger.warning("WEB3 credentials missing. Testnet Minting will fail safely.")
            self.w3 = None
            return

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        # Inject PoA middleware to support chains like Polygon 
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        # Extract actual public address from Private Key securely
        from eth_account import Account
        self.account = Account.from_key(self.private_key)

        if self.w3.is_connected():
            logger.info(f"Connected to Web3 Node using wallet: {self.account.address}")
        else:
            logger.error("Failed to connect to the provided Web3 RPC URL.")
            self.w3 = None

    def inscribe_hash_on_chain(self, metadata_hash: str) -> str:
        """
        Instead of managing a complex Smart Contract ABI for this testnet feature, 
        we directly inscribe the SHA-256 Digital Passport Hash into the transaction's 
        'data' field in a 0-value self-transfer. This achieves immutable Proof of Authenticity.
        """
        if not self.w3:
            logger.error("Cannot mint: Web3 is not connected.")
            return ""

        logger.info(f"Inscribing Digital Passport Hash onto blockchain: {metadata_hash}")

        try:
            # Convert the SHA-256 hash string into bytes for the transaction payload
            encoded_data = metadata_hash.encode('utf-8')

            tx = {
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'to': self.account.address, # Send to self
                'value': 0,
                'gas': 2000000,
                'gasPrice': self.w3.eth.gas_price,
                'data': encoded_data,
                'chainId': self.w3.eth.chain_id
            }

            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Convert bytes to hex string (e.g., 0x123abc...)
            tx_receipt_id = self.w3.to_hex(tx_hash)
            logger.info(f"Successfully inscribed! Transaction Hash: {tx_receipt_id}")
            
            return tx_receipt_id

        except Exception as e:
            logger.error(f"Failed to inscribe hash on blockchain: {e}")
            return ""
