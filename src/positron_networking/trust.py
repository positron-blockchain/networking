"""
Trust and reputation management system for network peers.
"""
from typing import Dict, List, Optional
from positron_networking.protocol import PeerInfo
from positron_networking.storage import Storage
import time
import asyncio
import math


class TrustManager:
    """Manages trust scores and reputation for network peers."""
    
    def __init__(
        self,
        storage: Storage,
        initial_trust: float = 0.5,
        min_trust: float = 0.1,
        max_trust: float = 1.0,
        decay_rate: float = 0.01,
        decay_interval: float = 300.0
    ):
        """
        Initialize trust manager.
        
        Args:
            storage: Storage instance for persisting trust data
            initial_trust: Initial trust score for new peers
            min_trust: Minimum trust threshold
            max_trust: Maximum trust score
            decay_rate: Trust decay rate per interval
            decay_interval: Interval between trust decay operations
        """
        self.storage = storage
        self.initial_trust = initial_trust
        self.min_trust = min_trust
        self.max_trust = max_trust
        self.decay_rate = decay_rate
        self.decay_interval = decay_interval
        
        # In-memory trust cache for performance
        self.trust_cache: Dict[str, float] = {}
        
        # Track recent interactions
        self.interaction_history: Dict[str, List[float]] = {}
        
        self._decay_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start trust management background tasks."""
        self._decay_task = asyncio.create_task(self._trust_decay_loop())
    
    async def stop(self):
        """Stop trust management background tasks."""
        if self._decay_task:
            self._decay_task.cancel()
            try:
                await self._decay_task
            except asyncio.CancelledError:
                pass
    
    async def get_trust(self, node_id: str) -> float:
        """
        Get trust score for a node.
        
        Args:
            node_id: Node identifier
            
        Returns:
            Trust score (0.0 - 1.0)
        """
        if node_id in self.trust_cache:
            return self.trust_cache[node_id]
        
        peer = await self.storage.get_peer(node_id)
        if peer:
            self.trust_cache[node_id] = peer.trust_score
            return peer.trust_score
        
        return self.initial_trust
    
    async def set_trust(self, node_id: str, trust_score: float, reason: str = ""):
        """
        Set trust score for a node.
        
        Args:
            node_id: Node identifier
            trust_score: New trust score
            reason: Reason for trust change
        """
        old_trust = await self.get_trust(node_id)
        trust_score = max(0.0, min(self.max_trust, trust_score))
        
        self.trust_cache[node_id] = trust_score
        await self.storage.update_peer_trust(node_id, trust_score)
        
        # Log the trust change
        delta = trust_score - old_trust
        await self.storage.log_trust_event(node_id, "set_trust", delta, reason)
    
    async def adjust_trust(self, node_id: str, delta: float, reason: str = ""):
        """
        Adjust trust score by a delta amount.
        
        Args:
            node_id: Node identifier
            delta: Amount to change trust (can be negative)
            reason: Reason for adjustment
        """
        current = await self.get_trust(node_id)
        new_trust = max(0.0, min(self.max_trust, current + delta))
        await self.set_trust(node_id, new_trust, reason)
    
    async def on_valid_message(self, node_id: str, boost: float = 0.001):
        """
        Called when a valid message is received from a peer.
        
        Args:
            node_id: Node identifier
            boost: Trust boost amount
        """
        await self.adjust_trust(node_id, boost, "valid_message")
        await self.storage.increment_peer_stats(node_id, valid_messages=1)
        
        # Track interaction
        self._record_interaction(node_id, boost)
    
    async def on_invalid_message(self, node_id: str, penalty: float = 0.1):
        """
        Called when an invalid message is received from a peer.
        
        Args:
            node_id: Node identifier
            penalty: Trust penalty amount
        """
        await self.adjust_trust(node_id, -penalty, "invalid_message")
        await self.storage.increment_peer_stats(node_id, invalid_messages=1)
        
        # Track interaction
        self._record_interaction(node_id, -penalty)
    
    async def on_peer_timeout(self, node_id: str, penalty: float = 0.05):
        """
        Called when a peer times out.
        
        Args:
            node_id: Node identifier
            penalty: Trust penalty amount
        """
        await self.adjust_trust(node_id, -penalty, "timeout")
    
    async def on_successful_connection(self, node_id: str, boost: float = 0.005):
        """
        Called when successfully connecting to a peer.
        
        Args:
            node_id: Node identifier
            boost: Trust boost amount
        """
        await self.adjust_trust(node_id, boost, "successful_connection")
    
    async def is_trusted(self, node_id: str, threshold: Optional[float] = None) -> bool:
        """
        Check if a node is trusted.
        
        Args:
            node_id: Node identifier
            threshold: Custom trust threshold (uses min_trust if not provided)
            
        Returns:
            True if node is trusted
        """
        threshold = threshold or self.min_trust
        trust = await self.get_trust(node_id)
        return trust >= threshold
    
    async def get_trusted_peers(self, min_trust: Optional[float] = None) -> List[PeerInfo]:
        """
        Get list of trusted peers.
        
        Args:
            min_trust: Minimum trust threshold
            
        Returns:
            List of trusted peer information
        """
        threshold = min_trust or 0.7
        return await self.storage.get_trusted_peers(threshold)
    
    async def apply_transitive_trust(
        self,
        recommender_id: str,
        recommended_id: str,
        recommended_trust: float
    ):
        """
        Apply transitive trust from a recommender.
        
        Args:
            recommender_id: ID of the recommending node
            recommended_id: ID of the recommended node
            recommended_trust: Trust score from recommender
        """
        recommender_trust = await self.get_trust(recommender_id)
        
        # Weight the recommendation by the recommender's trust
        weighted_boost = recommended_trust * recommender_trust * 0.1
        
        await self.adjust_trust(
            recommended_id,
            weighted_boost,
            f"recommendation_from_{recommender_id}"
        )
    
    def _record_interaction(self, node_id: str, value: float):
        """Record an interaction for trend analysis."""
        if node_id not in self.interaction_history:
            self.interaction_history[node_id] = []
        
        self.interaction_history[node_id].append(value)
        
        # Keep only recent history (last 100 interactions)
        if len(self.interaction_history[node_id]) > 100:
            self.interaction_history[node_id].pop(0)
    
    def get_interaction_trend(self, node_id: str) -> float:
        """
        Get the trend of recent interactions.
        
        Args:
            node_id: Node identifier
            
        Returns:
            Trend value (positive for improving, negative for declining)
        """
        if node_id not in self.interaction_history:
            return 0.0
        
        history = self.interaction_history[node_id]
        if len(history) < 2:
            return 0.0
        
        # Simple linear regression slope
        n = len(history)
        x_mean = n / 2
        y_mean = sum(history) / n
        
        numerator = sum((i - x_mean) * (history[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    async def _trust_decay_loop(self):
        """Background task to apply trust decay over time."""
        while True:
            try:
                await asyncio.sleep(self.decay_interval)
                await self._apply_trust_decay()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue
                print(f"Error in trust decay loop: {e}")
    
    async def _apply_trust_decay(self):
        """Apply trust decay to all peers."""
        peers = await self.storage.get_all_peers()
        
        for peer in peers:
            # Decay trust towards the initial trust value
            current = peer.trust_score
            target = self.initial_trust
            
            # Exponential decay towards target
            new_trust = current + (target - current) * self.decay_rate
            
            if abs(new_trust - current) > 0.001:  # Only update if significant change
                await self.set_trust(peer.node_id, new_trust, "periodic_decay")
    
    async def compute_reputation_score(self, node_id: str) -> float:
        """
        Compute comprehensive reputation score.
        
        Args:
            node_id: Node identifier
            
        Returns:
            Reputation score incorporating multiple factors
        """
        trust = await self.get_trust(node_id)
        trend = self.get_interaction_trend(node_id)
        
        # Get peer stats
        peer = await self.storage.get_peer(node_id)
        if not peer:
            return trust
        
        # Weight factors
        trust_weight = 0.6
        trend_weight = 0.2
        stats_weight = 0.2
        
        # Compute stats score
        # (Could be expanded with more sophisticated metrics)
        stats_score = 0.5  # Baseline
        
        # Combine factors
        reputation = (
            trust * trust_weight +
            max(0, min(1, 0.5 + trend)) * trend_weight +
            stats_score * stats_weight
        )
        
        return max(0.0, min(1.0, reputation))
