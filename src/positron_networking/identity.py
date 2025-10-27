"""
Cryptographic identity management using Ed25519 signatures.
"""
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import os
import hashlib
from typing import Tuple, Optional


class Identity:
    """Manages cryptographic identity for a node."""
    
    def __init__(self, private_key: ed25519.Ed25519PrivateKey):
        """
        Initialize identity with a private key.
        
        Args:
            private_key: Ed25519 private key
        """
        self.private_key = private_key
        self.public_key = private_key.public_key()
        self._node_id = self._generate_node_id()
    
    @property
    def node_id(self) -> str:
        """Get the unique node identifier derived from public key."""
        return self._node_id
    
    def _generate_node_id(self) -> str:
        """Generate a unique node ID from the public key."""
        public_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        # Use SHA256 hash of public key as node ID
        hash_digest = hashlib.sha256(public_bytes).hexdigest()
        return hash_digest[:16]  # Use first 16 chars for readability
    
    def sign(self, data: bytes) -> bytes:
        """
        Sign data with the private key.
        
        Args:
            data: Data to sign
            
        Returns:
            Signature bytes
        """
        return self.private_key.sign(data)
    
    def verify(self, public_key_bytes: bytes, data: bytes, signature: bytes) -> bool:
        """
        Verify a signature using a public key.
        
        Args:
            public_key_bytes: Public key in raw format
            data: Original data that was signed
            signature: Signature to verify
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            public_key.verify(signature, data)
            return True
        except (InvalidSignature, Exception):
            return False
    
    def get_public_key_bytes(self) -> bytes:
        """
        Get the public key as raw bytes.
        
        Returns:
            Public key bytes
        """
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def save_keys(self, private_key_path: str, public_key_path: str):
        """
        Save keys to files.
        
        Args:
            private_key_path: Path to save private key
            public_key_path: Path to save public key
        """
        # Ensure directories exist
        os.makedirs(os.path.dirname(private_key_path), exist_ok=True)
        os.makedirs(os.path.dirname(public_key_path), exist_ok=True)
        
        # Save private key
        private_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        with open(private_key_path, "wb") as f:
            f.write(private_pem)
        
        # Set restrictive permissions on private key
        os.chmod(private_key_path, 0o600)
        
        # Save public key
        public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        with open(public_key_path, "wb") as f:
            f.write(public_pem)
    
    @classmethod
    def generate(cls) -> "Identity":
        """
        Generate a new identity with a fresh key pair.
        
        Returns:
            New Identity instance
        """
        private_key = ed25519.Ed25519PrivateKey.generate()
        return cls(private_key)
    
    @classmethod
    def load_from_files(cls, private_key_path: str) -> "Identity":
        """
        Load identity from a private key file.
        
        Args:
            private_key_path: Path to private key file
            
        Returns:
            Identity instance loaded from file
        """
        with open(private_key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=None
            )
        
        if not isinstance(private_key, ed25519.Ed25519PrivateKey):
            raise ValueError("Key file does not contain an Ed25519 private key")
        
        return cls(private_key)
    
    @classmethod
    def load_or_generate(cls, private_key_path: str, public_key_path: str) -> "Identity":
        """
        Load identity from file or generate a new one if it doesn't exist.
        
        Args:
            private_key_path: Path to private key file
            public_key_path: Path to public key file
            
        Returns:
            Identity instance
        """
        if os.path.exists(private_key_path):
            return cls.load_from_files(private_key_path)
        else:
            identity = cls.generate()
            identity.save_keys(private_key_path, public_key_path)
            return identity


def derive_node_id_from_public_key(public_key_bytes: bytes) -> str:
    """
    Derive a node ID from a public key.
    
    Args:
        public_key_bytes: Public key in raw format
        
    Returns:
        Node ID string
    """
    hash_digest = hashlib.sha256(public_key_bytes).hexdigest()
    return hash_digest[:16]
