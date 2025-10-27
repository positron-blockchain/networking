"""
Configuration management for the decentralized network.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import json
import os


@dataclass
class NetworkConfig:
    """Configuration for the decentralized network node."""
    
    # Node identity
    node_id: Optional[str] = None
    private_key_path: str = "keys/private_key.pem"
    public_key_path: str = "keys/public_key.pem"
    
    # Network settings
    host: str = "0.0.0.0"
    port: int = 8888
    bootstrap_nodes: List[str] = field(default_factory=list)
    
    # Gossip protocol settings
    gossip_fanout: int = 3  # Number of peers to gossip to
    gossip_interval: float = 1.0  # Seconds between gossip rounds
    message_ttl: int = 10  # Time-to-live for messages
    message_cache_size: int = 10000  # Number of message IDs to cache
    
    # Peer management
    max_peers: int = 50
    min_peers: int = 5
    peer_discovery_interval: float = 30.0  # Seconds
    peer_timeout: float = 60.0  # Seconds of inactivity before peer is considered dead
    heartbeat_interval: float = 10.0  # Seconds between heartbeats
    
    # Trust system
    initial_trust_score: float = 0.5  # Initial trust for new peers (0.0-1.0)
    trust_decay_rate: float = 0.01  # Trust decay per interval
    trust_decay_interval: float = 300.0  # Seconds
    min_trust_threshold: float = 0.1  # Minimum trust to maintain connection
    max_trust_score: float = 1.0
    trust_boost_message: float = 0.001  # Trust increase per valid message
    trust_penalty_invalid: float = 0.1  # Trust decrease for invalid message
    
    # Storage
    data_dir: str = "node_data"
    db_path: str = "node_data/network.db"
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    # Performance
    max_concurrent_connections: int = 100
    message_buffer_size: int = 1024
    connection_timeout: float = 10.0
    
    def __post_init__(self):
        """Ensure data directories exist."""
        os.makedirs(os.path.dirname(self.private_key_path), exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    @classmethod
    def from_file(cls, path: str) -> "NetworkConfig":
        """Load configuration from a JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(**data)
    
    def to_file(self, path: str):
        """Save configuration to a JSON file."""
        data = {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_")
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def validate(self) -> bool:
        """Validate configuration parameters."""
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")
        
        if self.gossip_fanout < 1:
            raise ValueError(f"gossip_fanout must be at least 1")
        
        if not (0.0 <= self.initial_trust_score <= 1.0):
            raise ValueError(f"initial_trust_score must be between 0.0 and 1.0")
        
        if self.max_peers < self.min_peers:
            raise ValueError(f"max_peers must be >= min_peers")
        
        return True
