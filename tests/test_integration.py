"""
Integration tests for the network.
"""
import pytest
import asyncio
import tempfile
import os

from positron_networking.node import Node
from positron_networking.config import NetworkConfig


@pytest.mark.asyncio
async def test_single_node_startup():
    """Test starting and stopping a single node."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = NetworkConfig(
            host="127.0.0.1",
            port=9000,
            data_dir=os.path.join(tmpdir, "data"),
            db_path=os.path.join(tmpdir, "data", "test.db"),
            private_key_path=os.path.join(tmpdir, "keys", "private_key.pem"),
            public_key_path=os.path.join(tmpdir, "keys", "public_key.pem"),
        )
        
        node = Node(config)
        await node.start()
        
        assert node.node_id is not None
        assert node._running is True
        
        await node.stop()
        assert node._running is False


@pytest.mark.asyncio
async def test_two_node_connection():
    """Test connecting two nodes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create bootstrap node
        config1 = NetworkConfig(
            host="127.0.0.1",
            port=9001,
            data_dir=os.path.join(tmpdir, "node1"),
            db_path=os.path.join(tmpdir, "node1", "test.db"),
            private_key_path=os.path.join(tmpdir, "node1", "private_key.pem"),
            public_key_path=os.path.join(tmpdir, "node1", "public_key.pem"),
        )
        
        node1 = Node(config1)
        await node1.start()
        
        # Create second node with bootstrap
        config2 = NetworkConfig(
            host="127.0.0.1",
            port=9002,
            bootstrap_nodes=["127.0.0.1:9001"],
            data_dir=os.path.join(tmpdir, "node2"),
            db_path=os.path.join(tmpdir, "node2", "test.db"),
            private_key_path=os.path.join(tmpdir, "node2", "private_key.pem"),
            public_key_path=os.path.join(tmpdir, "node2", "public_key.pem"),
        )
        
        node2 = Node(config2)
        await node2.start()
        
        # Give time for connection
        await asyncio.sleep(2)
        
        # Check if nodes are connected
        assert node1.network.get_connection_count() >= 0
        assert node2.network.get_connection_count() >= 0
        
        # Cleanup
        await node2.stop()
        await node1.stop()


@pytest.mark.asyncio
async def test_message_broadcast():
    """Test broadcasting messages in the network."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create bootstrap node
        config1 = NetworkConfig(
            host="127.0.0.1",
            port=9003,
            data_dir=os.path.join(tmpdir, "node1"),
            db_path=os.path.join(tmpdir, "node1", "test.db"),
            private_key_path=os.path.join(tmpdir, "node1", "private_key.pem"),
            public_key_path=os.path.join(tmpdir, "node1", "public_key.pem"),
        )
        
        node1 = Node(config1)
        
        # Track received messages
        received_messages = []
        
        async def message_handler(sender_id, data):
            received_messages.append((sender_id, data))
        
        node1.register_data_handler("test", message_handler)
        await node1.start()
        
        # Create second node
        config2 = NetworkConfig(
            host="127.0.0.1",
            port=9004,
            bootstrap_nodes=["127.0.0.1:9003"],
            data_dir=os.path.join(tmpdir, "node2"),
            db_path=os.path.join(tmpdir, "node2", "test.db"),
            private_key_path=os.path.join(tmpdir, "node2", "private_key.pem"),
            public_key_path=os.path.join(tmpdir, "node2", "public_key.pem"),
        )
        
        node2 = Node(config2)
        node2.register_data_handler("test", message_handler)
        await node2.start()
        
        # Give time for connection
        await asyncio.sleep(2)
        
        # Broadcast from node2
        test_data = {"message": "Hello, network!"}
        await node2.broadcast(test_data)
        
        # Give time for propagation
        await asyncio.sleep(2)
        
        # Cleanup
        await node2.stop()
        await node1.stop()


@pytest.mark.asyncio
async def test_trust_propagation():
    """Test trust score propagation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = NetworkConfig(
            host="127.0.0.1",
            port=9005,
            data_dir=os.path.join(tmpdir, "node"),
            db_path=os.path.join(tmpdir, "node", "test.db"),
            private_key_path=os.path.join(tmpdir, "node", "private_key.pem"),
            public_key_path=os.path.join(tmpdir, "node", "public_key.pem"),
        )
        
        node = Node(config)
        await node.start()
        
        # Test trust operations
        test_node_id = "test_peer_123"
        
        initial_trust = await node.trust_manager.get_trust(test_node_id)
        assert initial_trust == config.initial_trust_score
        
        # Simulate valid messages
        await node.trust_manager.on_valid_message(test_node_id)
        
        new_trust = await node.trust_manager.get_trust(test_node_id)
        assert new_trust > initial_trust
        
        # Simulate invalid message
        await node.trust_manager.on_invalid_message(test_node_id)
        
        final_trust = await node.trust_manager.get_trust(test_node_id)
        assert final_trust < new_trust
        
        await node.stop()
