# Transport Layer Documentation

## Overview

The Positron Blockchain networking layer implements a production-ready, packet-based transport protocol that provides reliable and unreliable communication over UDP and TCP. The transport layer is designed to be efficient, scalable, and resilient to network failures.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Application Layer                       │
│              (Gossip, Trust, Peer Management)              │
└────────────────────────────────────────────────────────────┘
                           ↕
┌────────────────────────────────────────────────────────────┐
│                      Transport API                         │
│        send_reliable() / send_unreliable() / send()        │
└────────────────────────────────────────────────────────────┘
                           ↕
┌────────────────────────────────────────────────────────────┐
│                  Transport Implementations                 │
│  ┌─────────────────┐           ┌──────────────────┐       │
│  │  UDP Transport  │           │  TCP Transport   │       │
│  │  + Reliability  │           │  + Framing       │       │
│  └─────────────────┘           └──────────────────┘       │
└────────────────────────────────────────────────────────────┘
                           ↕
┌────────────────────────────────────────────────────────────┐
│              Connection State Management                   │
│   (State Machine, Sequence Numbers, RTT Estimation)        │
└────────────────────────────────────────────────────────────┘
                           ↕
┌────────────────────────────────────────────────────────────┐
│                Flow & Congestion Control                   │
│   (Sliding Window, Slow Start, Congestion Avoidance)       │
└────────────────────────────────────────────────────────────┘
                           ↕
┌────────────────────────────────────────────────────────────┐
│           Packet Layer (Fragmentation, Checksums)          │
└────────────────────────────────────────────────────────────┘
                           ↕
┌────────────────────────────────────────────────────────────┐
│                  Network (UDP/TCP Sockets)                 │
└────────────────────────────────────────────────────────────┘
```

## Packet Format

### Header Structure (32 bytes)

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
```

### Field Descriptions

- **Magic (2 bytes)**: Protocol identifier (0xBEEF)
- **Version (1 byte)**: Protocol version (currently 1)
- **Type (1 byte)**: Packet type (SYN, ACK, DATA, etc.)
- **Flags (1 byte)**: Control flags (FIN, RST, compressed, etc.)
- **Sequence Number (4 bytes)**: Packet sequence number
- **Acknowledgment Number (4 bytes)**: ACK for received packets
- **Window Size (2 bytes)**: Receiver's available window
- **Checksum (2 bytes)**: CRC32 checksum (lower 16 bits)
- **Payload Length (4 bytes)**: Length of payload data
- **Fragment ID (4 bytes)**: Unique ID for fragmented messages
- **Fragment Index (2 bytes)**: Index of this fragment
- **Fragment Total (2 bytes)**: Total fragments in message
- **Reserved (4 bytes)**: Reserved for future use

## Packet Types

### Control Packets

#### SYN (0x01)
Initiates a new connection.
```python
# Connection establishment
packet = Packet.create_syn(sequence=1000)
await transport.send_packet(peer_addr, packet)
```

#### SYN_ACK (0x02)
Acknowledges connection request.
```python
packet = Packet.create_syn_ack(
    sequence=2000,
    ack_number=1001
)
```

#### ACK (0x03)
Acknowledges received data.
```python
packet = Packet.create_ack(
    sequence=1001,
    ack_number=2001
)
```

#### FIN (0x04)
Initiates connection termination.
```python
packet = Packet.create_fin(sequence=5000)
```

#### FIN_ACK (0x05)
Acknowledges termination request.

#### RST (0x06)
Forcefully resets connection.

### Data Packets

#### DATA (0x07)
Carries application data.
```python
packet = Packet.create_data(
    sequence=3000,
    ack_number=2500,
    payload=data
)
```

#### FRAGMENT (0x0A)
Fragment of larger message.
```python
# Automatic fragmentation
fragmenter = PacketFragmenter(mtu=1400)
fragments = fragmenter.fragment(large_data)
for fragment in fragments:
    await transport.send_packet(peer_addr, fragment)
```

#### FRAGMENT_ACK (0x0B)
Acknowledges fragment receipt.

### Maintenance Packets

#### PING (0x08)
Keep-alive request.

#### PONG (0x09)
Keep-alive response.

#### NACK (0x0C)
Negative acknowledgment for lost packets.

## Connection State Machine

### States

```
CLOSED → SYN_SENT → ESTABLISHED → FIN_WAIT_1 → FIN_WAIT_2 → CLOSED
            ↓
         SYN_RCVD
```

1. **CLOSED**: No connection exists
2. **SYN_SENT**: SYN sent, waiting for SYN_ACK
3. **SYN_RCVD**: SYN received, SYN_ACK sent
4. **ESTABLISHED**: Connection established, data transfer
5. **FIN_WAIT_1**: FIN sent, waiting for ACK
6. **FIN_WAIT_2**: FIN ACKed, waiting for peer FIN
7. **CLOSING**: Both sides closing simultaneously
8. **CLOSE_WAIT**: Peer initiated close
9. **LAST_ACK**: Final ACK sent, waiting for close
10. **TIME_WAIT**: Waiting before final close

### Example Connection Lifecycle

```python
from positron_networking.transport import Connection, ConnectionState

# Create connection
conn = Connection(peer_addr=("192.168.1.100", 8888))

# Initiate connection
syn_packet = conn.initiate_connection()
await transport.send_packet(conn.peer_addr, syn_packet)

# Connection established
assert conn.state == ConnectionState.SYN_SENT

# Receive SYN_ACK
response = conn.handle_packet(syn_ack_packet)
if response:
    await transport.send_packet(conn.peer_addr, response)

# Now in ESTABLISHED state
assert conn.state == ConnectionState.ESTABLISHED

# Send data
data_packet = conn.create_data_packet(b"Hello, network!")
await transport.send_packet(conn.peer_addr, data_packet)

# Close connection
fin_packet = conn.close()
await transport.send_packet(conn.peer_addr, fin_packet)
```

## Flow Control

The flow control mechanism prevents the sender from overwhelming the receiver.

### Sliding Window Protocol

```python
from positron_networking.transport import FlowController

controller = FlowController(initial_window=65535)

# Check if we can send
if controller.can_send(len(data)):
    await send_data(data)
    controller.on_send(len(data))

# On ACK received
controller.on_ack(
    data_size=len(data),
    receiver_window=32768  # Advertised by receiver
)

# Get available window
available = controller.get_available_window()
```

### Window Management

- **Initial Window**: 65535 bytes
- **Maximum Window**: 65535 bytes
- **Minimum Window**: 1024 bytes
- **Bytes in Flight**: Tracked per connection
- **Receiver Window**: Advertised by receiver in each ACK

## Congestion Control

Implements TCP-like congestion control with AIMD (Additive Increase, Multiplicative Decrease).

### Slow Start

```
cwnd starts at 1 MSS
For each ACK: cwnd += 1 MSS
Continue until cwnd >= ssthresh
```

### Congestion Avoidance

```
For each ACK: cwnd += MSS * (MSS / cwnd)
Linear increase to probe for bandwidth
```

### Fast Retransmit

```
On 3 duplicate ACKs:
  - Retransmit lost packet
  - ssthresh = cwnd / 2
  - cwnd = ssthresh + 3 MSS
  - Enter fast recovery
```

### Fast Recovery

```
For each additional duplicate ACK:
  - cwnd += 1 MSS
On new ACK:
  - cwnd = ssthresh
  - Exit fast recovery
```

### Timeout

```
On retransmission timeout:
  - ssthresh = cwnd / 2
  - cwnd = 1 MSS
  - Enter slow start
```

### Example Usage

```python
from positron_networking.transport import CongestionController

controller = CongestionController(mss=1400)

# Get send window
window = controller.get_send_window()

# On ACK received
controller.on_ack(rtt=0.05)  # 50ms RTT

# On duplicate ACK
controller.on_duplicate_ack(ack_number=5000)

# On timeout
controller.on_timeout()

# Get statistics
stats = controller.get_stats()
print(f"cwnd: {stats['cwnd']}")
print(f"ssthresh: {stats['ssthresh']}")
print(f"losses: {stats['losses']}")
```

## RTT Estimation

Uses Jacobson/Karels algorithm for adaptive timeout calculation.

### Formulas

```
SRTT = (1 - α) * SRTT + α * RTT_sample
RTTVAR = (1 - β) * RTTVAR + β * |SRTT - RTT_sample|
RTO = SRTT + 4 * RTTVAR

where:
  α = 1/8 (smoothing factor)
  β = 1/4 (variance factor)
```

### Implementation

```python
# In Connection class
def update_rtt(self, rtt_sample: float):
    """Update RTT estimate using Jacobson/Karels algorithm."""
    if self.srtt is None:
        # First RTT sample
        self.srtt = rtt_sample
        self.rttvar = rtt_sample / 2
    else:
        # Subsequent samples
        alpha = 0.125
        beta = 0.25
        self.rttvar = (1 - beta) * self.rttvar + \
                      beta * abs(self.srtt - rtt_sample)
        self.srtt = (1 - alpha) * self.srtt + alpha * rtt_sample
    
    # Calculate RTO with bounds
    self.rto = self.srtt + 4 * self.rttvar
    self.rto = max(self.min_rto, min(self.max_rto, self.rto))
```

## Fragmentation

Large messages are automatically fragmented to fit within MTU constraints.

### Example

```python
from positron_networking.transport import PacketFragmenter

fragmenter = PacketFragmenter(mtu=1400)

# Fragment large message
large_data = b"x" * 10000
fragments = fragmenter.fragment(large_data)

# Send fragments
for fragment in fragments:
    await transport.send_packet(peer_addr, fragment)

# Reassemble on receiver
reassembler = PacketFragmenter()
for fragment in received_fragments:
    complete = reassembler.add_fragment(fragment)
    if complete:
        original_data = complete
        break
```

### Fragmentation Parameters

- **MTU**: 1400 bytes (default, configurable)
- **Max Payload**: MTU - 32 (header size)
- **Fragment ID**: Random 32-bit ID per message
- **Fragment Index**: 0-based index
- **Fragment Total**: Total number of fragments

## UDP Transport

Provides both reliable and unreliable communication over UDP.

### Unreliable Send (Fast)

```python
from positron_networking.transport import UDPTransport

transport = UDPTransport(host="0.0.0.0", port=8888)
await transport.start()

# Fire-and-forget
await transport.send_unreliable(
    peer_addr=("192.168.1.100", 8888),
    data=b"Quick message"
)
```

### Reliable Send (ACKs + Retransmission)

```python
# With acknowledgments and retransmission
await transport.send_reliable(
    peer_addr=("192.168.1.100", 8888),
    data=b"Important message",
    timeout=5.0
)
```

### Features

- Automatic connection management
- Sequence number tracking
- Retransmission with exponential backoff
- ACK timeout detection
- Keep-alive via PING/PONG
- Automatic fragmentation for large messages

## TCP Transport

Provides reliable, ordered delivery with packet framing over TCP.

### Usage

```python
from positron_networking.transport import TCPTransport

transport = TCPTransport(host="0.0.0.0", port=8888)
await transport.start()

# Send data (automatically framed)
await transport.send(
    peer_addr=("192.168.1.100", 8888),
    data=b"Reliable message"
)

# Connection pooling (automatic)
# Reuses existing connections to same peer
```

### Packet Framing

TCP is a stream protocol, so we use length-prefixed framing:

```
[4-byte length][packet data][4-byte length][packet data]...
```

Each packet is prefixed with its length as a 32-bit big-endian integer.

## Adaptive Flow Control

Combines flow control and congestion control for optimal performance.

### Usage

```python
from positron_networking.transport import AdaptiveFlowController

controller = AdaptiveFlowController(
    mss=1400,
    initial_window=65535
)

# Before sending
if controller.can_send(len(data)):
    await send_data(data)
    controller.on_send(len(data))

# On ACK
controller.on_ack(
    data_size=len(data),
    receiver_window=32768,
    rtt=0.05
)

# On timeout
controller.on_timeout()

# Get effective window
effective_window = controller.get_effective_window()

# Get detailed statistics
stats = controller.get_stats()
```

### Statistics

```python
{
    'flow_control': {
        'window_size': 65535,
        'receiver_window': 32768,
        'bytes_in_flight': 1400,
        'available': 31368,
    },
    'congestion_control': {
        'cwnd': 4200,
        'ssthresh': 32768,
        'in_slow_start': False,
        'in_fast_recovery': False,
        'losses': 0,
        'fast_retransmits': 0,
        'duplicate_acks': 0,
        'min_rtt': 0.045,
    },
    'effective_window': 31368,
}
```

## Error Handling

### Checksum Verification

All packets include a CRC32 checksum:

```python
# Automatic verification on receive
try:
    packet = Packet.from_bytes(packet_data)
    # Checksum verified automatically
except ValueError as e:
    # Invalid checksum
    logger.error(f"Checksum failed: {e}")
```

### Retransmission

Lost packets are automatically retransmitted:

```python
# In Connection class
async def maintenance(self):
    """Check for timeouts and retransmit."""
    now = time.time()
    
    for seq_num, (packet, send_time, retries) in list(self.sent_packets.items()):
        if now - send_time > self.rto:
            if retries < self.max_retries:
                # Retransmit with exponential backoff
                self.rto *= 2
                await self.send_packet(packet)
                self.sent_packets[seq_num] = (packet, now, retries + 1)
            else:
                # Give up after max retries
                del self.sent_packets[seq_num]
                self.on_timeout()
```

### Connection Timeout

Connections are closed if inactive:

```python
# Default timeouts
CONNECTION_TIMEOUT = 60.0  # 60 seconds
PING_INTERVAL = 15.0       # 15 seconds

# Automatic keep-alive
if now - conn.last_activity > PING_INTERVAL:
    await send_ping(conn)

if now - conn.last_activity > CONNECTION_TIMEOUT:
    await close_connection(conn)
```

## Performance Tuning

### MTU Configuration

```python
# Optimize for your network
fragmenter = PacketFragmenter(mtu=1400)  # Default
fragmenter = PacketFragmenter(mtu=9000)  # Jumbo frames
fragmenter = PacketFragmenter(mtu=576)   # Low MTU networks
```

### Window Sizes

```python
# Large bandwidth-delay product networks
controller = FlowController(initial_window=131072)  # 128KB

# Constrained environments
controller = FlowController(initial_window=16384)   # 16KB
```

### Congestion Control Parameters

```python
# Aggressive (low latency networks)
controller = CongestionController(mss=1400)

# Conservative (high loss networks)
controller = CongestionController(mss=512)
```

### Connection Pool Size

```python
# TCP transport
transport = TCPTransport(
    host="0.0.0.0",
    port=8888,
    max_connections=1000  # Adjust based on system resources
)
```

## Best Practices

1. **Choose the Right Transport**
   - UDP unreliable: Low latency, can tolerate loss (heartbeats, metrics)
   - UDP reliable: Balance of latency and reliability (gossip messages)
   - TCP: Maximum reliability, ordered delivery (critical data)

2. **Handle Fragmentation**
   - Configure MTU based on your network
   - Consider overhead of fragmentation
   - Use compression for large messages

3. **Monitor Statistics**
   - Track RTT and packet loss
   - Monitor congestion control state
   - Watch for retransmission rates

4. **Tune Flow Control**
   - Adjust window sizes for your workload
   - Monitor bytes in flight
   - Consider receiver capabilities

5. **Error Recovery**
   - Implement retry logic at application layer
   - Handle connection timeouts gracefully
   - Log errors for debugging

## Integration Example

```python
import asyncio
from positron_networking.transport import UDPTransport, TCPTransport
from positron_networking import Node

class NetworkNode:
    def __init__(self):
        # Create transports
        self.udp_transport = UDPTransport(host="0.0.0.0", port=8888)
        self.tcp_transport = TCPTransport(host="0.0.0.0", port=8889)
        
        # Register handlers
        self.udp_transport.register_handler(self.on_udp_receive)
        self.tcp_transport.register_handler(self.on_tcp_receive)
    
    async def start(self):
        """Start both transports."""
        await self.udp_transport.start()
        await self.tcp_transport.start()
        print("Transports started")
    
    async def on_udp_receive(self, packet, peer_addr):
        """Handle UDP packet."""
        print(f"UDP from {peer_addr}: {packet.payload}")
    
    async def on_tcp_receive(self, packet, peer_addr):
        """Handle TCP packet."""
        print(f"TCP from {peer_addr}: {packet.payload}")
    
    async def send_message(self, peer_addr, data, reliable=True):
        """Send message to peer."""
        if reliable:
            await self.udp_transport.send_reliable(peer_addr, data)
        else:
            await self.udp_transport.send_unreliable(peer_addr, data)
    
    async def stop(self):
        """Stop transports."""
        await self.udp_transport.stop()
        await self.tcp_transport.stop()

# Usage
async def main():
    node = NetworkNode()
    await node.start()
    
    # Send messages
    peer = ("192.168.1.100", 8888)
    await node.send_message(peer, b"Hello!", reliable=True)
    
    # Keep running
    await asyncio.sleep(3600)
    
    await node.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Testing

See `tests/test_transport.py` for comprehensive test suite.

## References

- RFC 793 - Transmission Control Protocol
- RFC 768 - User Datagram Protocol
- RFC 5681 - TCP Congestion Control
- RFC 6298 - Computing TCP's Retransmission Timer
- Jacobson, V. (1988). Congestion Avoidance and Control

---

For more information, see the [main README](../README.md) or visit https://github.com/positron-blockchain/networking
