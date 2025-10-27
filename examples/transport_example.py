#!/usr/bin/env python3
"""
Example usage of Positron Blockchain networking transport layer.
Demonstrates UDP/TCP transports, fragmentation, and flow control.
"""
import asyncio
import logging
from positron_networking.transport import (
    UDPTransport,
    TCPTransport,
    PacketFragmenter,
    AdaptiveFlowController,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def udp_example():
    """Demonstrate UDP transport with reliable/unreliable modes."""
    logger.info("=== UDP Transport Example ===")
    
    # Create UDP transport
    transport = UDPTransport(host="0.0.0.0", port=9000)
    
    # Register message handler
    async def on_receive(packet, peer_addr):
        logger.info(f"Received UDP packet from {peer_addr}: {packet.payload[:50]}...")
    
    transport.register_handler(on_receive)
    
    # Start transport
    await transport.start()
    logger.info("UDP transport listening on 0.0.0.0:9000")
    
    # Simulate peer address (in real use, this would be actual peer)
    peer_addr = ("127.0.0.1", 9001)
    
    # Fast unreliable send (fire-and-forget)
    logger.info("Sending unreliable message...")
    await transport.send_unreliable(
        peer_addr=peer_addr,
        data=b"Quick heartbeat message"
    )
    
    # Reliable send with ACKs
    logger.info("Sending reliable message...")
    try:
        await transport.send_reliable(
            peer_addr=peer_addr,
            data=b"Important message that needs ACK",
            timeout=2.0
        )
    except asyncio.TimeoutError:
        logger.warning("Message not acknowledged (peer may not be running)")
    
    # Send large message (auto-fragmented)
    logger.info("Sending large fragmented message...")
    large_data = b"x" * 10000
    try:
        await transport.send_reliable(
            peer_addr=peer_addr,
            data=large_data,
            timeout=2.0
        )
    except asyncio.TimeoutError:
        logger.warning("Fragmented message not acknowledged")
    
    # Get statistics
    stats = transport.get_stats()
    logger.info(f"UDP Stats: {stats}")
    
    await asyncio.sleep(1)
    await transport.stop()
    logger.info("UDP transport stopped")


async def tcp_example():
    """Demonstrate TCP transport with packet framing."""
    logger.info("\n=== TCP Transport Example ===")
    
    # Create TCP transport
    transport = TCPTransport(host="0.0.0.0", port=9100)
    
    # Register message handler
    async def on_receive(packet, peer_addr):
        logger.info(f"Received TCP packet from {peer_addr}: {packet.payload[:50]}...")
    
    transport.register_handler(on_receive)
    
    # Start transport
    await transport.start()
    logger.info("TCP transport listening on 0.0.0.0:9100")
    
    # Simulate peer address
    peer_addr = ("127.0.0.1", 9101)
    
    # Send message (automatically framed)
    logger.info("Sending TCP message...")
    try:
        await transport.send(
            peer_addr=peer_addr,
            data=b"Reliable TCP message with framing"
        )
    except Exception as e:
        logger.warning(f"Could not send (peer may not be running): {e}")
    
    # Send multiple messages (connection reused)
    for i in range(3):
        try:
            await transport.send(
                peer_addr=peer_addr,
                data=f"Message {i}".encode()
            )
        except Exception:
            pass
    
    await asyncio.sleep(1)
    await transport.stop()
    logger.info("TCP transport stopped")


async def fragmentation_example():
    """Demonstrate message fragmentation."""
    logger.info("\n=== Fragmentation Example ===")
    
    fragmenter = PacketFragmenter(mtu=1400)
    
    # Create large message
    large_message = b"Hello, Network! " * 1000  # ~16KB
    logger.info(f"Original message size: {len(large_message)} bytes")
    
    # Fragment the message
    fragments = fragmenter.fragment(large_message)
    logger.info(f"Fragmented into {len(fragments)} packets")
    
    # Show fragment details
    for i, fragment in enumerate(fragments):
        logger.info(
            f"Fragment {i}: {len(fragment.payload)} bytes "
            f"(seq={fragment.header.sequence_number})"
        )
    
    # Reassemble
    reassembler = PacketFragmenter()
    for fragment in fragments:
        complete = reassembler.add_fragment(fragment)
        if complete:
            logger.info(f"Reassembled message size: {len(complete)} bytes")
            assert complete == large_message
            logger.info("✓ Reassembly successful!")
            break


async def flow_control_example():
    """Demonstrate adaptive flow control."""
    logger.info("\n=== Flow Control Example ===")
    
    # Create flow controller
    controller = AdaptiveFlowController(
        mss=1400,
        initial_window=65535
    )
    
    logger.info("Initial state:")
    stats = controller.get_stats()
    logger.info(f"  Effective window: {stats['effective_window']} bytes")
    logger.info(f"  Congestion window: {stats['congestion_control']['cwnd']} bytes")
    
    # Simulate sending data
    data_size = 1400
    
    # Check if we can send
    if controller.can_send(data_size):
        logger.info(f"\n✓ Can send {data_size} bytes")
        controller.on_send(data_size)
        
        # Simulate ACK after 50ms
        await asyncio.sleep(0.05)
        controller.on_ack(
            data_size=data_size,
            receiver_window=65535,
            rtt=0.05
        )
        logger.info("ACK received, window updated")
    
    # Send more data (slow start phase)
    for i in range(10):
        if controller.can_send(data_size):
            controller.on_send(data_size)
            await asyncio.sleep(0.02)
            controller.on_ack(
                data_size=data_size,
                receiver_window=65535,
                rtt=0.02
            )
    
    logger.info("\nAfter 10 ACKs (slow start):")
    stats = controller.get_stats()
    logger.info(f"  Congestion window: {stats['congestion_control']['cwnd']} bytes")
    logger.info(f"  In slow start: {stats['congestion_control']['in_slow_start']}")
    
    # Simulate timeout
    logger.info("\nSimulating timeout...")
    controller.on_timeout()
    
    logger.info("After timeout:")
    stats = controller.get_stats()
    logger.info(f"  Congestion window: {stats['congestion_control']['cwnd']} bytes")
    logger.info(f"  Slow start threshold: {stats['congestion_control']['ssthresh']} bytes")
    logger.info(f"  Losses: {stats['congestion_control']['losses']}")


async def peer_communication_example():
    """Demonstrate peer-to-peer communication."""
    logger.info("\n=== Peer Communication Example ===")
    
    # Node 1
    transport1 = UDPTransport(host="0.0.0.0", port=9200)
    received1 = []
    
    async def handler1(packet, peer_addr):
        received1.append((packet, peer_addr))
        logger.info(f"Node 1 received: {packet.payload} from {peer_addr}")
    
    transport1.register_handler(handler1)
    await transport1.start()
    logger.info("Node 1 started on port 9200")
    
    # Node 2
    transport2 = UDPTransport(host="0.0.0.0", port=9201)
    received2 = []
    
    async def handler2(packet, peer_addr):
        received2.append((packet, peer_addr))
        logger.info(f"Node 2 received: {packet.payload} from {peer_addr}")
    
    transport2.register_handler(handler2)
    await transport2.start()
    logger.info("Node 2 started on port 9201")
    
    # Exchange messages
    logger.info("\nExchanging messages...")
    
    # Node 1 -> Node 2
    try:
        await transport1.send_reliable(
            peer_addr=("127.0.0.1", 9201),
            data=b"Hello from Node 1",
            timeout=1.0
        )
        logger.info("✓ Node 1 sent to Node 2")
    except asyncio.TimeoutError:
        logger.warning("✗ Node 1 -> Node 2 timed out")
    
    # Node 2 -> Node 1
    try:
        await transport2.send_reliable(
            peer_addr=("127.0.0.1", 9200),
            data=b"Hello from Node 2",
            timeout=1.0
        )
        logger.info("✓ Node 2 sent to Node 1")
    except asyncio.TimeoutError:
        logger.warning("✗ Node 2 -> Node 1 timed out")
    
    await asyncio.sleep(1)
    
    # Cleanup
    await transport1.stop()
    await transport2.stop()
    logger.info("\nBoth nodes stopped")


async def main():
    """Run all examples."""
    print("=" * 70)
    print("Positron Blockchain - Transport Layer Examples")
    print("=" * 70)
    
    try:
        # Run examples
        await udp_example()
        await tcp_example()
        await fragmentation_example()
        await flow_control_example()
        await peer_communication_example()
        
        print("\n" + "=" * 70)
        print("All examples completed!")
        print("=" * 70)
        
    except Exception as e:
        logger.error(f"Error running examples: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
