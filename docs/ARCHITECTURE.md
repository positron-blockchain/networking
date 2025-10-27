# Architecture Documentation

## System Overview

The decentralized network is built on a modular architecture with clear separation of concerns. Each component is designed to be independent, testable, and extensible.

## Core Components

### 1. Identity Module (`identity.py`)

**Purpose**: Cryptographic identity management using Ed25519 signatures.

**Key Features**:
- Generate Ed25519 key pairs
- Sign and verify messages
- Persist and load keys from disk
- Derive unique node IDs from public keys

**Security Model**:
- Private keys stored with 0600 permissions
- Node IDs are deterministic (SHA256 of public key)
- All messages must be signed

### 2. Protocol Module (`protocol.py`)

**Purpose**: Define message formats and serialization.

**Message Types**:
1. **Connection Management**: HANDSHAKE, HANDSHAKE_ACK, DISCONNECT
2. **Peer Discovery**: PEER_DISCOVERY, PEER_ANNOUNCEMENT
3. **Network Health**: HEARTBEAT
4. **Data Propagation**: GOSSIP_MESSAGE, CUSTOM_DATA
5. **Trust Management**: TRUST_UPDATE, TRUSTED_PEERS_REQUEST/RESPONSE

**Serialization**:
- Uses MessagePack for efficient binary serialization
- All messages include signature, timestamp, and TTL
- Message IDs generated from content hash

### 3. Storage Module (`storage.py`)

**Purpose**: Persistent state management using SQLite.

**Schema**:
```sql
peers: node_id, address, public_key, last_seen, trust_score
messages_seen: message_id, timestamp, sender_id
trust_events: node_id, event_type, trust_delta, timestamp
network_state: key, value, updated_at
```

**Performance**:
- Indexed queries for fast lookups
- Async operations with aiosqlite
- Automatic cleanup of old records

### 4. Trust Module (`trust.py`)

**Purpose**: Reputation and trust management.

**Trust Dynamics**:
```
Initial Trust: 0.5 (configurable)
Valid Message: +0.001
Invalid Message: -0.1
Timeout: -0.05
Decay Rate: -0.01 per interval (towards initial)
```

**Transitive Trust**:
```
boost = recommended_trust × recommender_trust × 0.1
```

**Reputation Score**:
```
reputation = trust × 0.6 + trend × 0.2 + stats × 0.2
```

### 5. Peer Management Module (`peers.py`)

**Purpose**: Manage peer connections and discovery.

**Peer States**:
- **Known**: Discovered but not connected
- **Connecting**: Connection attempt in progress
- **Active**: Fully connected and operational

**Discovery Strategy**:
1. Bootstrap from configured nodes
2. Receive peer announcements
3. Request peers from connected nodes
4. Periodic background discovery

**Eviction Policy**:
- Maintain min/max peer counts
- Evict lowest trust peers when at capacity
- Remove peers after timeout

### 6. Gossip Module (`gossip.py`)

**Purpose**: Epidemic message propagation.

**Algorithm**:
```
1. Receive message
2. Check if seen before (deduplication)
3. Verify signature and trust
4. Process message locally
5. Add to propagation queue
6. Periodically gossip to random subset (fanout)
7. Decrement TTL on each hop
```

**Optimizations**:
- Message cache for fast deduplication
- Batch processing of pending messages
- Configurable fanout and interval
- TTL to prevent infinite propagation

### 7. Network Module (`network.py`)

**Purpose**: Low-level networking and connection management.

**Connection Protocol**:
```
1. TCP connection established
2. Send HANDSHAKE with public key
3. Receive HANDSHAKE_ACK
4. Verify signatures
5. Store connection
6. Begin message exchange
```

**Message Framing**:
```
[4 bytes length prefix][message data]
```

**Concurrency**:
- Async I/O with asyncio
- Connection semaphore for limiting
- Per-connection locks for thread safety

### 8. Node Module (`node.py`)

**Purpose**: Main orchestrator bringing all components together.

**Lifecycle**:
```
1. Load/generate identity
2. Initialize storage
3. Start trust manager
4. Start peer manager
5. Start gossip protocol
6. Start network transport
7. Connect to bootstrap nodes
8. Begin background tasks (heartbeat, discovery)
```

**Message Flow**:
```
Network → Gossip → Handler → Application
         ↓
    Trust Update
         ↓
    Peer Manager
```

## Data Flow

### Outgoing Message
```
Application
    ↓
Node.broadcast()
    ↓
GossipProtocol.broadcast()
    ↓
[Add to pending queue]
    ↓
Gossip Loop (periodic)
    ↓
Select random peers (fanout)
    ↓
NetworkTransport.send_to_peer()
    ↓
Sign message
    ↓
TCP connection
```

### Incoming Message
```
TCP connection
    ↓
NetworkTransport.receive_message()
    ↓
GossipProtocol.receive_message()
    ↓
Deduplication check
    ↓
Trust verification
    ↓
Message handler (by type)
    ↓
Update peer activity
    ↓
Add to propagation queue (if needed)
```

## Trust Propagation

### Direct Trust
```
Peer A → [Valid Message] → Node
Node updates trust(A) = trust(A) + 0.001
```

### Transitive Trust
```
Peer A → [Recommends B with trust 0.8] → Node
Node updates trust(B) = trust(B) + (0.8 × trust(A) × 0.1)
```

### Trust Decay
```
Every decay_interval:
    current_trust → current_trust + (initial_trust - current_trust) × decay_rate
```

## Peer Discovery

### Bootstrap Phase
```
1. Node starts
2. Connect to configured bootstrap nodes
3. Receive initial peer list via HANDSHAKE_ACK
4. Store peers in known_peers
```

### Ongoing Discovery
```
1. Periodically check if peers < min_peers
2. Send PEER_DISCOVERY to random connected peers
3. Receive PEER_ANNOUNCEMENT with peer list
4. Evaluate trust scores
5. Attempt connections to high-trust peers
```

### Peer Selection
```
Criteria for connection:
1. Trust score above threshold
2. Not already connected
3. Active within timeout period
4. Space available (< max_peers)
```

## Security Architecture

### Attack Mitigation

**Sybil Attack**:
- Trust scores limit impact
- New peers start with low trust
- Trust decay prevents accumulation

**Eclipse Attack**:
- Multiple bootstrap nodes
- Continuous peer discovery
- Trust-based routing

**Message Flooding**:
- Message deduplication
- TTL limits
- Connection limits
- Trust penalties for spam

**Byzantine Nodes**:
- Signature verification
- Trust penalties for invalid messages
- Automatic disconnection of low-trust peers

### Trust Model Properties

**Eventual Consistency**:
- Trust converges to actual behavior
- Transitive trust spreads recommendations
- Decay prevents stale trust

**Sybil Resistance**:
- New identities have low trust
- Must earn trust through valid behavior
- Cost increases with network size

**Byzantine Tolerance**:
- Invalid messages decrease trust
- Multiple strikes lead to disconnection
- Network remains functional with <33% malicious nodes

## Performance Characteristics

### Scalability
- **Peers**: O(1) per peer overhead
- **Messages**: O(log n) propagation hops
- **Storage**: O(peers + messages) space
- **Trust**: O(peers) computation

### Latency
- **Message Propagation**: gossip_interval × hops
- **Peer Discovery**: discovery_interval
- **Trust Update**: Immediate with async persistence

### Throughput
- **Limited by**: fanout × gossip_interval
- **Typical**: 100-1000 messages/second per node
- **Optimizations**: Batching, caching, async I/O

## Configuration Tuning

### For High Throughput
```python
config = NetworkConfig(
    gossip_fanout=5,        # More propagation
    gossip_interval=0.5,    # Faster rounds
    max_peers=100,          # More connections
)
```

### For Low Resource Usage
```python
config = NetworkConfig(
    gossip_fanout=2,        # Less propagation
    gossip_interval=2.0,    # Slower rounds
    max_peers=20,           # Fewer connections
    message_cache_size=1000 # Smaller cache
)
```

### For High Security
```python
config = NetworkConfig(
    initial_trust_score=0.3,    # Lower initial trust
    min_trust_threshold=0.5,    # Higher threshold
    trust_decay_rate=0.02,      # Faster decay
)
```

## Extension Points

### Custom Message Handlers
```python
async def my_handler(message, sender_address):
    # Process custom message type
    pass

gossip.register_handler(CUSTOM_TYPE, my_handler)
```

### Custom Trust Metrics
```python
class CustomTrustManager(TrustManager):
    async def compute_trust(self, node_id):
        # Custom trust calculation
        pass
```

### Storage Backends
```python
class CustomStorage(Storage):
    async def save_peer(self, peer):
        # Custom persistence
        pass
```

## Future Enhancements

### Planned Features
1. **DHT**: Distributed hash table for key-value storage
2. **NAT Traversal**: STUN/TURN for NAT penetration
3. **Bloom Filters**: More efficient anti-entropy
4. **Vector Clocks**: Better consistency guarantees
5. **Rust Extensions**: Performance-critical paths in Rust

### Research Directions
1. **Consensus**: Add Byzantine consensus for critical decisions
2. **Sharding**: Partition network for scalability
3. **Privacy**: Anonymous communication layers
4. **Incentives**: Token-based participation incentives
