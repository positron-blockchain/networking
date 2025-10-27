"""
Unit tests for the identity module.
"""
import pytest
import tempfile
import os
from pathlib import Path

from positron_networking.identity import Identity, derive_node_id_from_public_key


def test_identity_generation():
    """Test generating a new identity."""
    identity = Identity.generate()
    
    assert identity is not None
    assert identity.node_id is not None
    assert len(identity.node_id) == 16  # First 16 chars of hash
    assert identity.private_key is not None
    assert identity.public_key is not None


def test_identity_signing():
    """Test signing and verification."""
    identity = Identity.generate()
    
    data = b"Hello, decentralized world!"
    signature = identity.sign(data)
    
    assert signature is not None
    assert len(signature) > 0
    
    # Verify with public key
    public_key_bytes = identity.get_public_key_bytes()
    assert identity.verify(public_key_bytes, data, signature)
    
    # Verification should fail with wrong data
    assert not identity.verify(public_key_bytes, b"Different data", signature)


def test_identity_persistence():
    """Test saving and loading identity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = os.path.join(tmpdir, "keys", "private_key.pem")
        public_key_path = os.path.join(tmpdir, "keys", "public_key.pem")
        
        # Create and save identity
        identity1 = Identity.generate()
        identity1.save_keys(private_key_path, public_key_path)
        
        # Load identity
        identity2 = Identity.load_from_files(private_key_path)
        
        # Should have same node ID
        assert identity1.node_id == identity2.node_id
        
        # Should be able to verify signatures
        data = b"Test data"
        signature = identity1.sign(data)
        
        public_key_bytes = identity2.get_public_key_bytes()
        assert identity2.verify(public_key_bytes, data, signature)


def test_load_or_generate():
    """Test load_or_generate functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = os.path.join(tmpdir, "keys", "private_key.pem")
        public_key_path = os.path.join(tmpdir, "keys", "public_key.pem")
        
        # First call should generate
        identity1 = Identity.load_or_generate(private_key_path, public_key_path)
        node_id1 = identity1.node_id
        
        # Second call should load
        identity2 = Identity.load_or_generate(private_key_path, public_key_path)
        node_id2 = identity2.node_id
        
        # Should be the same identity
        assert node_id1 == node_id2


def test_derive_node_id():
    """Test node ID derivation from public key."""
    identity = Identity.generate()
    public_key_bytes = identity.get_public_key_bytes()
    
    derived_id = derive_node_id_from_public_key(public_key_bytes)
    
    assert derived_id == identity.node_id
    assert len(derived_id) == 16


def test_different_identities_have_different_ids():
    """Test that different identities have different node IDs."""
    identity1 = Identity.generate()
    identity2 = Identity.generate()
    
    assert identity1.node_id != identity2.node_id
