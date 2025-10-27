"""
Network protocol message types and serialization.
"""
from enum import IntEnum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import msgpack
import time
import hashlib


class MessageType(IntEnum):
    """Types of messages in the network."""
    HANDSHAKE = 1
    HANDSHAKE_ACK = 2
    HEARTBEAT = 3
    PEER_DISCOVERY = 4
    PEER_ANNOUNCEMENT = 5
    GOSSIP_MESSAGE = 6
    TRUST_UPDATE = 7
    TRUSTED_PEERS_REQUEST = 8
    TRUSTED_PEERS_RESPONSE = 9
    DISCONNECT = 10
    CUSTOM_DATA = 11


@dataclass
class PeerInfo:
    """Information about a peer."""
    node_id: str
    address: str  # Format: "host:port"
    public_key: bytes
    last_seen: float = field(default_factory=time.time)
    trust_score: float = 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "address": self.address,
            "public_key": self.public_key,
            "last_seen": self.last_seen,
            "trust_score": self.trust_score,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PeerInfo":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class Message:
    """Base message structure for all network communication."""
    msg_type: int
    sender_id: str
    timestamp: float
    payload: Dict[str, Any]
    signature: Optional[bytes] = None
    message_id: Optional[str] = None
    ttl: int = 10
    
    def __post_init__(self):
        """Generate message ID if not provided."""
        if self.message_id is None:
            self.message_id = self._generate_message_id()
    
    def _generate_message_id(self) -> str:
        """Generate a unique message ID."""
        data = f"{self.sender_id}{self.timestamp}{self.msg_type}{str(self.payload)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def to_bytes(self) -> bytes:
        """Serialize message to bytes using msgpack."""
        data = {
            "msg_type": self.msg_type,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "signature": self.signature,
            "message_id": self.message_id,
            "ttl": self.ttl,
        }
        return msgpack.packb(data, use_bin_type=True)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        """Deserialize message from bytes."""
        unpacked = msgpack.unpackb(data, raw=False)
        return cls(**unpacked)
    
    def get_signable_data(self) -> bytes:
        """Get data that should be signed (everything except signature)."""
        data = {
            "msg_type": self.msg_type,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "message_id": self.message_id,
            "ttl": self.ttl,
        }
        return msgpack.packb(data, use_bin_type=True)


class MessageFactory:
    """Factory for creating different types of messages."""
    
    @staticmethod
    def create_handshake(
        sender_id: str,
        public_key: bytes,
        address: str
    ) -> Message:
        """Create a handshake message."""
        return Message(
            msg_type=MessageType.HANDSHAKE,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={
                "public_key": public_key,
                "address": address,
                "protocol_version": "1.0",
            }
        )
    
    @staticmethod
    def create_handshake_ack(
        sender_id: str,
        public_key: bytes,
        peers: List[PeerInfo]
    ) -> Message:
        """Create a handshake acknowledgment message."""
        return Message(
            msg_type=MessageType.HANDSHAKE_ACK,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={
                "public_key": public_key,
                "peers": [p.to_dict() for p in peers],
            }
        )
    
    @staticmethod
    def create_heartbeat(sender_id: str) -> Message:
        """Create a heartbeat message."""
        return Message(
            msg_type=MessageType.HEARTBEAT,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={}
        )
    
    @staticmethod
    def create_peer_discovery(sender_id: str) -> Message:
        """Create a peer discovery request message."""
        return Message(
            msg_type=MessageType.PEER_DISCOVERY,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={}
        )
    
    @staticmethod
    def create_peer_announcement(
        sender_id: str,
        peers: List[PeerInfo]
    ) -> Message:
        """Create a peer announcement message."""
        return Message(
            msg_type=MessageType.PEER_ANNOUNCEMENT,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={
                "peers": [p.to_dict() for p in peers],
            }
        )
    
    @staticmethod
    def create_gossip_message(
        sender_id: str,
        data: Any,
        ttl: int = 10
    ) -> Message:
        """Create a gossip message for propagation."""
        return Message(
            msg_type=MessageType.GOSSIP_MESSAGE,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={"data": data},
            ttl=ttl
        )
    
    @staticmethod
    def create_trust_update(
        sender_id: str,
        target_node_id: str,
        trust_score: float,
        reason: str = ""
    ) -> Message:
        """Create a trust update message."""
        return Message(
            msg_type=MessageType.TRUST_UPDATE,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={
                "target_node_id": target_node_id,
                "trust_score": trust_score,
                "reason": reason,
            }
        )
    
    @staticmethod
    def create_trusted_peers_request(sender_id: str) -> Message:
        """Create a request for trusted peers list."""
        return Message(
            msg_type=MessageType.TRUSTED_PEERS_REQUEST,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={}
        )
    
    @staticmethod
    def create_trusted_peers_response(
        sender_id: str,
        trusted_peers: List[PeerInfo]
    ) -> Message:
        """Create a response with trusted peers list."""
        return Message(
            msg_type=MessageType.TRUSTED_PEERS_RESPONSE,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={
                "trusted_peers": [p.to_dict() for p in trusted_peers],
            }
        )
    
    @staticmethod
    def create_disconnect(sender_id: str, reason: str = "") -> Message:
        """Create a disconnect message."""
        return Message(
            msg_type=MessageType.DISCONNECT,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={"reason": reason}
        )
    
    @staticmethod
    def create_custom_data(
        sender_id: str,
        data: Any,
        ttl: int = 10
    ) -> Message:
        """Create a custom data message."""
        return Message(
            msg_type=MessageType.CUSTOM_DATA,
            sender_id=sender_id,
            timestamp=time.time(),
            payload={"data": data},
            ttl=ttl
        )
