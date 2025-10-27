"""
Unit tests for the protocol module.
"""
import pytest
import time

from positron_networking.protocol import (
    Message, MessageType, MessageFactory, PeerInfo
)


def test_message_creation():
    """Test creating a basic message."""
    message = Message(
        msg_type=MessageType.HEARTBEAT,
        sender_id="test_node",
        timestamp=time.time(),
        payload={"test": "data"}
    )
    
    assert message is not None
    assert message.message_id is not None
    assert message.ttl == 10


def test_message_serialization():
    """Test message serialization and deserialization."""
    original = Message(
        msg_type=MessageType.HEARTBEAT,
        sender_id="test_node",
        timestamp=time.time(),
        payload={"test": "data"},
        signature=b"fake_signature"
    )
    
    # Serialize
    data = original.to_bytes()
    assert isinstance(data, bytes)
    
    # Deserialize
    recovered = Message.from_bytes(data)
    
    assert recovered.msg_type == original.msg_type
    assert recovered.sender_id == original.sender_id
    assert recovered.message_id == original.message_id
    assert recovered.payload == original.payload
    assert recovered.signature == original.signature


def test_message_factory_handshake():
    """Test creating handshake message."""
    message = MessageFactory.create_handshake(
        "node_123",
        b"public_key_bytes",
        "192.168.1.1:8888"
    )
    
    assert message.msg_type == MessageType.HANDSHAKE
    assert message.sender_id == "node_123"
    assert message.payload["public_key"] == b"public_key_bytes"
    assert message.payload["address"] == "192.168.1.1:8888"


def test_message_factory_gossip():
    """Test creating gossip message."""
    data = {"important": "information"}
    message = MessageFactory.create_gossip_message("node_123", data, ttl=5)
    
    assert message.msg_type == MessageType.GOSSIP_MESSAGE
    assert message.sender_id == "node_123"
    assert message.payload["data"] == data
    assert message.ttl == 5


def test_peer_info():
    """Test PeerInfo dataclass."""
    peer = PeerInfo(
        node_id="peer_123",
        address="192.168.1.2:8888",
        public_key=b"peer_public_key",
        trust_score=0.8
    )
    
    assert peer.node_id == "peer_123"
    assert peer.address == "192.168.1.2:8888"
    assert peer.trust_score == 0.8
    
    # Test dict conversion
    peer_dict = peer.to_dict()
    assert peer_dict["node_id"] == "peer_123"
    
    # Test from dict
    peer2 = PeerInfo.from_dict(peer_dict)
    assert peer2.node_id == peer.node_id
    assert peer2.trust_score == peer.trust_score


def test_message_ttl_handling():
    """Test TTL in messages."""
    message = MessageFactory.create_gossip_message("node_123", {"data": "test"}, ttl=3)
    
    assert message.ttl == 3
    
    # Simulate propagation
    message.ttl -= 1
    assert message.ttl == 2
    
    message.ttl -= 1
    assert message.ttl == 1
    
    message.ttl -= 1
    assert message.ttl == 0


def test_message_id_uniqueness():
    """Test that message IDs are unique."""
    msg1 = MessageFactory.create_heartbeat("node_123")
    msg2 = MessageFactory.create_heartbeat("node_123")
    
    # Different timestamps should lead to different IDs
    assert msg1.message_id != msg2.message_id
