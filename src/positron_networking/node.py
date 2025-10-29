"""
Main Node class that orchestrates the decentralized network.
"""
import asyncio
from typing import Optional, Callable, Any, List
from positron_networking.config import NetworkConfig
from positron_networking.identity import Identity
from positron_networking.storage import Storage
from positron_networking.trust import TrustManager
from positron_networking.peers import PeerManager
from positron_networking.gossip import GossipProtocol
from positron_networking.network import NetworkTransport
from positron_networking.protocol import Message, MessageType, MessageFactory, PeerInfo
from positron_networking.dht import DistributedHashTable
from positron_networking.nat_traversal import NATTraversalManager
import structlog
import time


class Node:
    """Main node in the decentralized network."""
    
    def __init__(self, config: Optional[NetworkConfig] = None):
        """
        Initialize a network node.
        
        Args:
            config: Network configuration (uses defaults if not provided)
        """
        self.config = config or NetworkConfig()
        self.config.validate()
        
        # Setup logging
        self.logger = structlog.get_logger()
        
        # Core components (initialized in start())
        self.identity: Optional[Identity] = None
        self.storage: Optional[Storage] = None
        self.trust_manager: Optional[TrustManager] = None
        self.peer_manager: Optional[PeerManager] = None
        self.gossip: Optional[GossipProtocol] = None
        self.network: Optional[NetworkTransport] = None
        self.dht: Optional[DistributedHashTable] = None
        self.nat_traversal: Optional[NATTraversalManager] = None
        
        # Custom message handlers
        self._custom_handlers = {}
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
    
    @property
    def node_id(self) -> Optional[str]:
        """Get this node's identifier."""
        return self.identity.node_id if self.identity else None
    
    @property
    def address(self) -> str:
        """Get this node's address."""
        return f"{self.config.host}:{self.config.port}"
    
    async def start(self):
        """Start the node and all its components."""
        self.logger.info("Starting decentralized network node")
        
        # Initialize identity
        self.identity = Identity.load_or_generate(
            self.config.private_key_path,
            self.config.public_key_path
        )
        self.logger.info(f"Node ID: {self.identity.node_id}")
        
        # Initialize storage
        self.storage = Storage(self.config.db_path)
        await self.storage.initialize()
        
        # Initialize trust manager
        self.trust_manager = TrustManager(
            storage=self.storage,
            initial_trust=self.config.initial_trust_score,
            min_trust=self.config.min_trust_threshold,
            max_trust=self.config.max_trust_score,
            decay_rate=self.config.trust_decay_rate,
            decay_interval=self.config.trust_decay_interval
        )
        await self.trust_manager.start()
        
        # Initialize peer manager
        self.peer_manager = PeerManager(
            node_id=self.identity.node_id,
            storage=self.storage,
            trust_manager=self.trust_manager,
            bootstrap_nodes=self.config.bootstrap_nodes,
            max_peers=self.config.max_peers,
            min_peers=self.config.min_peers,
            discovery_interval=self.config.peer_discovery_interval,
            peer_timeout=self.config.peer_timeout
        )
        await self.peer_manager.start()
        
        # Initialize gossip protocol
        self.gossip = GossipProtocol(
            node_id=self.identity.node_id,
            peer_manager=self.peer_manager,
            storage=self.storage,
            trust_manager=self.trust_manager,
            fanout=self.config.gossip_fanout,
            gossip_interval=self.config.gossip_interval,
            message_cache_size=self.config.message_cache_size
        )
        
        # Register default message handlers
        self._register_handlers()
        await self.gossip.start()
        
        # Initialize DHT
        self.dht = DistributedHashTable(
            node_id=self.identity.node_id,
            address=self.address,
            k=20,  # Standard Kademlia bucket size
            alpha=3,  # Concurrency parameter
            replication_factor=self.config.dht_replication_factor if hasattr(self.config, 'dht_replication_factor') else 3,
            ttl_default=self.config.dht_ttl_default if hasattr(self.config, 'dht_ttl_default') else 3600.0
        )
        await self.dht.start()
        
        # Initialize network transport
        self.network = NetworkTransport(
            identity=self.identity,
            host=self.config.host,
            port=self.config.port,
            max_connections=self.config.max_concurrent_connections,
            connection_timeout=self.config.connection_timeout
        )
        self.network.set_message_handler(self._handle_network_message)
        await self.network.start()
        
        # Initialize NAT traversal
        self.nat_traversal = NATTraversalManager(
            local_port=self.config.port,
            stun_servers=[
                ("stun.l.google.com", 19302),
                ("stun1.l.google.com", 19302),
                ("stun2.l.google.com", 19302)
            ]
        )
        await self.nat_traversal.initialize()
        self.logger.info(
            "NAT traversal initialized",
            behind_nat=self.nat_traversal.is_behind_nat(),
            nat_type=self.nat_traversal.get_nat_info().get("nat_type") if self.nat_traversal.is_behind_nat() else None
        )
        
        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Connect to bootstrap nodes
        await self._connect_to_bootstrap()
        
        self._running = True
        self.logger.info(
            "Node started successfully",
            address=self.address,
            node_id=self.identity.node_id
        )
    
    async def stop(self):
        """Stop the node and all its components."""
        self.logger.info("Stopping node")
        self._running = False
        
        # Stop background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Stop components in reverse order
        if self.nat_traversal:
            await self.nat_traversal.stop()
        
        if self.network:
            await self.network.stop()
        
        if self.dht:
            await self.dht.stop()
        
        if self.gossip:
            await self.gossip.stop()
        
        if self.peer_manager:
            await self.peer_manager.stop()
        
        if self.trust_manager:
            await self.trust_manager.stop()
        
        if self.storage:
            await self.storage.close()
        
        self.logger.info("Node stopped")
    
    def _register_handlers(self):
        """Register default message handlers."""
        self.gossip.register_handler(
            MessageType.HANDSHAKE,
            self._handle_handshake
        )
        self.gossip.register_handler(
            MessageType.HANDSHAKE_ACK,
            self._handle_handshake_ack
        )
        self.gossip.register_handler(
            MessageType.HEARTBEAT,
            self._handle_heartbeat
        )
        self.gossip.register_handler(
            MessageType.PEER_DISCOVERY,
            self._handle_peer_discovery
        )
        self.gossip.register_handler(
            MessageType.NAT_CANDIDATE_OFFER,
            self._handle_nat_candidate_offer
        )
        self.gossip.register_handler(
            MessageType.NAT_CANDIDATE_ANSWER,
            self._handle_nat_candidate_answer
        )
        self.gossip.register_handler(
            MessageType.NAT_PUNCH_REQUEST,
            self._handle_nat_punch_request
        )
        self.gossip.register_handler(
            MessageType.PEER_ANNOUNCEMENT,
            self._handle_peer_announcement
        )
        self.gossip.register_handler(
            MessageType.TRUST_UPDATE,
            self._handle_trust_update
        )
        self.gossip.register_handler(
            MessageType.TRUSTED_PEERS_REQUEST,
            self._handle_trusted_peers_request
        )
        self.gossip.register_handler(
            MessageType.TRUSTED_PEERS_RESPONSE,
            self._handle_trusted_peers_response
        )
        self.gossip.register_handler(
            MessageType.CUSTOM_DATA,
            self._handle_custom_data
        )
    
    async def _handle_network_message(self, message: Message, sender_address: str):
        """Handle incoming network message."""
        await self.gossip.receive_message(message, sender_address)
    
    async def _handle_handshake(self, message: Message, sender_address: str):
        """Handle handshake message."""
        public_key = message.payload.get("public_key")
        peer_address = message.payload.get("address")
        
        peer = PeerInfo(
            node_id=message.sender_id,
            address=peer_address,
            public_key=public_key,
            trust_score=self.config.initial_trust_score
        )
        
        self.peer_manager.add_peer(peer)
    
    async def _handle_handshake_ack(self, message: Message, sender_address: str):
        """Handle handshake acknowledgment."""
        public_key = message.payload.get("public_key")
        peers_data = message.payload.get("peers", [])
        
        # Add the responding peer
        peer = PeerInfo(
            node_id=message.sender_id,
            address=sender_address,
            public_key=public_key,
            trust_score=self.config.initial_trust_score
        )
        self.peer_manager.add_peer(peer)
        
        # Add announced peers to known peers
        for peer_data in peers_data:
            peer = PeerInfo.from_dict(peer_data)
            if peer.node_id != self.identity.node_id:
                self.peer_manager.known_peers[peer.node_id] = peer
                await self.storage.save_peer(peer)
    
    async def _handle_heartbeat(self, message: Message, sender_address: str):
        """Handle heartbeat message."""
        self.peer_manager.update_peer_activity(message.sender_id)
    
    async def _handle_peer_discovery(self, message: Message, sender_address: str):
        """Handle peer discovery request."""
        # Send peer announcement with our known trusted peers
        trusted_peers = self.peer_manager.get_trusted_peers(min_trust=0.6)
        
        response = MessageFactory.create_peer_announcement(
            self.identity.node_id,
            trusted_peers[:10]  # Send top 10 trusted peers
        )
        
        await self.network.send_to_peer(message.sender_id, response)
    
    async def _handle_peer_announcement(self, message: Message, sender_address: str):
        """Handle peer announcement."""
        peers_data = message.payload.get("peers", [])
        
        for peer_data in peers_data:
            peer = PeerInfo.from_dict(peer_data)
            if peer.node_id != self.identity.node_id:
                self.peer_manager.known_peers[peer.node_id] = peer
                await self.storage.save_peer(peer)
    
    async def _handle_trust_update(self, message: Message, sender_address: str):
        """Handle trust update from a peer."""
        target_node_id = message.payload.get("target_node_id")
        trust_score = message.payload.get("trust_score")
        
        # Apply transitive trust
        await self.trust_manager.apply_transitive_trust(
            message.sender_id,
            target_node_id,
            trust_score
        )
    
    async def _handle_trusted_peers_request(self, message: Message, sender_address: str):
        """Handle request for trusted peers list."""
        trusted_peers = await self.trust_manager.get_trusted_peers(min_trust=0.7)
        
        response = MessageFactory.create_trusted_peers_response(
            self.identity.node_id,
            trusted_peers[:20]  # Send top 20 trusted peers
        )
        
        await self.network.send_to_peer(message.sender_id, response)
    
    async def _handle_trusted_peers_response(self, message: Message, sender_address: str):
        """Handle trusted peers list response."""
        trusted_peers_data = message.payload.get("trusted_peers", [])
        
        for peer_data in trusted_peers_data:
            peer = PeerInfo.from_dict(peer_data)
            if peer.node_id != self.identity.node_id:
                # Apply transitive trust for recommended peers
                await self.trust_manager.apply_transitive_trust(
                    message.sender_id,
                    peer.node_id,
                    peer.trust_score
                )
                
                # Add to known peers
                if peer.node_id not in self.peer_manager.known_peers:
                    self.peer_manager.known_peers[peer.node_id] = peer
                    await self.storage.save_peer(peer)
    
    async def _handle_custom_data(self, message: Message, sender_address: str):
        """Handle custom data message."""
        data = message.payload.get("data")
        
        # Call custom handlers if registered
        for handler in self._custom_handlers.values():
            try:
                await handler(message.sender_id, data)
            except Exception as e:
                self.logger.error(f"Error in custom handler: {e}")
    
    async def _handle_nat_candidate_offer(self, message: Message, sender_address: str):
        """Handle NAT candidate offer from a peer."""
        if not self.nat_traversal:
            return
        
        candidates = message.payload.get("candidates", [])
        self.logger.info(
            "received_nat_candidates",
            peer_id=message.sender_id,
            count=len(candidates)
        )
        
        # Get our own candidates
        our_candidates = await self.nat_traversal.get_candidates()
        
        # Send our candidates back
        answer = MessageFactory.create_nat_candidate_answer(
            self.identity.node_id,
            our_candidates
        )
        await self.network.send_to_peer(message.sender_id, answer)
        
        # Attempt to connect using received candidates
        try:
            success = await self.nat_traversal.connect_to_peer(
                message.sender_id,
                candidates
            )
            if success:
                self.logger.info("nat_connection_established", peer_id=message.sender_id)
        except Exception as e:
            self.logger.warning("nat_connection_failed", peer_id=message.sender_id, error=str(e))
    
    async def _handle_nat_candidate_answer(self, message: Message, sender_address: str):
        """Handle NAT candidate answer from a peer."""
        if not self.nat_traversal:
            return
        
        candidates = message.payload.get("candidates", [])
        self.logger.info(
            "received_nat_answer",
            peer_id=message.sender_id,
            count=len(candidates)
        )
        
        # Attempt to connect using received candidates
        try:
            success = await self.nat_traversal.connect_to_peer(
                message.sender_id,
                candidates
            )
            if success:
                self.logger.info("nat_connection_established", peer_id=message.sender_id)
        except Exception as e:
            self.logger.warning("nat_connection_failed", peer_id=message.sender_id, error=str(e))
    
    async def _handle_nat_punch_request(self, message: Message, sender_address: str):
        """Handle NAT punch request from a peer."""
        if not self.nat_traversal:
            return
        
        punch_id = message.payload.get("punch_id")
        self.logger.info("received_punch_request", peer_id=message.sender_id, punch_id=punch_id)
        
        # The hole puncher will handle the actual punching when it receives UDP packets
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to peers."""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                
                heartbeat = MessageFactory.create_heartbeat(self.identity.node_id)
                
                # Send to all active peers
                active_peers = self.peer_manager.get_active_peers()
                for peer in active_peers:
                    await self.network.send_to_peer(peer.node_id, heartbeat)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in heartbeat loop: {e}")
    
    async def _connect_to_bootstrap(self):
        """Connect to bootstrap nodes."""
        for bootstrap_addr in self.config.bootstrap_nodes:
            try:
                self.logger.info(f"Connecting to bootstrap node: {bootstrap_addr}")
                connection = await self.network.connect(bootstrap_addr)
                if connection:
                    self.logger.info(f"Connected to bootstrap node: {bootstrap_addr}")
            except Exception as e:
                self.logger.warning(f"Failed to connect to bootstrap {bootstrap_addr}: {e}")
    
    async def broadcast(self, data: Any, ttl: int = 10):
        """
        Broadcast data to the network via gossip.
        
        Args:
            data: Data to broadcast
            ttl: Time-to-live for the message
        """
        message = MessageFactory.create_gossip_message(
            self.identity.node_id,
            data,
            ttl
        )
        await self.gossip.broadcast(message)
    
    async def send_to_peer(self, node_id: str, data: Any):
        """
        Send data directly to a specific peer.
        
        Args:
            node_id: Target peer's node ID
            data: Data to send
        """
        message = MessageFactory.create_custom_data(
            self.identity.node_id,
            data
        )
        await self.network.send_to_peer(node_id, message)
    
    def register_data_handler(self, name: str, handler: Callable):
        """
        Register a custom data handler.
        
        Args:
            name: Handler name
            handler: Async function(sender_id, data)
        """
        self._custom_handlers[name] = handler
    
    async def request_trusted_peers(self, node_id: str):
        """
        Request trusted peers list from a specific peer.
        
        Args:
            node_id: Peer to request from
        """
        request = MessageFactory.create_trusted_peers_request(self.identity.node_id)
        await self.network.send_to_peer(node_id, request)
    
    async def share_trusted_peers(self):
        """Share our trusted peers list with the network."""
        trusted_peers = await self.trust_manager.get_trusted_peers(min_trust=0.7)
        
        message = MessageFactory.create_trusted_peers_response(
            self.identity.node_id,
            trusted_peers[:20]
        )
        await self.gossip.broadcast(message)
    
    # DHT Methods
    
    async def dht_store(self, key: str, value: Any, ttl: Optional[float] = None) -> bool:
        """
        Store a key-value pair in the distributed hash table.
        
        Args:
            key: Storage key
            value: Value to store
            ttl: Time-to-live in seconds (None = use default)
            
        Returns:
            True if stored successfully
        """
        if not self.dht:
            raise RuntimeError("DHT not initialized")
        
        return await self.dht.store(key, value, ttl=ttl, replicate=True)
    
    async def dht_retrieve(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the distributed hash table.
        
        Args:
            key: Storage key
            
        Returns:
            Retrieved value or None if not found
        """
        if not self.dht:
            raise RuntimeError("DHT not initialized")
        
        return await self.dht.retrieve(key, local_only=False)
    
    async def dht_delete(self, key: str) -> bool:
        """
        Delete a key-value pair from the distributed hash table.
        
        Args:
            key: Key to delete
            
        Returns:
            True if deleted
        """
        if not self.dht:
            raise RuntimeError("DHT not initialized")
        
        return await self.dht.delete(key, replicate=True)
    
    def dht_get_stats(self) -> dict:
        """
        Get DHT statistics.
        
        Returns:
            Dictionary of DHT statistics
        """
        if not self.dht:
            return {}
        
        return self.dht.get_statistics()
    
    async def dht_add_peer(self, node_id: str, address: str):
        """
        Add a peer to the DHT routing table.
        
        Args:
            node_id: Node identifier
            address: Node network address
        """
        if self.dht:
            self.dht.add_node(node_id, address)
    
    def get_stats(self) -> dict:
        """Get node statistics."""
        stats = {
            "node_id": self.identity.node_id,
            "address": self.address,
            "active_peers": len(self.peer_manager.active_peers),
            "known_peers": len(self.peer_manager.known_peers),
            "connections": self.network.get_connection_count(),
            "gossip_stats": self.gossip.get_statistics(),
        }
        
        if self.dht:
            stats["dht_stats"] = self.dht.get_statistics()
        
        return stats
    
    # NAT Traversal Methods
    
    async def get_nat_candidates(self) -> List[dict]:
        """
        Get NAT traversal candidates for establishing connections.
        
        Returns:
            List of connection candidates
        """
        if not self.nat_traversal:
            raise RuntimeError("NAT traversal not initialized")
        
        return await self.nat_traversal.get_candidates()
    
    async def request_peer_connection(self, peer_id: str):
        """
        Request a NAT-aware connection to a peer.
        
        This initiates the ICE-like candidate exchange process.
        
        Args:
            peer_id: Target peer's node ID
        """
        if not self.nat_traversal:
            raise RuntimeError("NAT traversal not initialized")
        
        # Get our candidates
        candidates = await self.get_nat_candidates()
        
        # Send candidate offer to peer
        offer = MessageFactory.create_nat_candidate_offer(
            self.identity.node_id,
            candidates
        )
        
        await self.network.send_to_peer(peer_id, offer)
        self.logger.info(f"Sent NAT candidate offer to {peer_id}")
    
    def is_behind_nat(self) -> bool:
        """
        Check if this node is behind NAT.
        
        Returns:
            True if behind NAT
        """
        if not self.nat_traversal:
            return False
        
        return self.nat_traversal.is_behind_nat()
    
    def get_nat_info(self) -> dict:
        """
        Get NAT information.
        
        Returns:
            Dictionary with NAT type and addresses
        """
        if not self.nat_traversal:
            return {}
        
        return self.nat_traversal.get_nat_info()
    
    async def _handle_nat_candidate_offer(self, message: Message, sender_address: str):
        """Handle NAT candidate offer from a peer."""
        sender_id = message.sender_id
        candidates = message.payload.get("candidates", [])
        
        self.logger.info(f"Received NAT candidate offer from {sender_id}")
        
        # Get our candidates and send answer
        our_candidates = await self.get_nat_candidates()
        
        answer = MessageFactory.create_nat_candidate_answer(
            self.identity.node_id,
            our_candidates
        )
        
        await self.network.send_to_peer(sender_id, answer)
        
        # Attempt hole punching with their candidates
        if self.nat_traversal:
            try:
                success = await self.nat_traversal.connect_to_peer(sender_id, candidates)
                if success:
                    self.logger.info(f"Successfully established NAT traversal connection to {sender_id}")
                else:
                    self.logger.warning(f"Failed to establish NAT traversal connection to {sender_id}")
            except Exception as e:
                self.logger.error(f"Error during NAT traversal to {sender_id}: {e}")
    
    async def _handle_nat_candidate_answer(self, message: Message, sender_address: str):
        """Handle NAT candidate answer from a peer."""
        sender_id = message.sender_id
        candidates = message.payload.get("candidates", [])
        
        self.logger.info(f"Received NAT candidate answer from {sender_id}")
        
        # Attempt hole punching with their candidates
        if self.nat_traversal:
            try:
                success = await self.nat_traversal.connect_to_peer(sender_id, candidates)
                if success:
                    self.logger.info(f"Successfully established NAT traversal connection to {sender_id}")
                else:
                    self.logger.warning(f"Failed to establish NAT traversal connection to {sender_id}")
            except Exception as e:
                self.logger.error(f"Error during NAT traversal to {sender_id}: {e}")
    
    async def _handle_nat_punch_request(self, message: Message, sender_address: str):
        """Handle NAT punch request."""
        punch_id = message.payload.get("punch_id")
        sender_id = message.sender_id
        
        self.logger.debug(f"Received NAT punch request from {sender_id}, punch_id={punch_id}")
        
        # The punch request itself serves to open our NAT
        # Connection attempt should already be in progress from candidate exchange
