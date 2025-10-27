"""
Peer discovery and management for the decentralized network.
"""
import asyncio
from typing import Dict, Set, List, Optional, Tuple
from positron_networking.protocol import PeerInfo, Message, MessageType, MessageFactory
from positron_networking.storage import Storage
from positron_networking.trust import TrustManager
import time
import random


class PeerManager:
    """Manages peer connections and discovery."""
    
    def __init__(
        self,
        node_id: str,
        storage: Storage,
        trust_manager: TrustManager,
        bootstrap_nodes: List[str],
        max_peers: int = 50,
        min_peers: int = 5,
        discovery_interval: float = 30.0,
        peer_timeout: float = 60.0
    ):
        """
        Initialize peer manager.
        
        Args:
            node_id: This node's identifier
            storage: Storage instance
            trust_manager: Trust manager instance
            bootstrap_nodes: List of bootstrap node addresses
            max_peers: Maximum number of peers
            min_peers: Minimum number of peers to maintain
            discovery_interval: Interval between peer discovery attempts
            peer_timeout: Timeout for peer inactivity
        """
        self.node_id = node_id
        self.storage = storage
        self.trust_manager = trust_manager
        self.bootstrap_nodes = bootstrap_nodes
        self.max_peers = max_peers
        self.min_peers = min_peers
        self.discovery_interval = discovery_interval
        self.peer_timeout = peer_timeout
        
        # Active peer connections
        self.active_peers: Dict[str, PeerInfo] = {}
        
        # Peers we've discovered but aren't connected to
        self.known_peers: Dict[str, PeerInfo] = {}
        
        # Peers we're currently trying to connect to
        self.connecting_peers: Set[str] = set()
        
        # Background tasks
        self._discovery_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start peer management background tasks."""
        # Load known peers from storage
        await self._load_known_peers()
        
        # Start background tasks
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        """Stop peer management background tasks."""
        tasks = [self._discovery_task, self._cleanup_task]
        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    async def _load_known_peers(self):
        """Load known peers from storage."""
        peers = await self.storage.get_all_peers()
        for peer in peers:
            if peer.node_id != self.node_id:
                self.known_peers[peer.node_id] = peer
    
    def add_peer(self, peer: PeerInfo) -> bool:
        """
        Add a peer to active peers.
        
        Args:
            peer: Peer information
            
        Returns:
            True if peer was added, False if rejected
        """
        if peer.node_id == self.node_id:
            return False
        
        if len(self.active_peers) >= self.max_peers:
            # Check if we should replace an existing low-trust peer
            if not self._should_accept_peer(peer):
                return False
            self._evict_lowest_trust_peer()
        
        self.active_peers[peer.node_id] = peer
        self.known_peers[peer.node_id] = peer
        
        # Save to storage
        asyncio.create_task(self.storage.save_peer(peer))
        
        return True
    
    def _should_accept_peer(self, peer: PeerInfo) -> bool:
        """Determine if we should accept a new peer when at capacity."""
        if not self.active_peers:
            return True
        
        # Find lowest trust peer
        lowest_trust = min(p.trust_score for p in self.active_peers.values())
        
        # Accept if new peer has higher trust
        return peer.trust_score > lowest_trust
    
    def _evict_lowest_trust_peer(self):
        """Remove the peer with the lowest trust score."""
        if not self.active_peers:
            return
        
        lowest_peer = min(
            self.active_peers.values(),
            key=lambda p: p.trust_score
        )
        self.remove_peer(lowest_peer.node_id)
    
    def remove_peer(self, node_id: str):
        """
        Remove a peer from active peers.
        
        Args:
            node_id: Node identifier
        """
        if node_id in self.active_peers:
            del self.active_peers[node_id]
        
        if node_id in self.connecting_peers:
            self.connecting_peers.remove(node_id)
    
    def update_peer_activity(self, node_id: str):
        """
        Update last seen time for a peer.
        
        Args:
            node_id: Node identifier
        """
        if node_id in self.active_peers:
            self.active_peers[node_id].last_seen = time.time()
            asyncio.create_task(self.storage.save_peer(self.active_peers[node_id]))
    
    def get_peer(self, node_id: str) -> Optional[PeerInfo]:
        """
        Get peer information.
        
        Args:
            node_id: Node identifier
            
        Returns:
            PeerInfo or None
        """
        return self.active_peers.get(node_id) or self.known_peers.get(node_id)
    
    def get_active_peers(self) -> List[PeerInfo]:
        """Get list of active peers."""
        return list(self.active_peers.values())
    
    def get_random_peers(self, count: int, exclude: Optional[Set[str]] = None) -> List[PeerInfo]:
        """
        Get random subset of active peers.
        
        Args:
            count: Number of peers to return
            exclude: Set of node IDs to exclude
            
        Returns:
            List of random peer information
        """
        exclude = exclude or set()
        candidates = [
            p for p in self.active_peers.values()
            if p.node_id not in exclude
        ]
        
        count = min(count, len(candidates))
        return random.sample(candidates, count) if candidates else []
    
    def get_trusted_peers(self, min_trust: float = 0.7) -> List[PeerInfo]:
        """
        Get trusted active peers.
        
        Args:
            min_trust: Minimum trust threshold
            
        Returns:
            List of trusted peers
        """
        return [
            p for p in self.active_peers.values()
            if p.trust_score >= min_trust
        ]
    
    def needs_more_peers(self) -> bool:
        """Check if we need to discover more peers."""
        return len(self.active_peers) < self.min_peers
    
    def can_accept_peers(self) -> bool:
        """Check if we can accept more peers."""
        return len(self.active_peers) < self.max_peers
    
    async def discover_peers(self) -> List[str]:
        """
        Discover new peers to connect to.
        
        Returns:
            List of peer addresses to try connecting to
        """
        candidates = []
        
        # First, try bootstrap nodes if we're low on peers
        if self.needs_more_peers():
            for bootstrap_addr in self.bootstrap_nodes:
                if bootstrap_addr not in [p.address for p in self.active_peers.values()]:
                    candidates.append(bootstrap_addr)
        
        # Try known peers that aren't currently connected
        disconnected_peers = [
            p for p in self.known_peers.values()
            if p.node_id not in self.active_peers
            and p.node_id not in self.connecting_peers
            and await self.trust_manager.is_trusted(p.node_id)
        ]
        
        # Sort by trust score and last seen
        disconnected_peers.sort(
            key=lambda p: (p.trust_score, -p.last_seen),
            reverse=True
        )
        
        # Add top candidates
        for peer in disconnected_peers[:5]:
            candidates.append(peer.address)
        
        return candidates
    
    async def _discovery_loop(self):
        """Background task for peer discovery."""
        while True:
            try:
                await asyncio.sleep(self.discovery_interval)
                
                if self.needs_more_peers():
                    candidates = await self.discover_peers()
                    # Actual connection attempts would be handled by the network layer
                    # This just identifies candidates
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in discovery loop: {e}")
    
    async def _cleanup_loop(self):
        """Background task for cleaning up inactive peers."""
        while True:
            try:
                await asyncio.sleep(30.0)  # Run every 30 seconds
                
                current_time = time.time()
                inactive_peers = []
                
                # Find inactive peers
                for node_id, peer in self.active_peers.items():
                    if current_time - peer.last_seen > self.peer_timeout:
                        inactive_peers.append(node_id)
                
                # Remove inactive peers
                for node_id in inactive_peers:
                    self.remove_peer(node_id)
                    await self.trust_manager.on_peer_timeout(node_id)
                
                # Cleanup old message records
                await self.storage.cleanup_old_messages()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in cleanup loop: {e}")
    
    def parse_address(self, address: str) -> Tuple[str, int]:
        """
        Parse an address string into host and port.
        
        Args:
            address: Address in "host:port" format
            
        Returns:
            Tuple of (host, port)
        """
        if ":" in address:
            host, port_str = address.rsplit(":", 1)
            return host, int(port_str)
        else:
            return address, 8888  # Default port
    
    def format_address(self, host: str, port: int) -> str:
        """
        Format host and port into address string.
        
        Args:
            host: Host address
            port: Port number
            
        Returns:
            Address string in "host:port" format
        """
        return f"{host}:{port}"
