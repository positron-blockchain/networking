# Transport Layer Integration Guide

This guide explains how to integrate the new packet-based transport layer with the existing high-level networking components (Node, Gossip, Peers).

## Current State

### What's Complete
- ✅ Transport layer fully implemented (packet.py, connection.py, udp_transport.py, tcp_transport.py, flow_control.py)
- ✅ Comprehensive test suite
- ✅ Documentation (README.md, TRANSPORT.md)
- ✅ Working examples

### What Needs Integration
- ⏳ Node class (node.py) - Update to use new transports
- ⏳ Gossip protocol (gossip.py) - Use packet-based messaging
- ⏳ Peer manager (peers.py) - Use new connection management
- ⏳ Network layer (network.py) - Deprecate or update

## Integration Steps

### Step 1: Update Node Class

The `Node` class currently uses the old `network.py` transport. Update it to use the new packet-based transports.

#### Changes Needed in `node.py`:

```python
# OLD
from .network import Network

class Node:
    def __init__(self, config: NetworkConfig):
        self.network = Network(
            host=config.host,
            port=config.port,
            # ...
        )

# NEW
from .transport import UDPTransport, TCPTransport

class Node:
    def __init__(self, config: NetworkConfig):
        # Use UDP for fast gossip messages
        self.udp_transport = UDPTransport(
            host=config.host,
            port=config.port
        )
        
        # Use TCP for reliable data transfer
        self.tcp_transport = TCPTransport(
            host=config.host,
            port=config.port + 1  # Different port
        )
        
        # Register handlers
        self.udp_transport.register_handler(self._on_udp_packet)
        self.tcp_transport.register_handler(self._on_tcp_packet)
    
    async def start(self):
        """Start both transports."""
        await self.udp_transport.start()
        await self.tcp_transport.start()
        # ... rest of start logic
    
    async def _on_udp_packet(self, packet, peer_addr):
        """Handle incoming UDP packet."""
        # Deserialize application message from packet payload
        try:
            message = msgpack.unpackb(packet.payload)
            await self._handle_message(message, peer_addr)
        except Exception as e:
            self.logger.error(f"Error handling UDP packet: {e}")
    
    async def _on_tcp_packet(self, packet, peer_addr):
        """Handle incoming TCP packet."""
        try:
            message = msgpack.unpackb(packet.payload)
            await self._handle_message(message, peer_addr)
        except Exception as e:
            self.logger.error(f"Error handling TCP packet: {e}")
```

### Step 2: Update Gossip Protocol

Update `gossip.py` to use the new transport layer for message propagation.

#### Changes Needed in `gossip.py`:

```python
# OLD
async def propagate(self, message: dict, exclude: Set[str] = None):
    """Propagate message via gossip."""
    # Select peers
    peers = self._select_gossip_targets(exclude)
    
    # Send to each peer
    for peer in peers:
        await self.network.send(peer.address, message)

# NEW
async def propagate(self, message: dict, exclude: Set[str] = None):
    """Propagate message via gossip."""
    # Serialize message
    payload = msgpack.packb(message)
    
    # Select peers
    peers = self._select_gossip_targets(exclude)
    
    # Send to each peer using UDP reliable mode
    for peer in peers:
        try:
            await self.transport.send_reliable(
                peer_addr=peer.address,
                data=payload,
                timeout=2.0  # Short timeout for gossip
            )
        except asyncio.TimeoutError:
            # Peer didn't ACK - may be down
            self.logger.warning(f"Gossip to {peer.address} timed out")
            # Update peer status, trigger failure handling, etc.
```

### Step 3: Update Peer Management

Update `peers.py` to use the new connection management from the transport layer.

#### Changes Needed in `peers.py`:

```python
# Import connection state
from .transport import ConnectionState

class PeerManager:
    def __init__(self, transport):
        self.transport = transport
        # ... existing init
    
    async def connect_to_peer(self, peer_addr: Tuple[str, int]):
        """Establish connection to peer."""
        # Connection is handled automatically by transport
        # Just send a handshake message
        handshake = self._create_handshake_message()
        
        try:
            await self.transport.send_reliable(
                peer_addr=peer_addr,
                data=msgpack.packb(handshake),
                timeout=5.0
            )
            
            # Add peer to active peers
            self.active_peers[peer_addr] = {
                'connected_at': time.time(),
                'last_seen': time.time(),
                # ...
            }
            
        except Exception as e:
            self.logger.error(f"Failed to connect to {peer_addr}: {e}")
    
    def get_connection_stats(self, peer_addr: Tuple[str, int]) -> dict:
        """Get transport-level connection statistics."""
        # Access connection from transport
        conn = self.transport.connections.get(peer_addr)
        if conn:
            return {
                'state': conn.state.name,
                'rtt': conn.srtt,
                'rto': conn.rto,
                'packets_sent': len(conn.sent_packets),
                # ...
            }
        return {}
```

### Step 4: Choose Transport for Each Use Case

Different message types should use different transports based on their requirements:

#### Gossip Messages → UDP Reliable
- Fast propagation needed
- Can tolerate some loss
- Short timeout acceptable

```python
await udp_transport.send_reliable(
    peer_addr=peer,
    data=gossip_message,
    timeout=2.0
)
```

#### Heartbeats → UDP Unreliable
- Very fast, fire-and-forget
- Loss is acceptable (next heartbeat coming soon)
- Minimal overhead

```python
await udp_transport.send_unreliable(
    peer_addr=peer,
    data=heartbeat_message
)
```

#### Trust Updates → TCP
- Must be reliable
- Order matters
- Can tolerate slightly higher latency

```python
await tcp_transport.send(
    peer_addr=peer,
    data=trust_update
)
```

#### Trusted Peer Lists → TCP
- Must be reliable
- Can be large (fragmentation needed)
- Order matters

```python
await tcp_transport.send(
    peer_addr=peer,
    data=trusted_peers_list
)
```

### Step 5: Message Format Adaptation

The transport layer works with raw bytes (packets), while the application protocol uses structured messages. Here's how to adapt:

#### Application Message Wrapper

```python
import msgpack
from typing import Dict, Any

class MessageAdapter:
    """Adapts between application messages and transport packets."""
    
    @staticmethod
    def serialize(msg_type: int, payload: Dict[Any, Any], 
                  sender_id: str, signature: bytes) -> bytes:
        """Serialize application message for transport."""
        message = {
            'msg_type': msg_type,
            'sender_id': sender_id,
            'timestamp': time.time(),
            'payload': payload,
            'signature': signature,
        }
        return msgpack.packb(message)
    
    @staticmethod
    def deserialize(data: bytes) -> Dict[Any, Any]:
        """Deserialize application message from transport."""
        return msgpack.unpackb(data)
```

#### Usage in Node

```python
class Node:
    async def broadcast(self, data: dict):
        """Broadcast data to network."""
        # Create application-level message
        message = {
            'msg_type': MessageType.CUSTOM_DATA,
            'sender_id': self.identity.node_id,
            'timestamp': time.time(),
            'payload': data,
        }
        
        # Sign message
        message_bytes = msgpack.packb(message)
        message['signature'] = self.identity.sign(message_bytes)
        
        # Serialize for transport
        transport_data = MessageAdapter.serialize(
            msg_type=message['msg_type'],
            payload=message['payload'],
            sender_id=message['sender_id'],
            signature=message['signature']
        )
        
        # Send via gossip using UDP reliable
        await self.gossip.propagate(transport_data)
    
    async def _handle_packet(self, packet, peer_addr):
        """Handle incoming packet from transport."""
        # Deserialize application message
        message = MessageAdapter.deserialize(packet.payload)
        
        # Verify signature
        if not self._verify_message(message):
            self.logger.warning(f"Invalid signature from {peer_addr}")
            return
        
        # Route to appropriate handler
        msg_type = message['msg_type']
        if msg_type == MessageType.GOSSIP_MESSAGE:
            await self.gossip.handle_message(message, peer_addr)
        elif msg_type == MessageType.TRUST_UPDATE:
            await self.trust_manager.handle_update(message, peer_addr)
        # ... other handlers
```

### Step 6: Update Configuration

Add transport-specific configuration options:

```python
# In config.py
@dataclass
class NetworkConfig:
    # Existing options
    host: str = "0.0.0.0"
    port: int = 8888
    
    # NEW: Transport options
    tcp_port: int = 8889  # Separate TCP port
    mtu: int = 1400  # Maximum transmission unit
    enable_udp: bool = True
    enable_tcp: bool = True
    
    # NEW: Flow control options
    initial_window: int = 65535
    max_connections: int = 1000
    
    # NEW: Congestion control options
    mss: int = 1400  # Maximum segment size
    
    # NEW: Retransmission options
    min_rto: float = 1.0  # Minimum RTO in seconds
    max_rto: float = 60.0  # Maximum RTO in seconds
    max_retries: int = 5
```

### Step 7: Error Handling

Add proper error handling for transport-level issues:

```python
class Node:
    async def send_message(self, peer_addr, message, reliable=True):
        """Send message with proper error handling."""
        try:
            if reliable:
                await self.udp_transport.send_reliable(
                    peer_addr=peer_addr,
                    data=message,
                    timeout=5.0
                )
            else:
                await self.udp_transport.send_unreliable(
                    peer_addr=peer_addr,
                    data=message
                )
        
        except asyncio.TimeoutError:
            # Peer didn't ACK in time
            self.logger.warning(f"Send to {peer_addr} timed out")
            await self.peer_manager.mark_peer_slow(peer_addr)
        
        except ConnectionError:
            # Connection failed
            self.logger.error(f"Connection to {peer_addr} failed")
            await self.peer_manager.mark_peer_down(peer_addr)
        
        except Exception as e:
            # Unknown error
            self.logger.error(f"Error sending to {peer_addr}: {e}")
```

### Step 8: Statistics and Monitoring

Integrate transport statistics into node monitoring:

```python
class Node:
    def get_stats(self) -> dict:
        """Get comprehensive node statistics."""
        stats = {
            # Existing stats
            'node_id': self.identity.node_id,
            'active_peers': len(self.peer_manager.active_peers),
            
            # NEW: Transport stats
            'transport': {
                'udp': self.udp_transport.get_stats(),
                'tcp': self.tcp_transport.get_stats(),
            },
            
            # NEW: Connection stats
            'connections': {
                peer_addr: self._get_connection_stats(peer_addr)
                for peer_addr in self.peer_manager.active_peers
            },
            
            # Existing stats
            'gossip_stats': self.gossip.get_stats(),
            'trust_stats': self.trust_manager.get_stats(),
        }
        
        return stats
    
    def _get_connection_stats(self, peer_addr):
        """Get stats for specific peer connection."""
        conn = self.udp_transport.connections.get(peer_addr)
        if conn:
            return {
                'state': conn.state.name,
                'rtt': conn.srtt,
                'rto': conn.rto,
                'retransmissions': conn.retransmissions,
            }
        return None
```

## Testing Integration

### Unit Tests

Update existing tests to use new transport:

```python
# In test_node.py
@pytest.mark.asyncio
async def test_node_broadcast():
    """Test node broadcast with new transport."""
    config = NetworkConfig(host="0.0.0.0", port=9000)
    node = Node(config)
    
    await node.start()
    
    # Broadcast message
    await node.broadcast({'test': 'data'})
    
    # Verify transport was used
    assert len(node.udp_transport.connections) > 0
    
    await node.stop()
```

### Integration Tests

Create new integration tests:

```python
# In test_transport_integration.py
@pytest.mark.asyncio
async def test_peer_communication():
    """Test peer-to-peer communication with new transport."""
    # Create two nodes
    node1 = Node(NetworkConfig(host="0.0.0.0", port=9000))
    node2 = Node(NetworkConfig(host="0.0.0.0", port=9001))
    
    await node1.start()
    await node2.start()
    
    # Node1 connects to node2
    await node1.peer_manager.connect_to_peer(("127.0.0.1", 9001))
    
    # Wait for handshake
    await asyncio.sleep(0.5)
    
    # Verify connection established
    assert ("127.0.0.1", 9001) in node1.peer_manager.active_peers
    
    # Send message
    await node1.send_message(
        peer_addr=("127.0.0.1", 9001),
        message=b"Hello, peer!",
        reliable=True
    )
    
    # Cleanup
    await node1.stop()
    await node2.stop()
```

## Migration Checklist

- [ ] Update Node class to use new transports
- [ ] Update Gossip protocol to use packet-based messaging
- [ ] Update Peer manager to use new connection management
- [ ] Add MessageAdapter for serialization
- [ ] Update configuration with transport options
- [ ] Add error handling for transport errors
- [ ] Integrate transport statistics
- [ ] Update CLI to show transport stats
- [ ] Update all unit tests
- [ ] Add integration tests
- [ ] Update documentation
- [ ] Performance testing
- [ ] Deprecate old network.py

## Backward Compatibility

If backward compatibility is needed during migration:

```python
class Node:
    def __init__(self, config: NetworkConfig):
        # Support both old and new transport
        if config.use_new_transport:
            self.transport = UDPTransport(config.host, config.port)
        else:
            self.transport = Network(config.host, config.port)
        
        # Common interface
        self.send = self.transport.send
```

## Performance Considerations

1. **Use UDP unreliable for heartbeats** - Minimal overhead
2. **Use UDP reliable for gossip** - Balance of speed and reliability
3. **Use TCP for critical data** - Maximum reliability
4. **Tune MTU** - Match network characteristics
5. **Adjust window sizes** - Based on bandwidth-delay product
6. **Monitor RTT** - Detect network issues early
7. **Track retransmissions** - Identify problematic peers

## Common Issues and Solutions

### Issue: Too many retransmissions
**Solution**: Increase RTO or reduce network load

### Issue: High memory usage
**Solution**: Reduce max_connections or connection timeout

### Issue: Messages not being delivered
**Solution**: Check firewall rules, verify peer addresses, enable debug logging

### Issue: High latency
**Solution**: Use UDP unreliable for time-sensitive data, reduce gossip fanout

## Next Steps

1. Start with Node class integration
2. Test with two nodes locally
3. Gradually migrate gossip and peer management
4. Add integration tests
5. Performance testing
6. Deploy to test network
7. Monitor and tune

## Support

For questions or issues during integration:
- See TRANSPORT.md for detailed transport documentation
- Check examples/transport_example.py for usage examples
- Review tests/test_transport.py for test examples
- Open an issue at https://github.com/positron-blockchain/networking

---

Part of the [Positron Blockchain](https://github.com/positron-blockchain) ecosystem.
