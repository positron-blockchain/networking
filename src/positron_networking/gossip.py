"""
Gossip protocol implementation for epidemic message propagation.
"""
import asyncio
from typing import Dict, Set, Optional, Callable, Any, List
from positron_networking.protocol import Message, MessageType, MessageFactory
from positron_networking.peers import PeerManager
from positron_networking.storage import Storage
from positron_networking.trust import TrustManager
import time
import random
from collections import deque


class GossipProtocol:
    """Implements gossip-based epidemic message propagation."""
    
    def __init__(
        self,
        node_id: str,
        peer_manager: PeerManager,
        storage: Storage,
        trust_manager: TrustManager,
        fanout: int = 3,
        gossip_interval: float = 1.0,
        message_cache_size: int = 10000
    ):
        """
        Initialize gossip protocol.
        
        Args:
            node_id: This node's identifier
            peer_manager: Peer manager instance
            storage: Storage instance
            trust_manager: Trust manager instance
            fanout: Number of peers to gossip to per round
            gossip_interval: Interval between gossip rounds
            message_cache_size: Maximum number of message IDs to cache
        """
        self.node_id = node_id
        self.peer_manager = peer_manager
        self.storage = storage
        self.trust_manager = trust_manager
        self.fanout = fanout
        self.gossip_interval = gossip_interval
        
        # Message cache for deduplication (using deque for FIFO)
        self.message_cache: deque = deque(maxlen=message_cache_size)
        self.message_cache_set: Set[str] = set()
        
        # Pending messages to gossip
        self.pending_messages: deque = deque()
        
        # Message handlers for different message types
        self.handlers: Dict[int, Callable] = {}
        
        # Statistics
        self.stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "messages_propagated": 0,
            "duplicates_rejected": 0,
        }
        
        # Background task
        self._gossip_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start gossip protocol background tasks."""
        self._gossip_task = asyncio.create_task(self._gossip_loop())
    
    async def stop(self):
        """Stop gossip protocol background tasks."""
        if self._gossip_task:
            self._gossip_task.cancel()
            try:
                await self._gossip_task
            except asyncio.CancelledError:
                pass
    
    def register_handler(self, message_type: int, handler: Callable):
        """
        Register a handler for a specific message type.
        
        Args:
            message_type: Message type to handle
            handler: Async function to handle the message
        """
        self.handlers[message_type] = handler
    
    async def broadcast(self, message: Message):
        """
        Broadcast a message to the network.
        
        Args:
            message: Message to broadcast
        """
        # Mark as seen
        await self._mark_seen(message.message_id)
        
        # Add to pending queue for gossip
        self.pending_messages.append(message)
        
        self.stats["messages_sent"] += 1
    
    async def receive_message(self, message: Message, sender_address: str) -> bool:
        """
        Receive and process a message.
        
        Args:
            message: Received message
            sender_address: Address of sender
            
        Returns:
            True if message was processed, False if rejected
        """
        self.stats["messages_received"] += 1
        
        # Check if we've seen this message before
        if await self._has_seen(message.message_id):
            self.stats["duplicates_rejected"] += 1
            return False
        
        # Check TTL
        if message.ttl <= 0:
            return False
        
        # Verify sender trust
        if not await self.trust_manager.is_trusted(message.sender_id):
            await self.trust_manager.on_invalid_message(message.sender_id)
            return False
        
        # Mark as seen
        await self._mark_seen(message.message_id)
        
        # Update peer activity
        self.peer_manager.update_peer_activity(message.sender_id)
        
        # Process message based on type
        if message.msg_type in self.handlers:
            try:
                await self.handlers[message.msg_type](message, sender_address)
                await self.trust_manager.on_valid_message(message.sender_id)
            except Exception as e:
                print(f"Error handling message: {e}")
                await self.trust_manager.on_invalid_message(message.sender_id)
                return False
        
        # If message should be propagated, add to pending queue
        if self._should_propagate(message):
            # Decrease TTL for propagation
            message.ttl -= 1
            self.pending_messages.append(message)
        
        return True
    
    def _should_propagate(self, message: Message) -> bool:
        """
        Determine if a message should be propagated.
        
        Args:
            message: Message to check
            
        Returns:
            True if message should be propagated
        """
        # Propagate gossip messages, custom data, and trust updates
        propagate_types = {
            MessageType.GOSSIP_MESSAGE,
            MessageType.CUSTOM_DATA,
            MessageType.TRUST_UPDATE,
            MessageType.PEER_ANNOUNCEMENT,
        }
        return message.msg_type in propagate_types and message.ttl > 0
    
    async def _gossip_loop(self):
        """Background task for gossiping messages."""
        while True:
            try:
                await asyncio.sleep(self.gossip_interval)
                
                if self.pending_messages:
                    await self._do_gossip()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in gossip loop: {e}")
    
    async def _do_gossip(self):
        """Perform one round of gossip."""
        if not self.pending_messages:
            return
        
        # Get random peers for gossip (fanout)
        peers = self.peer_manager.get_random_peers(
            self.fanout,
            exclude={self.node_id}
        )
        
        if not peers:
            return
        
        # Process pending messages
        messages_to_send = []
        while self.pending_messages and len(messages_to_send) < 10:  # Batch limit
            messages_to_send.append(self.pending_messages.popleft())
        
        # Send messages to selected peers
        # Note: Actual sending would be done by the network transport layer
        # This just prepares the gossip batch
        for peer in peers:
            for message in messages_to_send:
                # Skip if peer is the original sender
                if message.sender_id == peer.node_id:
                    continue
                
                # This would trigger the actual network send
                # For now, we just track statistics
                self.stats["messages_propagated"] += 1
                
                # Yield to event loop
                await asyncio.sleep(0)
    
    async def _has_seen(self, message_id: str) -> bool:
        """
        Check if we've seen a message before.
        
        Args:
            message_id: Message identifier
            
        Returns:
            True if message has been seen
        """
        # Check in-memory cache first
        if message_id in self.message_cache_set:
            return True
        
        # Check persistent storage
        return await self.storage.has_seen_message(message_id)
    
    async def _mark_seen(self, message_id: str):
        """
        Mark a message as seen.
        
        Args:
            message_id: Message identifier
        """
        # Add to in-memory cache
        if message_id not in self.message_cache_set:
            if len(self.message_cache) >= self.message_cache.maxlen:
                # Remove oldest from set
                oldest = self.message_cache[0]
                self.message_cache_set.discard(oldest)
            
            self.message_cache.append(message_id)
            self.message_cache_set.add(message_id)
        
        # Persist to storage
        await self.storage.mark_message_seen(message_id, self.node_id)
    
    def get_pending_messages_for_peer(self, peer_node_id: str) -> List[Message]:
        """
        Get messages pending for a specific peer.
        
        Args:
            peer_node_id: Target peer's node ID
            
        Returns:
            List of messages to send to this peer
        """
        # Filter messages that weren't originated by this peer
        return [
            msg for msg in self.pending_messages
            if msg.sender_id != peer_node_id
        ]
    
    def clear_pending_messages(self):
        """Clear all pending messages."""
        self.pending_messages.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get gossip protocol statistics.
        
        Returns:
            Dictionary of statistics
        """
        return {
            **self.stats,
            "pending_messages": len(self.pending_messages),
            "message_cache_size": len(self.message_cache),
        }
    
    async def request_anti_entropy(self, peer_node_id: str):
        """
        Request anti-entropy synchronization with a peer.
        
        This helps ensure eventual consistency by requesting
        any messages we might have missed.
        
        Args:
            peer_node_id: Peer to sync with
        """
        # Create a request for recent messages
        # The peer would respond with messages we haven't seen
        # This is a simplified version - a full implementation would
        # exchange bloom filters or vector clocks
        request = MessageFactory.create_peer_discovery(self.node_id)
        await self.broadcast(request)
