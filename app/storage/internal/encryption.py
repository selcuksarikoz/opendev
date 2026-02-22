from cryptography.fernet import Fernet
import keyring
from pathlib import Path

class EncryptionManager:
    def __init__(self, key_file: Path):
        self.key_file = key_file
        enc_key = self._get_persistent_key()
        self.cipher = Fernet(enc_key)

    def _get_persistent_key(self) -> bytes:
        if self.key_file.exists():
            return self.key_file.read_bytes()

        key = keyring.get_password("opendev_cli", "encryption_key")
        if key:
            new_key = key.encode()
            self.key_file.write_bytes(new_key)
            return new_key

        new_key = Fernet.generate_key()
        try:
            keyring.set_password("opendev_cli", "encryption_key", new_key.decode())
        except:
            pass
        self.key_file.write_bytes(new_key)
        return new_key

    def encrypt(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        return self.cipher.decrypt(encrypted_data.encode()).decode()
