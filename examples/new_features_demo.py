"""
Example demonstrating the new features:
- Bloom Filters for efficient anti-entropy
- Distributed Hash Table (DHT)
- Enhanced Metrics System
"""
import asyncio
from positron_networking import Node, NetworkConfig
from positron_networking.bloom_filter import BloomFilter, ScalableBloomFilter
from positron_networking.metrics import get_metrics


async def demonstrate_bloom_filters():
    """Demonstrate Bloom filter usage."""
    print("\n=== Bloom Filter Demo ===")
    
    # Create a Bloom filter
    bloom = BloomFilter(expected_elements=1000, false_positive_rate=0.01)
    
    # Add message IDs
    message_ids = [f"msg_{i}" for i in range(500)]
    for msg_id in message_ids:
        bloom.add(msg_id)
    
    # Check membership
    print(f"'msg_0' in filter: {('msg_0' in bloom)}")
    print(f"'msg_999' in filter: {('msg_999' in bloom)}")
    
    # Get statistics
    stats = bloom.get_stats()
    print(f"\nBloom Filter Stats:")
    print(f"  Elements: {stats['current_elements']}/{stats['expected_elements']}")
    print(f"  Size: {stats['size_bytes']} bytes")
    print(f"  False positive rate: {stats['current_false_positive_rate']:.4f}")
    print(f"  Utilization: {stats['utilization']:.1%}")
    
    # Demonstrate scalable Bloom filter
    print("\n--- Scalable Bloom Filter ---")
    scalable = ScalableBloomFilter(initial_capacity=100)
    
    # Add more items than initial capacity
    for i in range(500):
        scalable.add(f"item_{i}")
    
    scalable_stats = scalable.get_stats()
    print(f"  Number of filters: {scalable_stats['num_filters']}")
    print(f"  Total items: {scalable_stats['total_items']}")
    print(f"  Total size: {scalable_stats['total_size_bytes']} bytes")


async def demonstrate_dht():
    """Demonstrate DHT usage."""
    print("\n=== Distributed Hash Table Demo ===")
    
    # Create a node with DHT
    config = NetworkConfig(
        host="127.0.0.1",
        port=9000,
        bootstrap_nodes=[]
    )
    
    node = Node(config)
    await node.start()
    
    try:
        # Store values in DHT
        print("\nStoring values in DHT...")
        await node.dht_store("user:1001", {"name": "Alice", "score": 100}, ttl=3600)
        await node.dht_store("user:1002", {"name": "Bob", "score": 95}, ttl=3600)
        await node.dht_store("config:app", {"version": "1.0", "debug": True})
        
        # Retrieve values
        print("\nRetrieving values from DHT...")
        user1 = await node.dht_retrieve("user:1001")
        print(f"  user:1001 = {user1}")
        
        user2 = await node.dht_retrieve("user:1002")
        print(f"  user:1002 = {user2}")
        
        config = await node.dht_retrieve("config:app")
        print(f"  config:app = {config}")
        
        # Get DHT statistics
        dht_stats = node.dht_get_stats()
        print(f"\nDHT Statistics:")
        print(f"  Stored keys: {dht_stats['stored_keys']}")
        print(f"  Total operations: {dht_stats['stores']} stores, {dht_stats['retrievals']} retrievals")
        
        # Delete a value
        print("\nDeleting user:1002...")
        await node.dht_delete("user:1002")
        
        # Verify deletion
        deleted_user = await node.dht_retrieve("user:1002")
        print(f"  user:1002 after deletion: {deleted_user}")
        
    finally:
        await node.stop()


async def demonstrate_metrics():
    """Demonstrate enhanced metrics system."""
    print("\n=== Enhanced Metrics Demo ===")
    
    # Get global metrics instance
    metrics = get_metrics()
    
    # Simulate network activity
    print("\nSimulating network activity...")
    
    # Counters
    for i in range(50):
        metrics.increment_counter("messages.sent.total")
    
    for i in range(45):
        metrics.increment_counter("messages.received.total")
    
    metrics.increment_counter("messages.dropped.total", 5)
    
    # Gauges
    metrics.set_gauge("connections.active", 12)
    metrics.set_gauge("peers.active", 8)
    metrics.set_gauge("dht.keys.stored", 3)
    
    # Histograms
    import random
    for _ in range(100):
        metrics.observe_histogram("message.size.bytes", random.randint(100, 5000))
        metrics.observe_histogram("message.latency.seconds", random.uniform(0.001, 0.1))
    
    # Timer context manager
    print("\nTiming an operation...")
    with metrics.timer("operation.duration.seconds"):
        await asyncio.sleep(0.05)
    
    # Get summary
    summary = metrics.get_summary()
    print(f"\nMetrics Summary:")
    print(f"  Messages sent: {summary['messages']['sent']}")
    print(f"  Messages received: {summary['messages']['received']}")
    print(f"  Messages dropped: {summary['messages']['dropped']}")
    print(f"  Active connections: {summary['connections']['active']}")
    print(f"  Active peers: {summary['peers']['active']}")
    print(f"  DHT keys stored: {summary['dht']['keys_stored']}")
    
    # Get histogram statistics
    latency_hist = metrics.histogram("message.latency.seconds")
    latency_summary = latency_hist.get_summary()
    
    print(f"\nMessage Latency Distribution:")
    print(f"  Count: {latency_summary.count}")
    print(f"  Mean: {latency_summary.mean:.4f}s")
    print(f"  Min: {latency_summary.min:.4f}s")
    print(f"  Max: {latency_summary.max:.4f}s")
    print(f"  P50: {latency_hist.get_percentile(0.5):.4f}s")
    print(f"  P95: {latency_hist.get_percentile(0.95):.4f}s")
    print(f"  P99: {latency_hist.get_percentile(0.99):.4f}s")
    
    # Export to Prometheus format
    print("\n--- Prometheus Export (first 20 lines) ---")
    prometheus_output = metrics.export_prometheus()
    lines = prometheus_output.split('\n')[:20]
    for line in lines:
        print(line)


async def main():
    """Run all demonstrations."""
    print("\n" + "="*60)
    print("   Positron Networking - New Features Demonstration")
    print("="*60)
    
    await demonstrate_bloom_filters()
    await demonstrate_dht()
    await demonstrate_metrics()
    
    print("\n" + "="*60)
    print("   Demo Complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
