"""
Tests for transport layer components.
"""
import pytest
import asyncio
from positron_networking.transport import (
    Packet,
    PacketType,
    PacketFlags,
    PacketHeader,
    PacketFragmenter,
    Connection,
    ConnectionState,
    FlowController,
    CongestionController,
    AdaptiveFlowController,
)


class TestPacket:
    """Test packet creation and serialization."""
    
    def test_create_syn_packet(self):
        """Test SYN packet creation."""
        packet = Packet.create_syn(sequence=1000)
        
        assert packet.header.packet_type == PacketType.SYN
        assert packet.header.sequence_number == 1000
        assert packet.payload == b""
    
    def test_create_data_packet(self):
        """Test DATA packet creation."""
        payload = b"Hello, network!"
        packet = Packet.create_data(
            sequence=2000,
            ack_number=1001,
            payload=payload
        )
        
        assert packet.header.packet_type == PacketType.DATA
        assert packet.header.sequence_number == 2000
        assert packet.header.ack_number == 1001
        assert packet.payload == payload
    
    def test_packet_serialization(self):
        """Test packet serialization and deserialization."""
        original = Packet.create_data(
            sequence=3000,
            ack_number=2500,
            payload=b"Test data"
        )
        
        # Serialize
        data = original.to_bytes()
        
        # Deserialize
        restored = Packet.from_bytes(data)
        
        assert restored.header.packet_type == original.header.packet_type
        assert restored.header.sequence_number == original.header.sequence_number
        assert restored.header.ack_number == original.header.ack_number
        assert restored.payload == original.payload
    
    def test_packet_checksum(self):
        """Test checksum verification."""
        packet = Packet.create_data(
            sequence=4000,
            ack_number=3500,
            payload=b"Checksum test"
        )
        
        data = packet.to_bytes()
        
        # Valid checksum
        restored = Packet.from_bytes(data)
        assert restored.payload == packet.payload
        
        # Corrupt data
        corrupted = bytearray(data)
        corrupted[40] ^= 0xFF  # Flip bits in payload
        
        with pytest.raises(ValueError, match="checksum"):
            Packet.from_bytes(bytes(corrupted))
    
    def test_packet_flags(self):
        """Test packet flags."""
        packet = Packet.create_fin(sequence=5000)
        
        assert packet.header.flags & PacketFlags.FIN
        assert not (packet.header.flags & PacketFlags.RST)


class TestPacketFragmenter:
    """Test message fragmentation."""
    
    def test_small_message_no_fragmentation(self):
        """Test that small messages are not fragmented."""
        fragmenter = PacketFragmenter(mtu=1400)
        data = b"Small message"
        
        fragments = fragmenter.fragment(data)
        
        assert len(fragments) == 1
        assert fragments[0].payload == data
    
    def test_large_message_fragmentation(self):
        """Test fragmentation of large messages."""
        fragmenter = PacketFragmenter(mtu=1400)
        data = b"x" * 10000  # 10KB
        
        fragments = fragmenter.fragment(data)
        
        # Should be split into multiple fragments
        assert len(fragments) > 1
        
        # All fragments should have same fragment_id
        fragment_id = fragments[0].header.fragment_id
        for frag in fragments:
            assert frag.header.fragment_id == fragment_id
        
        # Fragment indices should be sequential
        for i, frag in enumerate(fragments):
            assert frag.header.fragment_index == i
        
        # Total should match
        for frag in fragments:
            assert frag.header.fragment_total == len(fragments)
    
    def test_fragment_reassembly(self):
        """Test reassembly of fragmented messages."""
        fragmenter = PacketFragmenter(mtu=1400)
        original_data = b"Hello, network! " * 1000  # ~16KB
        
        # Fragment
        fragments = fragmenter.fragment(original_data)
        
        # Reassemble
        reassembler = PacketFragmenter()
        result = None
        for frag in fragments:
            result = reassembler.add_fragment(frag)
            if result is not None:
                break
        
        assert result == original_data
    
    def test_out_of_order_reassembly(self):
        """Test reassembly with out-of-order fragments."""
        fragmenter = PacketFragmenter(mtu=1400)
        original_data = b"Test data " * 500  # ~5KB
        
        # Fragment
        fragments = fragmenter.fragment(original_data)
        
        # Shuffle fragments
        import random
        shuffled = fragments.copy()
        random.shuffle(shuffled)
        
        # Reassemble
        reassembler = PacketFragmenter()
        result = None
        for frag in shuffled:
            result = reassembler.add_fragment(frag)
            if result is not None:
                break
        
        assert result == original_data


class TestConnection:
    """Test connection state management."""
    
    def test_connection_initialization(self):
        """Test connection initialization."""
        conn = Connection(peer_addr=("192.168.1.100", 8888))
        
        assert conn.state == ConnectionState.CLOSED
        assert conn.peer_addr == ("192.168.1.100", 8888)
        assert conn.sequence_number == 1000  # Initial value
    
    def test_connection_handshake(self):
        """Test three-way handshake."""
        # Client side
        client = Connection(peer_addr=("192.168.1.100", 8888))
        
        # Initiate connection
        syn = client.initiate_connection()
        assert syn.header.packet_type == PacketType.SYN
        assert client.state == ConnectionState.SYN_SENT
        
        # Server side
        server = Connection(peer_addr=("192.168.1.101", 8889))
        
        # Receive SYN
        response = server.handle_packet(syn)
        assert response.header.packet_type == PacketType.SYN_ACK
        assert server.state == ConnectionState.SYN_RCVD
        
        # Client receives SYN_ACK
        ack = client.handle_packet(response)
        assert ack.header.packet_type == PacketType.ACK
        assert client.state == ConnectionState.ESTABLISHED
        
        # Server receives ACK
        result = server.handle_packet(ack)
        assert result is None  # No response needed
        assert server.state == ConnectionState.ESTABLISHED
    
    def test_data_transfer(self):
        """Test data packet handling."""
        conn = Connection(peer_addr=("192.168.1.100", 8888))
        conn.state = ConnectionState.ESTABLISHED
        
        # Create data packet
        data_packet = conn.create_data_packet(b"Hello!")
        
        assert data_packet.header.packet_type == PacketType.DATA
        assert data_packet.payload == b"Hello!"
        
        # Sequence number should increment
        old_seq = conn.sequence_number
        data_packet2 = conn.create_data_packet(b"World!")
        assert conn.sequence_number > old_seq
    
    def test_connection_close(self):
        """Test connection termination."""
        conn = Connection(peer_addr=("192.168.1.100", 8888))
        conn.state = ConnectionState.ESTABLISHED
        
        # Initiate close
        fin = conn.close()
        assert fin.header.packet_type == PacketType.FIN
        assert conn.state == ConnectionState.FIN_WAIT_1
    
    def test_rtt_estimation(self):
        """Test RTT estimation."""
        conn = Connection(peer_addr=("192.168.1.100", 8888))
        
        # First RTT sample
        conn.update_rtt(0.05)  # 50ms
        assert conn.srtt == 0.05
        assert conn.rttvar == 0.025
        
        # Second sample
        conn.update_rtt(0.06)  # 60ms
        assert conn.srtt > 0.05
        assert conn.srtt < 0.06
        
        # RTO should be reasonable
        assert conn.rto >= conn.min_rto
        assert conn.rto <= conn.max_rto


class TestFlowControl:
    """Test flow control mechanisms."""
    
    def test_initial_window(self):
        """Test initial window size."""
        controller = FlowController(initial_window=65535)
        
        assert controller.window_size == 65535
        assert controller.bytes_in_flight == 0
    
    def test_can_send(self):
        """Test send permission."""
        controller = FlowController(initial_window=10000)
        
        # Should be able to send initially
        assert controller.can_send(5000)
        
        # Send data
        controller.on_send(5000)
        assert controller.bytes_in_flight == 5000
        
        # Should still be able to send more
        assert controller.can_send(4000)
        
        # But not too much
        assert not controller.can_send(6000)
    
    def test_ack_handling(self):
        """Test ACK processing."""
        controller = FlowController(initial_window=10000)
        
        # Send data
        controller.on_send(3000)
        assert controller.bytes_in_flight == 3000
        
        # Receive ACK
        controller.on_ack(data_size=3000, receiver_window=10000)
        assert controller.bytes_in_flight == 0
    
    def test_receiver_window(self):
        """Test receiver window limits."""
        controller = FlowController(initial_window=10000)
        
        # Receiver advertises smaller window
        controller.receiver_window = 5000
        
        # Should respect receiver window
        assert controller.can_send(6000) is False
        assert controller.can_send(4000) is True


class TestCongestionControl:
    """Test congestion control algorithms."""
    
    def test_slow_start(self):
        """Test slow start phase."""
        controller = CongestionController(mss=1400)
        
        assert controller.in_slow_start
        initial_cwnd = controller.cwnd
        
        # ACK increases cwnd by 1 MSS
        controller.on_ack()
        assert controller.cwnd == initial_cwnd + 1400
        
        # Another ACK
        controller.on_ack()
        assert controller.cwnd == initial_cwnd + 2 * 1400
    
    def test_congestion_avoidance(self):
        """Test congestion avoidance phase."""
        controller = CongestionController(mss=1400)
        
        # Set high cwnd to exit slow start
        controller.cwnd = 10000
        controller.ssthresh = 8000
        controller.in_slow_start = False
        
        initial_cwnd = controller.cwnd
        
        # ACK increases cwnd linearly
        controller.on_ack()
        increment = controller.mss * controller.mss / initial_cwnd
        assert controller.cwnd == pytest.approx(initial_cwnd + increment)
    
    def test_fast_retransmit(self):
        """Test fast retransmit on 3 duplicate ACKs."""
        controller = CongestionController(mss=1400)
        controller.cwnd = 10000
        
        # First duplicate ACK
        controller.on_duplicate_ack(5000)
        assert not controller.in_fast_recovery
        
        # Second duplicate ACK
        controller.on_duplicate_ack(5000)
        assert not controller.in_fast_recovery
        
        # Third duplicate ACK triggers fast retransmit
        controller.on_duplicate_ack(5000)
        assert controller.in_fast_recovery
        assert controller.ssthresh == 5000  # cwnd / 2
        assert controller.fast_retransmits == 1
    
    def test_timeout_recovery(self):
        """Test recovery from timeout."""
        controller = CongestionController(mss=1400)
        controller.cwnd = 10000
        
        # Timeout
        controller.on_timeout()
        
        # Should enter slow start with cwnd = 1 MSS
        assert controller.cwnd == 1400
        assert controller.in_slow_start
        assert controller.ssthresh == 5000  # cwnd / 2
        assert controller.losses == 1


class TestAdaptiveFlowControl:
    """Test adaptive flow control."""
    
    def test_combined_control(self):
        """Test combined flow and congestion control."""
        controller = AdaptiveFlowController(
            mss=1400,
            initial_window=65535
        )
        
        # Should be able to send initially
        assert controller.can_send(1400)
        
        # Send data
        controller.on_send(1400)
        
        # ACK
        controller.on_ack(
            data_size=1400,
            receiver_window=65535,
            rtt=0.05
        )
        
        # Window should have grown (slow start)
        stats = controller.get_stats()
        assert stats['congestion_control']['cwnd'] > 1400
    
    def test_effective_window(self):
        """Test effective window calculation."""
        controller = AdaptiveFlowController(
            mss=1400,
            initial_window=10000
        )
        
        # Effective window is minimum of flow and congestion windows
        effective = controller.get_effective_window()
        
        assert effective <= 10000
        assert effective <= controller.congestion_controller.get_send_window()
    
    def test_statistics(self):
        """Test statistics gathering."""
        controller = AdaptiveFlowController(
            mss=1400,
            initial_window=65535
        )
        
        stats = controller.get_stats()
        
        # Check structure
        assert 'flow_control' in stats
        assert 'congestion_control' in stats
        assert 'effective_window' in stats
        
        # Check flow control stats
        fc_stats = stats['flow_control']
        assert 'window_size' in fc_stats
        assert 'bytes_in_flight' in fc_stats
        
        # Check congestion control stats
        cc_stats = stats['congestion_control']
        assert 'cwnd' in cc_stats
        assert 'ssthresh' in cc_stats
        assert 'losses' in cc_stats


@pytest.mark.asyncio
class TestTransportIntegration:
    """Integration tests for transport layer."""
    
    async def test_connection_lifecycle(self):
        """Test complete connection lifecycle."""
        # Create connection
        conn = Connection(peer_addr=("192.168.1.100", 8888))
        
        # Initialize
        assert conn.state == ConnectionState.CLOSED
        
        # Connect
        syn = conn.initiate_connection()
        assert conn.state == ConnectionState.SYN_SENT
        
        # Simulate receiving SYN_ACK
        syn_ack = Packet.create_syn_ack(
            sequence=2000,
            ack_number=syn.header.sequence_number + 1
        )
        ack = conn.handle_packet(syn_ack)
        assert conn.state == ConnectionState.ESTABLISHED
        
        # Send data
        data_packet = conn.create_data_packet(b"Hello!")
        assert data_packet.payload == b"Hello!"
        
        # Close
        fin = conn.close()
        assert conn.state == ConnectionState.FIN_WAIT_1
    
    async def test_fragmentation_with_flow_control(self):
        """Test fragmentation combined with flow control."""
        # Create flow controller
        controller = AdaptiveFlowController(mss=1400, initial_window=65535)
        
        # Create large message
        large_data = b"x" * 10000
        
        # Fragment
        fragmenter = PacketFragmenter(mtu=1400)
        fragments = fragmenter.fragment(large_data)
        
        # Send fragments respecting flow control
        sent_count = 0
        for fragment in fragments:
            if controller.can_send(len(fragment.payload)):
                controller.on_send(len(fragment.payload))
                sent_count += 1
                
                # Simulate ACK
                await asyncio.sleep(0.001)
                controller.on_ack(
                    data_size=len(fragment.payload),
                    receiver_window=65535,
                    rtt=0.001
                )
        
        assert sent_count == len(fragments)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
