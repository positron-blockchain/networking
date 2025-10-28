"""
Comprehensive tests for Distributed Hash Table (DHT) implementation.
"""
import pytest
import asyncio
import time
from positron_networking.dht import (
    DHTNode, DHTValue, KBucket, DistributedHashTable
)


class TestDHTNode:
    """Test cases for DHTNode class."""
    
    def test_initialization(self):
        """Test DHT node initialization."""
        node = DHTNode(node_id="abc123", address="127.0.0.1:8888")
        
        assert node.node_id == "abc123"
        assert node.address == "127.0.0.1:8888"
        assert node.last_seen > 0
    
    def test_distance_calculation(self):
        """Test XOR distance calculation."""
        node1 = DHTNode(node_id="0f", address="127.0.0.1:8888")
        node2_id = "f0"
        
        distance = node1.distance_to(node2_id)
        
        # 0x0f XOR 0xf0 = 0xff = 255
        assert distance == 255


class TestDHTValue:
    """Test cases for DHTValue class."""
    
    def test_initialization(self):
        """Test DHT value initialization."""
        value = DHTValue(
            key="test_key",
            value={"data": "test"},
            timestamp=time.time(),
            ttl=3600.0
        )
        
        assert value.key == "test_key"
        assert value.value == {"data": "test"}
        assert not value.is_expired()
    
    def test_expiration(self):
        """Test value expiration."""
        # Create expired value
        old_time = time.time() - 7200  # 2 hours ago
        value = DHTValue(
            key="test_key",
            value="test_data",
            timestamp=old_time,
            ttl=3600.0  # 1 hour TTL
        )
        
        assert value.is_expired()
    
    def test_no_expiration(self):
        """Test values without TTL don't expire."""
        old_time = time.time() - 7200
        value = DHTValue(
            key="test_key",
            value="test_data",
            timestamp=old_time,
            ttl=None  # No expiration
        )
        
        assert not value.is_expired()
    
    def test_serialization(self):
        """Test value serialization and deserialization."""
        original = DHTValue(
            key="test_key",
            value={"nested": "data"},
            timestamp=time.time(),
            ttl=3600.0,
            replicas={"node1", "node2"}
        )
        
        # Serialize
        data = original.to_dict()
        
        # Deserialize
        restored = DHTValue.from_dict(data)
        
        assert restored.key == original.key
        assert restored.value == original.value
        assert restored.timestamp == original.timestamp
        assert restored.ttl == original.ttl
        assert restored.replicas == original.replicas


class TestKBucket:
    """Test cases for KBucket class."""
    
    def test_initialization(self):
        """Test K-bucket initialization."""
        bucket = KBucket(k=20)
        
        assert bucket.k == 20
        assert len(bucket.nodes) == 0
        assert len(bucket.replacement_cache) == 0
    
    def test_add_node(self):
        """Test adding nodes to bucket."""
        bucket = KBucket(k=3)
        
        node1 = DHTNode(node_id="abc", address="127.0.0.1:8888")
        node2 = DHTNode(node_id="def", address="127.0.0.1:8889")
        
        assert bucket.add_node(node1)
        assert bucket.add_node(node2)
        assert len(bucket.nodes) == 2
    
    def test_bucket_full(self):
        """Test bucket behavior when full."""
        bucket = KBucket(k=2)
        
        node1 = DHTNode(node_id="aaa", address="127.0.0.1:8888")
        node2 = DHTNode(node_id="bbb", address="127.0.0.1:8889")
        node3 = DHTNode(node_id="ccc", address="127.0.0.1:8890")
        
        assert bucket.add_node(node1)
        assert bucket.add_node(node2)
        assert bucket.is_full()
        
        # Third node should go to replacement cache
        assert not bucket.add_node(node3)
        assert len(bucket.replacement_cache) == 1
    
    def test_update_existing_node(self):
        """Test updating an existing node in bucket."""
        bucket = KBucket(k=3)
        
        node1 = DHTNode(node_id="abc", address="127.0.0.1:8888")
        bucket.add_node(node1)
        
        # Update same node ID with new info
        node1_updated = DHTNode(node_id="abc", address="127.0.0.1:9999")
        assert bucket.add_node(node1_updated)
        
        # Should still have only 1 node
        assert len(bucket.nodes) == 1
        # Address should be updated
        assert bucket.nodes[0].address == "127.0.0.1:9999"
    
    def test_remove_node(self):
        """Test removing nodes from bucket."""
        bucket = KBucket(k=3)
        
        node1 = DHTNode(node_id="abc", address="127.0.0.1:8888")
        node2 = DHTNode(node_id="def", address="127.0.0.1:8889")
        
        bucket.add_node(node1)
        bucket.add_node(node2)
        
        assert bucket.remove_node("abc")
        assert len(bucket.nodes) == 1
        assert bucket.nodes[0].node_id == "def"
    
    def test_replacement_cache_promotion(self):
        """Test that replacement cache nodes are promoted when space available."""
        bucket = KBucket(k=2)
        
        node1 = DHTNode(node_id="aaa", address="127.0.0.1:8888")
        node2 = DHTNode(node_id="bbb", address="127.0.0.1:8889")
        node3 = DHTNode(node_id="ccc", address="127.0.0.1:8890")
        
        bucket.add_node(node1)
        bucket.add_node(node2)
        bucket.add_node(node3)  # Goes to replacement cache
        
        # Remove a node
        bucket.remove_node("aaa")
        
        # Replacement should be promoted
        assert len(bucket.nodes) == 2
        assert any(n.node_id == "ccc" for n in bucket.nodes)


@pytest.mark.asyncio
class TestDistributedHashTable:
    """Test cases for DistributedHashTable class."""
    
    async def test_initialization(self):
        """Test DHT initialization."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        assert dht.node_id == "abc123"
        assert dht.address == "127.0.0.1:8888"
        assert len(dht.buckets) == 160  # SHA-1 has 160 bits
        assert len(dht.storage) == 0
    
    async def test_add_node(self):
        """Test adding nodes to routing table."""
        dht = DistributedHashTable(
            node_id="0000000000000000000000000000000000000000",
            address="127.0.0.1:8888"
        )
        
        # Add a node
        result = dht.add_node(
            node_id="0000000000000000000000000000000000000001",
            address="127.0.0.1:8889"
        )
        
        assert result is True
    
    async def test_cannot_add_self(self):
        """Test that node cannot add itself."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        result = dht.add_node(node_id="abc123", address="127.0.0.1:8888")
        assert result is False
    
    async def test_remove_node(self):
        """Test removing nodes from routing table."""
        dht = DistributedHashTable(
            node_id="0000000000000000000000000000000000000000",
            address="127.0.0.1:8888"
        )
        
        node_id = "0000000000000000000000000000000000000001"
        dht.add_node(node_id=node_id, address="127.0.0.1:8889")
        
        result = dht.remove_node(node_id)
        assert result is True
    
    async def test_find_closest_nodes(self):
        """Test finding closest nodes to a target."""
        dht = DistributedHashTable(
            node_id="0000000000000000000000000000000000000000",
            address="127.0.0.1:8888",
            k=20
        )
        
        # Add several nodes
        for i in range(1, 11):
            dht.add_node(
                node_id=f"000000000000000000000000000000000000000{i}",
                address=f"127.0.0.1:888{i}"
            )
        
        # Find closest to a target
        target = "0000000000000000000000000000000000000005"
        closest = dht.find_closest_nodes(target, count=3)
        
        assert len(closest) <= 3
        assert all(isinstance(node, DHTNode) for node in closest)
    
    async def test_store_and_retrieve(self):
        """Test storing and retrieving values."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        # Store a value
        result = await dht.store("test_key", "test_value", replicate=False)
        assert result is True
        
        # Retrieve the value
        value = await dht.retrieve("test_key", local_only=True)
        assert value == "test_value"
    
    async def test_store_with_ttl(self):
        """Test storing values with TTL."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        # Store with short TTL
        await dht.store("temp_key", "temp_value", ttl=0.1, replicate=False)
        
        # Should be retrievable immediately
        value = await dht.retrieve("temp_key", local_only=True)
        assert value == "temp_value"
        
        # Wait for expiration
        await asyncio.sleep(0.2)
        
        # Should be expired and return None
        value = await dht.retrieve("temp_key", local_only=True)
        assert value is None
    
    async def test_delete(self):
        """Test deleting values."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        # Store and then delete
        await dht.store("delete_me", "value", replicate=False)
        result = await dht.delete("delete_me", replicate=False)
        
        assert result is True
        
        # Should not be retrievable
        value = await dht.retrieve("delete_me", local_only=True)
        assert value is None
    
    async def test_complex_values(self):
        """Test storing complex data structures."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        complex_value = {
            "list": [1, 2, 3],
            "nested": {"key": "value"},
            "number": 42
        }
        
        await dht.store("complex", complex_value, replicate=False)
        retrieved = await dht.retrieve("complex", local_only=True)
        
        assert retrieved == complex_value
    
    async def test_get_statistics(self):
        """Test getting DHT statistics."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        # Add some data
        await dht.store("key1", "value1", replicate=False)
        await dht.store("key2", "value2", replicate=False)
        
        stats = dht.get_statistics()
        
        assert isinstance(stats, dict)
        assert stats['stores'] == 2
        assert stats['stored_keys'] == 2
        assert 'retrievals' in stats
        assert 'replications' in stats
    
    async def test_get_stored_keys(self):
        """Test getting list of stored keys."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        keys = ["key1", "key2", "key3"]
        for key in keys:
            await dht.store(key, f"value_{key}", replicate=False)
        
        stored_keys = dht.get_stored_keys()
        
        assert set(stored_keys) == set(keys)
    
    async def test_bucket_info(self):
        """Test getting bucket information."""
        dht = DistributedHashTable(
            node_id="0000000000000000000000000000000000000000",
            address="127.0.0.1:8888"
        )
        
        # Add some nodes
        for i in range(1, 6):
            dht.add_node(
                node_id=f"000000000000000000000000000000000000000{i}",
                address=f"127.0.0.1:888{i}"
            )
        
        bucket_info = dht.get_bucket_info()
        
        assert isinstance(bucket_info, list)
        # Should have information for non-empty buckets
        assert len(bucket_info) > 0
    
    async def test_start_and_stop(self):
        """Test starting and stopping DHT."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        await dht.start()
        
        # Should have maintenance task running
        assert dht._maintenance_task is not None
        
        await dht.stop()
        
        # Task should be cancelled
        assert dht._maintenance_task.cancelled() or dht._maintenance_task.done()
    
    async def test_cleanup_expired(self):
        """Test automatic cleanup of expired values."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        # Store with very short TTL
        await dht.store("expire1", "value1", ttl=0.1, replicate=False)
        await dht.store("expire2", "value2", ttl=0.1, replicate=False)
        await dht.store("persist", "value3", ttl=None, replicate=False)
        
        # Wait for expiration
        await asyncio.sleep(0.2)
        
        # Manually trigger cleanup
        await dht._cleanup_expired()
        
        # Expired values should be gone
        assert "expire1" not in dht.storage
        assert "expire2" not in dht.storage
        # Persistent value should remain
        assert "persist" in dht.storage


@pytest.mark.asyncio
class TestDHTIntegration:
    """Integration tests for DHT operations."""
    
    async def test_multiple_dhts(self):
        """Test multiple DHT instances working together."""
        # Create two DHT instances
        dht1 = DistributedHashTable(
            node_id="0000000000000000000000000000000000000001",
            address="127.0.0.1:8888"
        )
        dht2 = DistributedHashTable(
            node_id="0000000000000000000000000000000000000002",
            address="127.0.0.1:8889"
        )
        
        # Add each other to routing tables
        dht1.add_node(dht2.node_id, dht2.address)
        dht2.add_node(dht1.node_id, dht1.address)
        
        # Store value in dht1
        await dht1.store("shared_key", "shared_value", replicate=False)
        
        # In a full implementation, dht2 could retrieve from dht1
        # For now, we just verify local storage works
        value = await dht1.retrieve("shared_key", local_only=True)
        assert value == "shared_value"
    
    async def test_key_distribution(self):
        """Test that keys are distributed based on hash."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        # Store multiple keys
        keys = [f"key_{i}" for i in range(100)]
        for key in keys:
            await dht.store(key, f"value_{key}", replicate=False)
        
        # All keys should be stored locally (no remote nodes)
        assert len(dht.storage) == 100
    
    async def test_concurrent_operations(self):
        """Test concurrent DHT operations."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        # Concurrent stores
        store_tasks = [
            dht.store(f"key_{i}", f"value_{i}", replicate=False)
            for i in range(50)
        ]
        await asyncio.gather(*store_tasks)
        
        # Concurrent retrievals
        retrieve_tasks = [
            dht.retrieve(f"key_{i}", local_only=True)
            for i in range(50)
        ]
        results = await asyncio.gather(*retrieve_tasks)
        
        # All should succeed
        assert all(results[i] == f"value_{i}" for i in range(50))


@pytest.mark.asyncio
class TestDHTEdgeCases:
    """Test edge cases and error conditions."""
    
    async def test_empty_key(self):
        """Test storing with empty key."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        await dht.store("", "value", replicate=False)
        value = await dht.retrieve("", local_only=True)
        
        assert value == "value"
    
    async def test_none_value(self):
        """Test storing None as a value."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        await dht.store("null_key", None, replicate=False)
        value = await dht.retrieve("null_key", local_only=True)
        
        assert value is None
    
    async def test_overwrite_key(self):
        """Test overwriting an existing key."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        await dht.store("key", "value1", replicate=False)
        await dht.store("key", "value2", replicate=False)
        
        value = await dht.retrieve("key", local_only=True)
        assert value == "value2"
    
    async def test_retrieve_nonexistent(self):
        """Test retrieving non-existent key."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        value = await dht.retrieve("nonexistent", local_only=True)
        assert value is None
    
    async def test_delete_nonexistent(self):
        """Test deleting non-existent key."""
        dht = DistributedHashTable(
            node_id="abc123",
            address="127.0.0.1:8888"
        )
        
        result = await dht.delete("nonexistent", replicate=False)
        # Should return False but not error
        assert result is False
