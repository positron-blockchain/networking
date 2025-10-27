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
        if self.network:
            await self.network.stop()
        
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
    
    def get_stats(self) -> dict:
        """Get node statistics."""
        return {
            "node_id": self.identity.node_id,
            "address": self.address,
            "active_peers": len(self.peer_manager.active_peers),
            "known_peers": len(self.peer_manager.known_peers),
            "connections": self.network.get_connection_count(),
            "gossip_stats": self.gossip.get_statistics(),
        }
