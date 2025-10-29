# Positron Blockchain - Networking Layer

A production-ready decentralized peer-to-peer network implementation in Python with packet-based transport, cryptographic identity, gossip protocol, trust management, and secure communication.

**Part of the [Positron Blockchain](https://github.com/positron-blockchain) ecosystem.**

## Features

### 🔐 Cryptographic Identity
- **Ed25519 Key Pairs**: Each node has a unique cryptographic identity
- **Message Signing**: All messages are cryptographically signed
- **Peer Authentication**: Verify the authenticity of all network participants
- **Key Persistence**: Secure storage and loading of cryptographic keys

### 🌐 Decentralized Architecture
- **No Central Authority**: Fully peer-to-peer, no single point of failure
- **Bootstrap Nodes**: Initial network discovery through configurable bootstrap nodes
- **Dynamic Peer Discovery**: Continuous discovery of new peers through existing connections
- **Self-Healing**: Automatic recovery from node failures and network partitions

### 💬 Gossip Protocol
- **Epidemic Broadcasting**: Efficient message propagation across the network
- **Configurable Fanout**: Control propagation speed and redundancy
- **Message Deduplication**: Prevent message loops and duplicate processing
- **TTL Management**: Time-to-live for messages prevents infinite propagation
- **Anti-Entropy**: Synchronization mechanisms for consistency

### 🤝 Trust & Reputation System
- **Dynamic Trust Scores**: Track peer reliability and behavior
- **Trust Propagation**: Transitive trust through peer recommendations
- **Automatic Decay**: Trust scores decay over time, requiring continuous good behavior
- **Behavioral Metrics**: Track valid/invalid messages, uptime, and responsiveness
- **Trust-Based Routing**: Prioritize communication with trusted peers

### 📊 Persistent Storage
- **SQLite Backend**: Efficient local storage of network state
- **Peer History**: Track all known peers and their trust scores
- **Message Cache**: Prevent duplicate message processing
- **Trust Events**: Complete audit trail of trust changes
- **State Management**: Persist configuration and network state

### 🚀 Production-Ready Transport Layer
- **Packet-Based Protocol**: Custom binary packet format with 32-byte headers
- **TCP & UDP Support**: Both reliable (TCP) and fast (UDP) transports with optional reliability
- **Fragmentation & Reassembly**: Automatic handling of large messages exceeding MTU
- **Flow Control**: Sliding window flow control prevents receiver overload
- **Congestion Control**: TCP-like congestion control with slow start, AIMD, fast retransmit/recovery
- **Connection State Machine**: Full TCP-like connection lifecycle management
- **CRC32 Checksums**: Packet integrity verification
- **RTT Estimation**: Jacobson/Karels algorithm for adaptive timeout calculation
- **Retransmission**: Automatic retransmission of lost packets with exponential backoff

### 🚀 High-Performance Networking
- **Async I/O**: Built on asyncio for concurrent connections
- **Connection Pooling**: Efficient management of peer connections
- **Message Queuing**: Buffer and batch messages for efficiency
- **Configurable Limits**: Control resource usage and performance
- **Timeout Management**: Handle network failures gracefully

### 🎯 Advanced Features ✨ NEW
- **Bloom Filters**: Space-efficient probabilistic data structures for message deduplication with configurable false positive rates
- **Distributed Hash Table (DHT)**: Kademlia-inspired distributed key-value storage with automatic replication and fault tolerance
- **Enhanced Metrics**: Comprehensive monitoring with counters, gauges, histograms, and Prometheus export support
- **NAT Traversal**: STUN-based NAT discovery and UDP hole punching for peer-to-peer connectivity through NATs and firewalls

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Node Application                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Identity   │  │    Config    │  │   Storage    │      │
│  │  Management  │  │  Management  │  │   (SQLite)   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │    Trust     │  │    Peer      │  │    Gossip    │      │
│  │   Manager    │  │   Manager    │  │   Protocol   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         Transport Layer (Packet-Based)              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │    │
│  │  │ UDP + Rel.  │  │     TCP     │  │    Flow    │ │    │
│  │  │  Transport  │  │  Transport  │  │  Control   │ │    │
│  │  └─────────────┘  └─────────────┘  └────────────┘ │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │  Packets, Fragmentation, Connection State  │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites
- Python 3.8 or higher
- pip

### Install from Source

```bash
# Clone the repository
git clone https://github.com/positron-blockchain/networking.git
cd networking

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

## Quick Start

### Start a Bootstrap Node

```bash
# Start the first node (bootstrap node)
positron-net start --host 0.0.0.0 --port 8888
```

### Connect Additional Nodes

```bash
# Start additional nodes that connect to the bootstrap node
positron-net start --host 0.0.0.0 --port 8889 --bootstrap 192.168.1.100:8888

# Start another node
positron-net start --host 0.0.0.0 --port 8890 --bootstrap 192.168.1.100:8888
```

### Run a Local Simulation

```bash
# Start a local network with 5 nodes
positron-net simulate --count 5 --base-port 8888
```

## Configuration

### Generate a Configuration File

```bash
positron-net generate-config config.json --host 0.0.0.0 --port 8888 --bootstrap 192.168.1.100:8888
```

### Configuration Options

```json
{
  "host": "0.0.0.0",
  "port": 8888,
  "bootstrap_nodes": ["192.168.1.100:8888"],
  "gossip_fanout": 3,
  "gossip_interval": 1.0,
  "message_ttl": 10,
  "max_peers": 50,
  "min_peers": 5,
  "initial_trust_score": 0.5,
  "min_trust_threshold": 0.1,
  "trust_decay_rate": 0.01,
  "data_dir": "node_data",
  "log_level": "INFO"
}
```

### Start with Configuration File

```bash
positron-net start --config config.json
```

## Programming API

### Basic Usage

```python
import asyncio
from positron_networking import Node, NetworkConfig

async def main():
    # Create configuration
    config = NetworkConfig(
        host="0.0.0.0",
        port=8888,
        bootstrap_nodes=["192.168.1.100:8888"]
    )
    
    # Create and start node
    node = Node(config)
    await node.start()
    
    # Broadcast a message
    await node.broadcast({"message": "Hello, network!"})
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await node.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Custom Message Handler

```python
async def handle_custom_data(sender_id: str, data: dict):
    """Handle custom data from the network."""
    print(f"Received from {sender_id}: {data}")

# Register handler
node.register_data_handler("my_handler", handle_custom_data)
```

### Query Network Status

```python
# Get node statistics
stats = node.get_stats()
print(f"Active peers: {stats['active_peers']}")
print(f"Known peers: {stats['known_peers']}")
print(f"Messages received: {stats['gossip_stats']['messages_received']}")

# Get trusted peers
trusted_peers = await node.trust_manager.get_trusted_peers(min_trust=0.7)
for peer in trusted_peers:
    print(f"{peer.node_id}: {peer.trust_score}")
```

### Send Direct Messages

```python
# Send to a specific peer
await node.send_to_peer("target_node_id", {"private": "message"})

# Request trusted peers from a peer
await node.request_trusted_peers("peer_node_id")

# Share your trusted peers with the network
await node.share_trusted_peers()
```

### Use Distributed Hash Table (DHT) ✨ NEW

```python
# Store a value in the DHT
await node.dht_store("my_key", {"data": "value"}, ttl=3600)

# Retrieve a value from the DHT
value = await node.dht_retrieve("my_key")
print(f"Retrieved: {value}")

# Delete a value from the DHT
await node.dht_delete("my_key")

# Get DHT statistics
dht_stats = node.dht_get_stats()
print(f"Stored keys: {dht_stats['stored_keys']}")
print(f"Total nodes in routing table: {dht_stats['total_nodes']}")
```

### Use Bloom Filters ✨ NEW

```python
from positron_networking.bloom_filter import BloomFilter, ScalableBloomFilter

# Create a Bloom filter
bloom = BloomFilter(expected_elements=10000, false_positive_rate=0.01)

# Add items
bloom.add("message_id_1")
bloom.add("message_id_2")

# Check membership
if "message_id_1" in bloom:
    print("Message may have been seen before")

# Get statistics
stats = bloom.get_stats()
print(f"Current false positive rate: {stats['current_false_positive_rate']}")

# Serialize and deserialize
serialized = bloom.serialize()
restored = BloomFilter.deserialize(serialized)

# Use scalable Bloom filter for dynamic growth
scalable_bloom = ScalableBloomFilter(initial_capacity=1000)
for i in range(10000):  # Automatically scales
    scalable_bloom.add(f"item_{i}")
```

### Enhanced Metrics System ✨ NEW

```python
from positron_networking.metrics import get_metrics

# Get the global metrics collector
metrics = get_metrics()

# Increment counters
metrics.increment_counter("messages.sent.total")
metrics.increment_counter("messages.received.total", 5)

# Set gauge values
metrics.set_gauge("connections.active", 10)
metrics.set_gauge("peers.active", 25)

# Record histogram values
metrics.observe_histogram("message.size.bytes", 1024)
metrics.observe_histogram("message.latency.seconds", 0.05)

# Use timer context manager
with metrics.timer("operation.duration.seconds"):
    # Your code here
    await some_operation()

# Get all metrics
all_metrics = metrics.get_all_metrics()
print(all_metrics)

# Get summary
summary = metrics.get_summary()
print(f"Messages sent: {summary['messages']['sent']}")
print(f"Active peers: {summary['peers']['active']}")

# Export in Prometheus format
prometheus_output = metrics.export_prometheus()
print(prometheus_output)
```

### NAT Traversal & Hole Punching ✨ NEW

```python
# Check if node is behind NAT
if node.is_behind_nat():
    print("Node is behind NAT")
    nat_info = node.get_nat_info()
    print(f"NAT Type: {nat_info['nat_type']}")
    print(f"Public Address: {nat_info['public_address']}:{nat_info['public_port']}")

# Get connection candidates for NAT traversal
candidates = await node.get_nat_candidates()
print(f"Available candidates: {len(candidates)}")
for candidate in candidates:
    print(f"  {candidate['type']}: {candidate['ip']}:{candidate['port']} (priority: {candidate['priority']})")

# Request NAT-aware connection to a peer
# This initiates ICE-like candidate exchange
await node.request_peer_connection("peer_node_id")

# The NAT traversal manager automatically:
# 1. Discovers public endpoints using STUN
# 2. Gathers host and server-reflexive candidates
# 3. Exchanges candidates with the peer
# 4. Attempts UDP hole punching
# 5. Maintains NAT bindings with keep-alive packets
```

## Testing

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test Categories

```bash
# Unit tests
pytest tests/test_identity.py tests/test_protocol.py -v

# Integration tests
pytest tests/test_integration.py -v
```

### Run with Coverage

```bash
pytest tests/ --cov=positron_networking --cov-report=html
```

## Network Protocol

### Transport Layer

The networking layer implements a production-ready packet-based transport protocol supporting both TCP and UDP.

#### Packet Structure

Each packet consists of a 32-byte fixed header followed by a variable-length payload:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Magic     |    Version    |     Type      |     Flags     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Sequence Number                        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      Acknowledgment Number                    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           Window Size         |          Checksum             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Payload Length                         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Fragment ID                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|        Fragment Index         |      Fragment Total           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           Reserved                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Payload Data                          |
|                             ...                               |
```

#### Packet Types

- **SYN**: Connection initiation
- **SYN_ACK**: Connection acknowledgment
- **ACK**: Data acknowledgment
- **DATA**: Application data
- **FIN**: Connection termination
- **FIN_ACK**: Termination acknowledgment
- **RST**: Connection reset
- **PING**: Keep-alive
- **PONG**: Keep-alive response
- **FRAGMENT**: Large message fragment
- **FRAGMENT_ACK**: Fragment acknowledgment
- **NACK**: Negative acknowledgment

#### Transport Features

**UDP Transport**:
```python
from positron_networking.transport import UDPTransport

transport = UDPTransport(host="0.0.0.0", port=8888)
await transport.start()

# Fast unreliable send (fire-and-forget)
await transport.send_unreliable(peer_addr, data)

# Reliable send with ACKs and retransmission
await transport.send_reliable(peer_addr, data)
```

**TCP Transport**:
```python
from positron_networking.transport import TCPTransport

transport = TCPTransport(host="0.0.0.0", port=8888)
await transport.start()

# Length-prefixed packet framing over TCP
await transport.send(peer_addr, data)
```

**Flow Control**:
```python
from positron_networking.transport import AdaptiveFlowController

controller = AdaptiveFlowController(mss=1400)

# Check if we can send
if controller.can_send(len(data)):
    await send_data(data)
    controller.on_send(len(data))

# On ACK received
controller.on_ack(len(data), receiver_window=32768, rtt=0.05)

# On timeout
controller.on_timeout()

# Get statistics
stats = controller.get_stats()
```

### Application Protocol

### Message Types

1. **HANDSHAKE**: Initial connection establishment
2. **HANDSHAKE_ACK**: Handshake acknowledgment
3. **HEARTBEAT**: Keep-alive messages
4. **PEER_DISCOVERY**: Request for peer information
5. **PEER_ANNOUNCEMENT**: Share known peers
6. **GOSSIP_MESSAGE**: Broadcast data via gossip
7. **TRUST_UPDATE**: Share trust score updates
8. **TRUSTED_PEERS_REQUEST**: Request trusted peer list
9. **TRUSTED_PEERS_RESPONSE**: Share trusted peer list
10. **CUSTOM_DATA**: Application-specific data

### Message Structure

```python
{
    "msg_type": int,           # Message type identifier
    "sender_id": str,          # Sender's node ID
    "timestamp": float,        # Unix timestamp
    "payload": dict,           # Message-specific data
    "signature": bytes,        # Cryptographic signature
    "message_id": str,         # Unique message identifier
    "ttl": int                 # Time-to-live for propagation
}
```

## Security Considerations

### Cryptographic Security
- **Ed25519 Signatures**: All messages are signed with Ed25519
- **Key Protection**: Private keys stored with restrictive permissions (0600)
- **Signature Verification**: All incoming messages are verified
- **Identity Binding**: Node IDs derived from public keys

### Trust & Reputation
- **Sybil Resistance**: Trust scores make Sybil attacks costly
- **Byzantine Tolerance**: Invalid messages penalize sender's trust
- **Trust Decay**: Prevents accumulation of stale trust
- **Transitive Trust**: Weighted by recommender's trust score

### Network Security
- **Message Validation**: All messages validated before processing
- **Connection Limits**: Configurable limits prevent resource exhaustion
- **Timeout Protection**: Dead connections cleaned up automatically
- **TTL Limits**: Prevent infinite message propagation

## Performance Tuning

### Gossip Protocol
- **fanout**: Higher values increase redundancy but use more bandwidth
- **gossip_interval**: Lower values increase propagation speed but use more CPU
- **message_ttl**: Higher values ensure delivery but increase network load

### Peer Management
- **max_peers**: More peers increase connectivity but use more resources
- **min_peers**: Ensures minimum connectivity for reliability
- **peer_timeout**: Balance between quick failure detection and false positives

### Trust System
- **trust_decay_rate**: Higher values require more active participation
- **min_trust_threshold**: Lower values allow more peers but increase risk
- **initial_trust_score**: Balance between optimistic and pessimistic starts

## Troubleshooting

### Connection Issues
```bash
# Check if port is available
netstat -an | grep 8888

# Test connectivity
nc -zv <host> <port>

# Check firewall rules
sudo ufw status
```

### Debug Logging
```python
config = NetworkConfig(log_level="DEBUG")
```

### Common Issues

1. **Can't connect to bootstrap node**: Verify network connectivity and firewall rules
2. **No peers discovered**: Ensure bootstrap nodes are reachable and operational
3. **High CPU usage**: Reduce gossip_interval or fanout
4. **High memory usage**: Reduce message_cache_size or max_peers

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository at https://github.com/positron-blockchain/networking
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for detailed guidelines.

## License

MIT License - See LICENSE file for details

## Roadmap

- [x] Integration with existing Node/Gossip/Peers modules
- [x] Comprehensive transport layer tests
- [x] **Bloom filters for efficient anti-entropy** ✨ NEW
- [x] **DHT implementation for distributed key-value storage** ✨ NEW
- [x] **Enhanced metrics and monitoring dashboard** ✨ NEW
- [x] **NAT traversal and hole punching** ✨ NEW
- [ ] QUIC transport support
- [ ] Rust extensions for performance-critical paths (C/C++/Cython support)
- [ ] WebRTC support for browser nodes
- [ ] Enhanced Byzantine fault tolerance
- [ ] Network visualization tools

## Related Projects

- [Positron Blockchain](https://github.com/positron-blockchain) - Main blockchain implementation
- More coming soon...

---

**Built with ❤️ by the Positron Blockchain team**

Part of the [Positron Blockchain](https://github.com/positron-blockchain) ecosystem.
