"""
Positron Networking - Production-ready decentralized P2P networking layer.

This package provides a complete decentralized networking solution with:
- Packet-based transport layer (UDP/TCP)
- Cryptographic identity and authentication (Ed25519)
- Gossip-based message propagation
- Node trust and reputation system
- Peer discovery and bootstrap mechanisms
- Flow control and congestion control
- Secure trusted node list sharing

Part of the Positron Blockchain ecosystem.
https://github.com/positron-blockchain/networking
"""

__version__ = "0.1.0"

from positron_networking.node import Node
from positron_networking.config import NetworkConfig

__all__ = ["Node", "NetworkConfig"]
