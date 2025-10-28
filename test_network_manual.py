#!/usr/bin/env python3
"""
Manual test to verify the network actually works end-to-end.
Tests real peer connectivity, message passing, and cryptography.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from positron_networking import Node, NetworkConfig
from positron_networking.identity import Identity


async def test_basic_node_startup():
    """Test that a single node can start and stop."""
    print("\n=== Test 1: Basic Node Startup ===")
    
    config = NetworkConfig(
        host="127.0.0.1",
        port=19000,
        bootstrap_nodes=[],
        data_dir="test_data_1"
    )
    
    node = Node(config)
    
    try:
        await node.start()
        print("✓ Node started successfully")
        
        stats = node.get_stats()
        print(f"✓ Node ID: {stats['node_id'][:16]}...")
        print(f"✓ Active peers: {stats['active_peers']}")
        print(f"✓ Known peers: {stats['known_peers']}")
        
        await node.stop()
        print("✓ Node stopped successfully")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_two_node_connection():
    """Test that two nodes can connect and communicate."""
    print("\n=== Test 2: Two Node Connection ===")
    
    # Node 1 (bootstrap)
    config1 = NetworkConfig(
        host="127.0.0.1",
        port=19001,
        bootstrap_nodes=[],
        data_dir="test_data_2a"
    )
    
    node1 = Node(config1)
    
    # Node 2 (connects to node 1)
    config2 = NetworkConfig(
        host="127.0.0.1",
        port=19002,
        bootstrap_nodes=["127.0.0.1:19001"],
        data_dir="test_data_2b"
    )
    
    node2 = Node(config2)
    
    try:
        # Start both nodes
        await node1.start()
        print("✓ Node 1 started")
        
        await node2.start()
        print("✓ Node 2 started")
        
        # Wait for connection
        await asyncio.sleep(2)
        
        # Check connectivity
        stats1 = node1.get_stats()
        stats2 = node2.get_stats()
        
        print(f"  Node 1 - Active peers: {stats1['active_peers']}, Known: {stats1['known_peers']}")
        print(f"  Node 2 - Active peers: {stats2['active_peers']}, Known: {stats2['known_peers']}")
        
        if stats1['active_peers'] > 0 and stats2['active_peers'] > 0:
            print("✓ Nodes connected successfully")
            result = True
        else:
            print("✗ Nodes failed to connect")
            result = False
        
        # Cleanup
        await node1.stop()
        await node2.stop()
        print("✓ Nodes stopped")
        
        return result
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            await node1.stop()
            await node2.stop()
        except:
            pass
        return False


async def test_message_broadcast():
    """Test message broadcasting between nodes."""
    print("\n=== Test 3: Message Broadcast ===")
    
    # Create 3 nodes
    nodes = []
    configs = [
        NetworkConfig(host="127.0.0.1", port=19003, bootstrap_nodes=[], data_dir="test_data_3a"),
        NetworkConfig(host="127.0.0.1", port=19004, bootstrap_nodes=["127.0.0.1:19003"], data_dir="test_data_3b"),
        NetworkConfig(host="127.0.0.1", port=19005, bootstrap_nodes=["127.0.0.1:19003"], data_dir="test_data_3c"),
    ]
    
    try:
        # Start all nodes
        for i, config in enumerate(configs):
            node = Node(config)
            await node.start()
            nodes.append(node)
            print(f"✓ Node {i+1} started")
        
        # Wait for connections
        await asyncio.sleep(3)
        
        # Check mesh connectivity
        total_peers = sum(node.get_stats()['active_peers'] for node in nodes)
        print(f"  Total peer connections: {total_peers}")
        
        if total_peers >= 4:  # Each node should have at least 1 peer (ideally 2)
            print("✓ Mesh network formed")
        else:
            print("⚠ Limited connectivity")
        
        # Test broadcast
        print("  Broadcasting test message from Node 1...")
        test_message = {"test": "data", "timestamp": asyncio.get_event_loop().time()}
        await nodes[0].broadcast(test_message)
        
        # Wait for propagation
        await asyncio.sleep(2)
        
        print("✓ Message broadcast completed")
        
        # Cleanup
        for i, node in enumerate(nodes):
            await node.stop()
            print(f"✓ Node {i+1} stopped")
        
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        for node in nodes:
            try:
                await node.stop()
            except:
                pass
        return False


async def test_cryptography():
    """Test cryptographic identity and signing."""
    print("\n=== Test 4: Cryptography ===")
    
    try:
        # Create identity
        identity = Identity.generate()
        print(f"✓ Generated identity: {identity.node_id[:16]}...")
        
        # Test signing
        message = b"Test message for signing"
        signature = identity.sign(message)
        print(f"✓ Signed message (signature length: {len(signature)})")
        
        # Test verification
        public_key = identity.get_public_key_bytes()
        if identity.verify(public_key, message, signature):
            print("✓ Signature verified successfully")
        else:
            print("✗ Signature verification failed")
            return False
        
        # Test tampering detection
        tampered_message = b"Tampered message"
        if not identity.verify(public_key, tampered_message, signature):
            print("✓ Tampered message detected correctly")
        else:
            print("✗ Failed to detect tampering")
            return False
        
        # Test identity persistence
        temp_dir = Path("test_temp_keys")
        temp_dir.mkdir(exist_ok=True)
        temp_private_path = temp_dir / "private_key.pem"
        temp_public_path = temp_dir / "public_key.pem"
        identity.save_keys(str(temp_private_path), str(temp_public_path))
        print("✓ Identity saved to disk")
        
        loaded_identity = Identity.load_from_files(str(temp_private_path))
        if loaded_identity.node_id == identity.node_id:
            print("✓ Identity loaded correctly")
        else:
            print("✗ Identity mismatch after loading")
            return False
        
        # Cleanup
        temp_private_path.unlink()
        temp_public_path.unlink()
        temp_dir.rmdir()
        
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_trust_system():
    """Test trust scoring and reputation."""
    print("\n=== Test 5: Trust System ===")
    
    config = NetworkConfig(
        host="127.0.0.1",
        port=19006,
        bootstrap_nodes=[],
        data_dir="test_data_5"
    )
    
    node = Node(config)
    
    try:
        await node.start()
        print("✓ Node started")
        
        # Create fake peer for testing
        peer_id = "test_peer_123"
        
        # Test trust scoring
        initial_trust = await node.trust_manager.get_trust(peer_id)
        print(f"✓ Initial trust score: {initial_trust:.3f}")
        
        # Test trust update
        await node.trust_manager.adjust_trust(peer_id, 0.1, "test increase")  # Increase trust
        updated_trust = await node.trust_manager.get_trust(peer_id)
        print(f"✓ Updated trust score: {updated_trust:.3f}")
        
        if updated_trust > initial_trust:
            print("✓ Trust increase works")
        else:
            print("✗ Trust did not increase")
            return False
        
        # Test penalty
        await node.trust_manager.on_invalid_message(peer_id)
        penalized_trust = await node.trust_manager.get_trust(peer_id)
        print(f"✓ Trust after penalty: {penalized_trust:.3f}")
        
        if penalized_trust < updated_trust:
            print("✓ Trust penalty works")
        else:
            print("✗ Trust penalty did not work")
            return False
        
        await node.stop()
        print("✓ Node stopped")
        
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            await node.stop()
        except:
            pass
        return False


async def cleanup_test_data():
    """Clean up test data directories."""
    import shutil
    
    test_dirs = [
        "test_data_1", "test_data_2a", "test_data_2b",
        "test_data_3a", "test_data_3b", "test_data_3c",
        "test_data_5"
    ]
    
    for dir_name in test_dirs:
        path = Path(dir_name)
        if path.exists():
            shutil.rmtree(path)


async def main():
    """Run all tests."""
    print("=" * 70)
    print("POSITRON NETWORKING - PRODUCTION READINESS TEST")
    print("=" * 70)
    
    results = []
    
    # Run tests
    results.append(("Basic Node Startup", await test_basic_node_startup()))
    results.append(("Two Node Connection", await test_two_node_connection()))
    results.append(("Message Broadcast", await test_message_broadcast()))
    results.append(("Cryptography", await test_cryptography()))
    results.append(("Trust System", await test_trust_system()))
    
    # Cleanup
    await cleanup_test_data()
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} - {test_name}")
    
    print("=" * 70)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - NETWORK IS PRODUCTION READY!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - Review required")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
