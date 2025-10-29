"""
Distributed Hash Table (DHT) implementation based on Kademlia principles.

Provides distributed key-value storage with automatic replication, routing,
and fault tolerance across the peer-to-peer network.
"""
import asyncio
import hashlib
import time
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import structlog


@dataclass
class DHTNode:
    """Represents a node in the DHT."""
    node_id: str
    address: str
    last_seen: float = field(default_factory=time.time)
    
    def distance_to(self, other_id: str) -> int:
        """
        Calculate XOR distance to another node ID.
        
        Args:
            other_id: Target node ID
            
        Returns:
            XOR distance as integer
        """
        # Convert hex IDs to integers and XOR
        return int(self.node_id, 16) ^ int(other_id, 16)


@dataclass
class DHTValue:
    """Represents a value stored in the DHT."""
    key: str
    value: Any
    timestamp: float
    ttl: Optional[float] = None  # Time-to-live in seconds
    replicas: Set[str] = field(default_factory=set)  # Node IDs holding replicas
    
    def is_expired(self) -> bool:
        """Check if the value has expired."""
        if self.ttl is None:
            return False
        return time.time() > (self.timestamp + self.ttl)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'key': self.key,
            'value': self.value,
            'timestamp': self.timestamp,
            'ttl': self.ttl,
            'replicas': list(self.replicas),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DHTValue':
        """Create from dictionary."""
        return cls(
            key=data['key'],
            value=data['value'],
            timestamp=data['timestamp'],
            ttl=data.get('ttl'),
            replicas=set(data.get('replicas', [])),
        )


class KBucket:
    """
    K-bucket for storing nodes at a specific distance range.
    
    Implements the Kademlia bucket structure with LRU eviction.
    """
    
    def __init__(self, k: int = 20):
        """
        Initialize K-bucket.
        
        Args:
            k: Maximum number of nodes per bucket
        """
        self.k = k
        self.nodes: List[DHTNode] = []
        self.replacement_cache: List[DHTNode] = []
    
    def add_node(self, node: DHTNode) -> bool:
        """
        Add a node to the bucket.
        
        Args:
            node: Node to add
            
        Returns:
            True if added, False if bucket is full
        """
        # Update if already exists
        for i, existing in enumerate(self.nodes):
            if existing.node_id == node.node_id:
                self.nodes[i] = node
                return True
        
        # Add if space available
        if len(self.nodes) < self.k:
            self.nodes.append(node)
            return True
        
        # Add to replacement cache
        self.replacement_cache.append(node)
        if len(self.replacement_cache) > self.k:
            self.replacement_cache.pop(0)
        return False
    
    def remove_node(self, node_id: str) -> bool:
        """Remove a node from the bucket."""
        for i, node in enumerate(self.nodes):
            if node.node_id == node_id:
                self.nodes.pop(i)
                # Try to add from replacement cache
                if self.replacement_cache:
                    self.nodes.append(self.replacement_cache.pop(0))
                return True
        return False
    
    def get_nodes(self) -> List[DHTNode]:
        """Get all nodes in the bucket."""
        return self.nodes.copy()
    
    def is_full(self) -> bool:
        """Check if bucket is full."""
        return len(self.nodes) >= self.k


class DistributedHashTable:
    """
    Distributed Hash Table implementation based on Kademlia.
    
    Provides distributed key-value storage with:
    - XOR-based routing
    - Automatic replication
    - Fault tolerance
    - Efficient lookups (O(log n))
    """
    
    def __init__(
        self,
        node_id: str,
        address: str,
        k: int = 20,
        alpha: int = 3,
        replication_factor: int = 3,
        ttl_default: float = 3600.0,
        network_send_callback: Optional[Any] = None,
    ):
        """
        Initialize DHT.
        
        Args:
            node_id: This node's identifier (hex string)
            address: This node's network address
            k: Bucket size (number of nodes per bucket)
            alpha: Concurrency parameter for parallel lookups
            replication_factor: Number of nodes to replicate data to
            ttl_default: Default time-to-live for stored values (seconds)
            network_send_callback: Callback for sending network messages
        """
        self.node_id = node_id
        self.address = address
        self.k = k
        self.alpha = alpha
        self.replication_factor = replication_factor
        self.ttl_default = ttl_default
        self.network_send_callback = network_send_callback
        
        self.logger = structlog.get_logger()
        
        # Routing table (160 buckets for 160-bit SHA-1 IDs)
        self.buckets: List[KBucket] = [KBucket(k) for _ in range(160)]
        
        # Local storage
        self.storage: Dict[str, DHTValue] = {}
        
        # Pending lookups (key_hash -> future)
        self.pending_lookups: Dict[str, asyncio.Future] = {}
        
        # Pending stores (correlation_id -> future)
        self.pending_operations: Dict[str, asyncio.Future] = {}
        
        # Statistics
        self.stats = {
            'stores': 0,
            'retrievals': 0,
            'replications': 0,
            'expirations': 0,
            'lookups': 0,
            'network_stores': 0,
            'network_lookups': 0,
        }
        
        # Background tasks
        self._maintenance_task: Optional[asyncio.Task] = None
    
    def _get_bucket_index(self, distance: int) -> int:
        """
        Get the bucket index for a given XOR distance.
        
        Args:
            distance: XOR distance
            
        Returns:
            Bucket index (0-159)
        """
        if distance == 0:
            return 0
        return min(159, distance.bit_length() - 1)
    
    def _calculate_distance(self, id1: str, id2: str) -> int:
        """Calculate XOR distance between two node IDs."""
        return int(id1, 16) ^ int(id2, 16)
    
    def _hash_key(self, key: str) -> str:
        """Hash a key to a node ID."""
        return hashlib.sha1(key.encode()).hexdigest()
    
    def add_node(self, node_id: str, address: str) -> bool:
        """
        Add a node to the routing table.
        
        Args:
            node_id: Node identifier
            address: Node network address
            
        Returns:
            True if added successfully
        """
        if node_id == self.node_id:
            return False
        
        distance = self._calculate_distance(self.node_id, node_id)
        bucket_index = self._get_bucket_index(distance)
        
        node = DHTNode(node_id=node_id, address=address)
        return self.buckets[bucket_index].add_node(node)
    
    def remove_node(self, node_id: str) -> bool:
        """Remove a node from the routing table."""
        distance = self._calculate_distance(self.node_id, node_id)
        bucket_index = self._get_bucket_index(distance)
        return self.buckets[bucket_index].remove_node(node_id)
    
    def find_closest_nodes(self, target_id: str, count: int = None) -> List[DHTNode]:
        """
        Find the closest nodes to a target ID.
        
        Args:
            target_id: Target node ID
            count: Number of nodes to return (default: k)
            
        Returns:
            List of closest nodes, sorted by distance
        """
        if count is None:
            count = self.k
        
        # Collect all known nodes
        all_nodes = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.get_nodes())
        
        # Sort by distance to target
        all_nodes.sort(key=lambda n: self._calculate_distance(n.node_id, target_id))
        
        return all_nodes[:count]
    
    async def store(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        replicate: bool = True
    ) -> bool:
        """
        Store a key-value pair in the DHT.
        
        Args:
            key: Storage key
            value: Value to store
            ttl: Time-to-live in seconds (None = use default)
            replicate: Whether to replicate to other nodes
            
        Returns:
            True if stored successfully
        """
        if ttl is None:
            ttl = self.ttl_default
        
        # Hash the key to get target node ID
        key_hash = self._hash_key(key)
        
        # Store locally
        dht_value = DHTValue(
            key=key,
            value=value,
            timestamp=time.time(),
            ttl=ttl,
            replicas={self.node_id}
        )
        self.storage[key] = dht_value
        self.stats['stores'] += 1
        
        # Replicate to closest nodes if requested
        if replicate:
            await self._replicate_value(key_hash, dht_value)
        
        return True
    
    async def retrieve(self, key: str, local_only: bool = False) -> Optional[Any]:
        """
        Retrieve a value from the DHT.
        
        Args:
            key: Storage key
            local_only: Only check local storage
            
        Returns:
            Retrieved value or None if not found
        """
        self.stats['retrievals'] += 1
        
        # Check local storage first
        if key in self.storage:
            dht_value = self.storage[key]
            if not dht_value.is_expired():
                return dht_value.value
            else:
                # Clean up expired value
                del self.storage[key]
                self.stats['expirations'] += 1
        
        # If not found locally and remote lookup is allowed
        if not local_only:
            key_hash = self._hash_key(key)
            return await self._lookup_value(key_hash)
        
        return None
    
    async def delete(self, key: str, replicate: bool = True) -> bool:
        """
        Delete a key-value pair from the DHT.
        
        Args:
            key: Key to delete
            replicate: Whether to delete from replicas
            
        Returns:
            True if deleted
        """
        deleted = False
        
        if key in self.storage:
            del self.storage[key]
            deleted = True
        
        if replicate:
            key_hash = self._hash_key(key)
            await self._replicate_delete(key_hash)
        
        return deleted
    
    async def _replicate_value(self, key_hash: str, dht_value: DHTValue):
        """
        Replicate a value to closest nodes using network RPCs.
        
        Args:
            key_hash: Hashed key
            dht_value: Value to replicate
        """
        closest = self.find_closest_nodes(key_hash, self.replication_factor)
        
        if not self.network_send_callback:
            # No network available, just track local replicas
            for node in closest:
                dht_value.replicas.add(node.node_id)
            self.stats['replications'] += 1
            return
        
        # Send STORE RPCs to closest nodes
        store_tasks = []
        for node in closest:
            if node.node_id == self.node_id:
                continue
                
            try:
                # Create DHT_STORE message
                message_payload = {
                    'key': dht_value.key,
                    'value': dht_value.value,
                    'ttl': dht_value.ttl,
                    'timestamp': dht_value.timestamp,
                    'operation': 'store'
                }
                
                task = self._send_dht_message(
                    node.address,
                    'DHT_STORE',
                    message_payload
                )
                store_tasks.append(task)
                dht_value.replicas.add(node.node_id)
                
                self.logger.debug(
                    "replicating_value",
                    key=dht_value.key,
                    target_node=node.node_id,
                    target_address=node.address
                )
                
            except Exception as e:
                self.logger.warning(
                    "value_replication_failed",
                    node_id=node.node_id,
                    error=str(e)
                )
        
        # Wait for all replication tasks
        if store_tasks:
            results = await asyncio.gather(*store_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            
            self.logger.info(
                "value_replicated",
                key=dht_value.key,
                success_count=success_count,
                total_attempts=len(store_tasks)
            )
        
        self.stats['replications'] += 1
        self.stats['network_stores'] += len(store_tasks)
    
    async def _replicate_delete(self, key_hash: str):
        """
        Replicate a delete operation to closest nodes using network RPCs.
        
        Args:
            key_hash: Hashed key to delete
        """
        closest = self.find_closest_nodes(key_hash, self.replication_factor)
        
        if not self.network_send_callback:
            # No network available, log only
            self.logger.debug(
                "delete_replication_skipped_no_network",
                key_hash=key_hash,
                node_count=len(closest)
            )
            return
        
        # Send DELETE RPCs to replica nodes
        delete_tasks = []
        for node in closest:
            if node.node_id == self.node_id:
                continue
                
            try:
                # Create DHT_DELETE message
                message_payload = {
                    'key_hash': key_hash,
                    'operation': 'delete'
                }
                
                task = self._send_dht_message(
                    node.address,
                    'DHT_DELETE',
                    message_payload
                )
                delete_tasks.append(task)
                
                self.logger.debug(
                    "replicating_delete",
                    key_hash=key_hash,
                    target_node=node.node_id,
                    target_address=node.address
                )
                
            except Exception as e:
                self.logger.warning(
                    "delete_replication_failed",
                    node_id=node.node_id,
                    error=str(e)
                )
        
        # Wait for all deletion tasks
        if delete_tasks:
            results = await asyncio.gather(*delete_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            
            self.logger.info(
                "delete_replicated",
                key_hash=key_hash,
                success_count=success_count,
                total_attempts=len(delete_tasks)
            )
    
    async def _lookup_value(self, key_hash: str) -> Optional[Any]:
        """
        Perform iterative lookup for a value using network RPCs.
        
        This performs an iterative node lookup to find the value,
        querying progressively closer nodes until the value is found.
        
        Args:
            key_hash: Hashed key
            
        Returns:
            Value if found, None otherwise
        """
        if not self.network_send_callback:
            # No network available - can only find local values
            self.logger.debug("lookup_skipped_no_network", key_hash=key_hash)
            return None
        
        # Track queried nodes to avoid loops
        queried_nodes: Set[str] = set()
        
        # Get closest nodes we know about
        closest_nodes = self.find_closest_nodes(key_hash, self.alpha)
        
        if not closest_nodes:
            self.logger.debug("no_nodes_for_lookup", key_hash=key_hash)
            return None
        
        # Iterative lookup process
        max_iterations = 20  # Prevent infinite loops
        iteration = 0
        found_value = None
        
        while iteration < max_iterations and closest_nodes and found_value is None:
            iteration += 1
            
            # Query the closest unqueried nodes in parallel
            query_tasks = []
            nodes_to_query = []
            
            for node in closest_nodes:
                if node.node_id not in queried_nodes:
                    nodes_to_query.append(node)
                    queried_nodes.add(node.node_id)
                    
                    # Send FIND_VALUE RPC
                    message_payload = {
                        'key_hash': key_hash,
                        'operation': 'find_value'
                    }
                    
                    task = self._send_dht_message(
                        node.address,
                        'DHT_FIND_VALUE',
                        message_payload
                    )
                    query_tasks.append((node, task))
                    
                    self.logger.debug(
                        "querying_node_for_value",
                        node_id=node.node_id,
                        key_hash=key_hash,
                        iteration=iteration
                    )
                    
                if len(nodes_to_query) >= self.alpha:
                    break
            
            if not query_tasks:
                # No more nodes to query
                break
            
            # Wait for responses
            for node, task in query_tasks:
                try:
                    response = await asyncio.wait_for(task, timeout=5.0)
                    
                    if response and 'value' in response:
                        # Found the value!
                        found_value = response['value']
                        self.logger.info(
                            "value_found",
                            key_hash=key_hash,
                            found_at_node=node.node_id,
                            iteration=iteration
                        )
                        break
                    elif response and 'closer_nodes' in response:
                        # Got closer nodes, add them to our search
                        for node_data in response['closer_nodes']:
                            new_node = DHTNode(
                                node_id=node_data['node_id'],
                                address=node_data['address']
                            )
                            if new_node.node_id not in queried_nodes:
                                # Calculate distance and insert in sorted order
                                dist = self._calculate_distance(new_node.node_id, key_hash)
                                self.add_node(new_node.node_id, new_node.address)
                                
                except asyncio.TimeoutError:
                    self.logger.debug(
                        "lookup_timeout",
                        node_id=node.node_id,
                        key_hash=key_hash
                    )
                except Exception as e:
                    self.logger.warning(
                        "lookup_error",
                        node_id=node.node_id,
                        key_hash=key_hash,
                        error=str(e)
                    )
            
            if found_value is None:
                # Update closest_nodes for next iteration
                closest_nodes = self.find_closest_nodes(key_hash, self.alpha)
                # Filter out already queried nodes
                closest_nodes = [n for n in closest_nodes if n.node_id not in queried_nodes]
        
        self.stats['lookups'] += 1
        self.stats['network_lookups'] += 1
        
        self.logger.debug(
            "lookup_complete",
            key_hash=key_hash,
            iterations=iteration,
            queried_count=len(queried_nodes),
            found=found_value is not None
        )
        
        return found_value
    
    async def _send_dht_message(self, target_address: str, message_type: str, payload: dict) -> Optional[dict]:
        """
        Send a DHT message to a target node.
        
        Args:
            target_address: Target node address
            message_type: Type of DHT message (DHT_STORE, DHT_FIND_VALUE, etc.)
            payload: Message payload
            
        Returns:
            Response payload if successful, None otherwise
        """
        if not self.network_send_callback:
            return None
        
        try:
            # Generate correlation ID for tracking responses
            correlation_id = hashlib.sha256(
                f"{target_address}{message_type}{time.time()}".encode()
            ).hexdigest()[:16]
            
            # Create future for response
            response_future = asyncio.Future()
            self.pending_operations[correlation_id] = response_future
            
            # Add correlation ID to payload
            payload['correlation_id'] = correlation_id
            payload['sender_id'] = self.node_id
            payload['sender_address'] = self.address
            
            # Send message via network callback
            await self.network_send_callback(target_address, message_type, payload)
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(response_future, timeout=10.0)
                return response
            except asyncio.TimeoutError:
                self.logger.debug(
                    "dht_message_timeout",
                    target=target_address,
                    message_type=message_type
                )
                return None
            finally:
                # Clean up pending operation
                self.pending_operations.pop(correlation_id, None)
                
        except Exception as e:
            self.logger.error(
                "dht_message_send_error",
                target=target_address,
                message_type=message_type,
                error=str(e)
            )
            return None
    
    async def handle_dht_message(self, message_type: str, payload: dict) -> Optional[dict]:
        """
        Handle incoming DHT RPC messages.
        
        Args:
            message_type: Type of DHT message
            payload: Message payload
            
        Returns:
            Response payload
        """
        sender_id = payload.get('sender_id')
        sender_address = payload.get('sender_address')
        correlation_id = payload.get('correlation_id')
        
        # Add sender to routing table
        if sender_id and sender_address:
            self.add_node(sender_id, sender_address)
        
        try:
            if message_type == 'DHT_STORE':
                # Handle STORE request
                key = payload.get('key')
                value = payload.get('value')
                ttl = payload.get('ttl', self.ttl_default)
                timestamp = payload.get('timestamp', time.time())
                
                dht_value = DHTValue(
                    key=key,
                    value=value,
                    timestamp=timestamp,
                    ttl=ttl,
                    replicas={self.node_id, sender_id}
                )
                self.storage[key] = dht_value
                
                self.logger.debug("dht_store_received", key=key, from_node=sender_id)
                
                return {'status': 'success', 'correlation_id': correlation_id}
            
            elif message_type == 'DHT_FIND_VALUE':
                # Handle FIND_VALUE request
                key_hash = payload.get('key_hash')
                
                # Check if we have the value locally
                for key, dht_value in self.storage.items():
                    if self._hash_key(key) == key_hash and not dht_value.is_expired():
                        self.logger.debug("dht_value_found_locally", key_hash=key_hash)
                        return {
                            'value': dht_value.value,
                            'correlation_id': correlation_id
                        }
                
                # Value not found, return closer nodes
                closer_nodes = self.find_closest_nodes(key_hash, self.k)
                nodes_data = [
                    {'node_id': n.node_id, 'address': n.address}
                    for n in closer_nodes
                ]
                
                self.logger.debug(
                    "dht_returning_closer_nodes",
                    key_hash=key_hash,
                    node_count=len(nodes_data)
                )
                
                return {
                    'closer_nodes': nodes_data,
                    'correlation_id': correlation_id
                }
            
            elif message_type == 'DHT_DELETE':
                # Handle DELETE request
                key_hash = payload.get('key_hash')
                
                # Find and delete matching keys
                keys_to_delete = []
                for key in self.storage:
                    if self._hash_key(key) == key_hash:
                        keys_to_delete.append(key)
                
                for key in keys_to_delete:
                    del self.storage[key]
                
                self.logger.debug(
                    "dht_delete_received",
                    key_hash=key_hash,
                    deleted_count=len(keys_to_delete)
                )
                
                return {'status': 'success', 'correlation_id': correlation_id}
            
            elif message_type in ['DHT_STORE_RESPONSE', 'DHT_FIND_VALUE_RESPONSE', 'DHT_DELETE_RESPONSE']:
                # Handle responses to our requests
                if correlation_id and correlation_id in self.pending_operations:
                    future = self.pending_operations[correlation_id]
                    if not future.done():
                        future.set_result(payload)
                
                return None
            
        except Exception as e:
            self.logger.error(
                "dht_message_handling_error",
                message_type=message_type,
                error=str(e)
            )
            return {'status': 'error', 'error': str(e), 'correlation_id': correlation_id}
        
        return None
    
    async def start(self):
        """Start DHT background maintenance tasks."""
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
    
    async def stop(self):
        """Stop DHT background tasks."""
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
    
    async def _maintenance_loop(self):
        """
        Background task for DHT maintenance.
        
        Performs:
        - Bucket refresh
        - Value replication
        - Expiration cleanup
        """
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                # Clean up expired values
                await self._cleanup_expired()
                
                # Republish values close to expiration
                await self._republish_values()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("dht_maintenance_error", error=str(e))
    
    async def _cleanup_expired(self):
        """Remove expired values from storage."""
        expired_keys = []
        
        for key, dht_value in self.storage.items():
            if dht_value.is_expired():
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.storage[key]
            self.stats['expirations'] += 1
    
    async def _republish_values(self):
        """Republish values that are close to expiration."""
        current_time = time.time()
        
        for key, dht_value in self.storage.items():
            if dht_value.ttl is not None:
                time_remaining = (dht_value.timestamp + dht_value.ttl) - current_time
                
                # Republish if less than 25% of TTL remains
                if 0 < time_remaining < (dht_value.ttl * 0.25):
                    key_hash = self._hash_key(key)
                    await self._replicate_value(key_hash, dht_value)
    
    def get_statistics(self) -> dict:
        """
        Get DHT statistics.
        
        Returns:
            Dictionary of statistics
        """
        total_nodes = sum(len(bucket.nodes) for bucket in self.buckets)
        non_empty_buckets = sum(1 for bucket in self.buckets if bucket.nodes)
        
        return {
            **self.stats,
            'stored_keys': len(self.storage),
            'total_nodes': total_nodes,
            'non_empty_buckets': non_empty_buckets,
            'avg_bucket_size': total_nodes / non_empty_buckets if non_empty_buckets > 0 else 0,
        }
    
    def get_stored_keys(self) -> List[str]:
        """Get all keys stored locally."""
        return list(self.storage.keys())
    
    def get_bucket_info(self) -> List[dict]:
        """
        Get information about all buckets.
        
        Returns:
            List of bucket information dictionaries
        """
        return [
            {
                'index': i,
                'node_count': len(bucket.nodes),
                'is_full': bucket.is_full(),
                'replacement_cache_size': len(bucket.replacement_cache),
            }
            for i, bucket in enumerate(self.buckets)
            if bucket.nodes or bucket.replacement_cache
        ]
