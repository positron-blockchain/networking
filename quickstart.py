#!/usr/bin/env python3
"""
Quick start script for testing the Positron Networking locally.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent / "src"))

from positron_networking import Node, NetworkConfig


async def run_demo_network():
    """Run a demo network with 3 nodes."""
    
    print("=" * 60)
    print("Positron Networking - Quick Start Demo")
    print("=" * 60)
    print("\nStarting 3 nodes locally...")
    print()
    
    nodes = []
    
    try:
        # Create bootstrap node
        print("[1/3] Creating bootstrap node on port 8888...")
        config1 = NetworkConfig(
            host="127.0.0.1",
            port=8888,
            data_dir="demo_data/node1",
            db_path="demo_data/node1/network.db",
            private_key_path="demo_data/node1/keys/private_key.pem",
            public_key_path="demo_data/node1/keys/public_key.pem",
            log_level="WARNING"
        )
        node1 = Node(config1)
        await node1.start()
        nodes.append(node1)
        print(f"✓ Node 1 started - ID: {node1.node_id}")
        
        await asyncio.sleep(1)
        
        # Create node 2
        print("\n[2/3] Creating node 2 on port 8889...")
        config2 = NetworkConfig(
            host="127.0.0.1",
            port=8889,
            bootstrap_nodes=["127.0.0.1:8888"],
            data_dir="demo_data/node2",
            db_path="demo_data/node2/network.db",
            private_key_path="demo_data/node2/keys/private_key.pem",
            public_key_path="demo_data/node2/keys/public_key.pem",
            log_level="WARNING"
        )
        node2 = Node(config2)
        await node2.start()
        nodes.append(node2)
        print(f"✓ Node 2 started - ID: {node2.node_id}")
        
        await asyncio.sleep(1)
        
        # Create node 3
        print("\n[3/3] Creating node 3 on port 8890...")
        config3 = NetworkConfig(
            host="127.0.0.1",
            port=8890,
            bootstrap_nodes=["127.0.0.1:8888"],
            data_dir="demo_data/node3",
            db_path="demo_data/node3/network.db",
            private_key_path="demo_data/node3/keys/private_key.pem",
            public_key_path="demo_data/node3/keys/public_key.pem",
            log_level="WARNING"
        )
        node3 = Node(config3)
        await node3.start()
        nodes.append(node3)
        print(f"✓ Node 3 started - ID: {node3.node_id}")
        
        # Wait for connections
        print("\n⏳ Waiting for network to stabilize...")
        await asyncio.sleep(3)
        
        # Display network status
        print("\n" + "=" * 60)
        print("Network Status:")
        print("=" * 60)
        
        for i, node in enumerate(nodes, 1):
            stats = node.get_stats()
            print(f"\nNode {i} ({node.node_id[:8]}):")
            print(f"  Address: {stats['address']}")
            print(f"  Active Peers: {stats['active_peers']}")
            print(f"  Known Peers: {stats['known_peers']}")
            print(f"  Connections: {stats['connections']}")
        
        # Demo message broadcasting
        print("\n" + "=" * 60)
        print("Testing Message Broadcasting:")
        print("=" * 60)
        
        # Set up message handler
        received_messages = []
        
        async def message_handler(sender_id, data):
            received_messages.append((sender_id, data))
            print(f"✓ Node received message from {sender_id[:8]}: {data.get('text', '')}")
        
        for node in nodes:
            node.register_data_handler("demo", message_handler)
        
        # Broadcast from node 2
        print(f"\nNode 2 broadcasting message...")
        await node2.broadcast({"text": "Hello from Node 2!", "type": "demo"})
        
        # Wait for propagation
        await asyncio.sleep(2)
        
        print(f"\n✓ Message propagation complete! Received {len(received_messages)} times")
        
        # Keep running
        print("\n" + "=" * 60)
        print("Network is running! Press Ctrl+C to stop...")
        print("=" * 60)
        print("\nYou can now:")
        print("  - Open another terminal and connect more nodes")
        print("  - Use the API to send/receive messages")
        print("  - Monitor network statistics")
        print()
        
        while True:
            await asyncio.sleep(5)
            
            # Periodic status update
            total_active_peers = sum(n.get_stats()['active_peers'] for n in nodes)
            total_messages = sum(n.gossip.stats['messages_received'] for n in nodes)
            
            print(f"\r⚡ Network: {len(nodes)} nodes | "
                  f"{total_active_peers} total peer connections | "
                  f"{total_messages} messages processed", end="", flush=True)
        
    except KeyboardInterrupt:
        print("\n\n⏹ Stopping network...")
    finally:
        # Clean up
        for i, node in enumerate(nodes, 1):
            print(f"  Stopping node {i}...")
            await node.stop()
        
        print("\n✓ All nodes stopped")
        print("=" * 60)


if __name__ == "__main__":
    print("\n🚀 Starting Quick Demo...\n")
    
    try:
        asyncio.run(run_demo_network())
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n👋 Demo completed!\n")
