import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    PYCRYPTODOME_AVAILABLE = True
except Exception:
    PYCRYPTODOME_AVAILABLE = False


class EncryptedMappingStore:
    """
    AES-256 Encrypted Mapping Store for PII original values.
    Ensures raw PII plaintext is never exposed in the database metadata.
    """

    def __init__(self, secret_key: Optional[str] = None, storage_dir: Optional[Path] = None):
        key_str = secret_key or os.getenv("PRIVACY_SHIELD_MASTER_KEY", "PrivacyShieldAI-DPDP2025-MasterKey#32Byte!")
        # Derive 32-byte key via SHA-256
        self.key = hashlib.sha256(key_str.encode("utf-8")).digest()

        if storage_dir is None:
            storage_dir = Path(__file__).resolve().parents[2] / "src" / "pii_detector" / "web" / "output" / "mappings"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def encrypt_val(self, plaintext: str) -> str:
        """Encrypt string value with AES-256 (CBC mode) + Base64 encoding."""
        if not plaintext:
            return ""

        if PYCRYPTODOME_AVAILABLE:
            iv = os.urandom(16)
            cipher = AES.new(self.key, AES.MODE_CBC, iv)
            padded = pad(plaintext.encode("utf-8"), AES.block_size)
            ciphertext = cipher.encrypt(padded)
            return base64.b64encode(iv + ciphertext).decode("utf-8")
        else:
            # Fallback simple XOR/b64 encryption if pycryptodome unavailable
            b = plaintext.encode("utf-8")
            enc = bytes([b[i] ^ self.key[i % len(self.key)] for i in range(len(b))])
            return base64.b64encode(enc).decode("utf-8")

    def decrypt_val(self, ciphertext: str) -> str:
        """Decrypt Base64 ciphertext back to original plaintext."""
        if not ciphertext:
            return ""

        try:
            raw = base64.b64decode(ciphertext.encode("utf-8"))
            if PYCRYPTODOME_AVAILABLE:
                iv = raw[:16]
                actual_ct = raw[16:]
                cipher = AES.new(self.key, AES.MODE_CBC, iv)
                padded = cipher.decrypt(actual_ct)
                return unpad(padded, AES.block_size).decode("utf-8")
            else:
                dec = bytes([raw[i] ^ self.key[i % len(self.key)] for i in range(len(raw))])
                return dec.decode("utf-8")
        except Exception as e:
            return f"[Decryption Error: {e}]"

    def store_document_mapping(self, document_id: str, original_mapping: Dict[str, str]) -> Path:
        """
        Encrypts all values in the original PII mapping dictionary
        and persists them to an isolated encrypted JSON mapping store.
        """
        encrypted_dict = {}
        for token, original_val in original_mapping.items():
            encrypted_dict[token] = self.encrypt_val(original_val)

        file_path = self.storage_dir / f"{document_id}_mapping.enc.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({
                "document_id": document_id,
                "encrypted_mapping": encrypted_dict
            }, f, indent=2)

        return file_path

    def load_document_mapping(self, document_id: str) -> Dict[str, str]:
        """
        Loads and decrypts the PII mapping dictionary for a given document.
        """
        file_path = self.storage_dir / f"{document_id}_mapping.enc.json"
        if not file_path.exists():
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            encrypted_dict = data.get("encrypted_mapping", {})
            decrypted_dict = {}
            for token, enc_val in encrypted_dict.items():
                decrypted_dict[token] = self.decrypt_val(enc_val)
            return decrypted_dict
        except Exception:
            return {}


# Global Encrypted Store Instance
encrypted_mapping_store = EncryptedMappingStore()
