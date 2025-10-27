# Transport Layer

Production-ready packet-based transport layer for the Positron Blockchain networking stack.

## Components

### `packet.py`
Core packet infrastructure:
- **PacketHeader**: 32-byte fixed header with magic, version, type, flags, sequence, ACK, window, checksum, etc.
- **Packet**: Complete packet abstraction with serialization, checksum verification
- **PacketFragmenter**: MTU-aware message segmentation and reassembly
- **PacketType**: 12 packet types (SYN, ACK, DATA, FIN, PING, FRAGMENT, etc.)

### `connection.py`
Connection lifecycle management:
- **Connection**: TCP-like connection state machine with 10 states
- **ConnectionState**: CLOSED, SYN_SENT, ESTABLISHED, FIN_WAIT, etc.
- RTT estimation (Jacobson/Karels algorithm)
- Retransmission with exponential backoff
- Sequence number management

### `udp_transport.py`
UDP transport with optional reliability:
- **UDPTransport**: Dual-mode UDP transport
- `send_unreliable()`: Fast fire-and-forget (raw UDP)
- `send_reliable()`: ACK-based reliable delivery
- Automatic connection management
- Keep-alive via PING/PONG

### `tcp_transport.py`
TCP transport with packet framing:
- **TCPTransport**: Reliable ordered delivery
- Length-prefixed packet framing (4-byte prefix)
- Connection pooling
- Automatic reconnection

### `flow_control.py`
Flow and congestion control:
- **FlowController**: Sliding window flow control
- **CongestionController**: TCP-like congestion control (slow start, AIMD, fast retransmit/recovery)
- **AdaptiveFlowController**: Combined adaptive control

## Quick Start

```python
import asyncio
from positron_networking.transport import UDPTransport

async def main():
    # Create transport
    transport = UDPTransport(host="0.0.0.0", port=8888)
    
    # Register handler
    async def on_receive(packet, peer_addr):
        print(f"Received: {packet.payload} from {peer_addr}")
    
    transport.register_handler(on_receive)
    
    # Start
    await transport.start()
    
    # Send (reliable)
    await transport.send_reliable(
        peer_addr=("192.168.1.100", 8888),
        data=b"Hello, network!"
    )
    
    # Keep running
    await asyncio.sleep(3600)
    
    await transport.stop()

asyncio.run(main())
```

## Features

- ✅ Packet-based protocol with proper headers
- ✅ CRC32 checksums for integrity
- ✅ Fragmentation/reassembly for large messages
- ✅ Connection state machine (10 states)
- ✅ RTT estimation and adaptive timeouts
- ✅ Flow control (sliding window)
- ✅ Congestion control (slow start, AIMD, fast retransmit/recovery)
- ✅ UDP reliable and unreliable modes
- ✅ TCP with packet framing
- ✅ Keep-alive mechanism
- ✅ Exponential backoff
- ✅ Connection pooling
- ✅ Statistics gathering

## Documentation

- See [docs/TRANSPORT.md](../../../docs/TRANSPORT.md) for comprehensive documentation
- See [examples/transport_example.py](../../../examples/transport_example.py) for working examples
- See [tests/test_transport.py](../../../tests/test_transport.py) for usage examples

## Architecture

```
Application Layer
       ↕
  Transport API
       ↕
UDP/TCP Transport
       ↕
Connection Management
       ↕
Flow/Congestion Control
       ↕
  Packet Layer
       ↕
Network (UDP/TCP)
```

## Testing

```bash
# Run transport tests
pytest tests/test_transport.py -v

# Run with coverage
pytest tests/test_transport.py --cov=positron_networking.transport
```

## Performance

- **Header overhead**: 32 bytes per packet
- **Default MTU**: 1400 bytes
- **Max payload**: 1368 bytes (MTU - header)
- **Memory per connection**: ~1-2KB
- **Scales to**: Thousands of concurrent connections

## License

MIT License - See [LICENSE](../../LICENSE)

---

Part of the [Positron Blockchain](https://github.com/positron-blockchain) networking layer.
