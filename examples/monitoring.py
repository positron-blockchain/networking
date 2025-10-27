"""
Example: Monitoring node statistics and network health.
"""
import asyncio
from positron_networking import Node, NetworkConfig


async def monitor_node(node: Node, interval: float = 5.0):
    """Monitor and display node statistics."""
    while True:
        await asyncio.sleep(interval)
        
        stats = node.get_stats()
        
        print("\n" + "=" * 50)
        print(f"Node ID: {stats['node_id']}")
        print(f"Address: {stats['address']}")
        print(f"Active Peers: {stats['active_peers']}")
        print(f"Known Peers: {stats['known_peers']}")
        print(f"Connections: {stats['connections']}")
        
        gossip_stats = stats['gossip_stats']
        print("\nGossip Statistics:")
        print(f"  Messages Received: {gossip_stats['messages_received']}")
        print(f"  Messages Sent: {gossip_stats['messages_sent']}")
        print(f"  Messages Propagated: {gossip_stats['messages_propagated']}")
        print(f"  Duplicates Rejected: {gossip_stats['duplicates_rejected']}")
        print(f"  Pending Messages: {gossip_stats['pending_messages']}")
        
        # Display trusted peers
        trusted_peers = await node.trust_manager.get_trusted_peers(min_trust=0.7)
        print(f"\nTrusted Peers: {len(trusted_peers)}")
        for peer in trusted_peers[:5]:  # Show top 5
            print(f"  {peer.node_id[:8]}... - Trust: {peer.trust_score:.3f}")
        
        print("=" * 50)


async def main():
    """Run a monitoring node."""
    config = NetworkConfig(
        host="0.0.0.0",
        port=8888,
        bootstrap_nodes=["192.168.1.100:8888"],  # Update with actual bootstrap
        log_level="INFO"
    )
    
    node = Node(config)
    await node.start()
    
    print("Monitoring node started...")
    print("Press Ctrl+C to stop")
    
    try:
        # Start monitoring
        await monitor_node(node, interval=10.0)
    except KeyboardInterrupt:
        print("\nStopping...")
        await node.stop()


if __name__ == "__main__":
    asyncio.run(main())
