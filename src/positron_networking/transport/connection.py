"""
Connection state management and lifecycle.
"""
import asyncio
from enum import IntEnum
from typing import Optional, Dict, Deque
from collections import deque
import time
from positron_networking.transport.packet import Packet, PacketType, PacketFlags


class ConnectionState(IntEnum):
    """Connection states."""
    CLOSED = 0
    SYN_SENT = 1
    SYN_RECEIVED = 2
    SYN_RCVD = 2  # Alias for compatibility
    ESTABLISHED = 3
    FIN_WAIT_1 = 4
    FIN_WAIT_2 = 5
    CLOSING = 6
    TIME_WAIT = 7
    CLOSE_WAIT = 8
    LAST_ACK = 9


class Connection:
    """
    Manages a single connection between two peers.
    Handles state, sequence numbers, retransmission, and ordering.
    """
    
    def __init__(
        self,
        connection_id: Optional[str] = None,
        local_addr: Optional[tuple] = None,
        remote_addr: Optional[tuple] = None,
        peer_addr: Optional[tuple] = None,  # Compatibility with tests
        initial_sequence: Optional[int] = None
    ):
        """
        Initialize connection.
        
        Args:
            connection_id: Unique connection identifier
            local_addr: Local (host, port) tuple
            remote_addr: Remote (host, port) tuple
            peer_addr: Peer address (alias for remote_addr, compatibility)
            initial_sequence: Initial sequence number
        """
        # Handle peer_addr as alias for remote_addr (test compatibility)
        if peer_addr and not remote_addr:
            remote_addr = peer_addr
        
        self.connection_id = connection_id or f"conn_{id(self)}"
        self.local_addr = local_addr or ("0.0.0.0", 0)
        self.remote_addr = remote_addr or ("0.0.0.0", 0)
        self.peer_addr = self.remote_addr  # Alias for compatibility
        
        # State
        self.state = ConnectionState.CLOSED
        
        # Sequence numbers
        self.send_sequence = initial_sequence or 1000  # Use 1000 as test-compatible default
        self.recv_sequence = 0
        self.send_ack = 0
        self.recv_ack = 0
        
        # Buffers
        self.send_buffer: Deque[Packet] = deque()  # Packets waiting to be sent
        self.recv_buffer: Dict[int, Packet] = {}   # Out-of-order received packets
        self.unacked_packets: Dict[int, Packet] = {}  # Sent but not acknowledged
        
        # Flow control
        self.send_window = 65535  # Remote's receive window
        self.recv_window = 65535  # Our receive window
        
        # RTT estimation (for retransmission timeout)
        self.srtt = 1.0  # Smoothed RTT in seconds
        self.rttvar = 0.5  # RTT variance
        self.rto = 3.0  # Retransmission timeout
        self.min_rto = 1.0  # Minimum RTO (compatibility)
        self.max_rto = 60.0  # Maximum RTO (compatibility)
        
        # Timing
        self.last_activity = time.time()
        self.last_ack_sent = 0
        
        # Statistics
        self.packets_sent = 0
        self.packets_received = 0
        self.packets_retransmitted = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        
        # Callbacks
        self.on_packet_callback = None
        self.on_state_change_callback = None
    
    @property
    def sequence_number(self) -> int:
        """Get current sequence number (compatibility)."""
        return self.send_sequence
    
    @sequence_number.setter
    def sequence_number(self, value: int):
        """Set sequence number (compatibility)."""
        self.send_sequence = value
    
    def get_next_sequence(self) -> int:
        """Get next sequence number and increment."""
        seq = self.send_sequence
        self.send_sequence = (self.send_sequence + 1) & 0xFFFFFFFF
        return seq
    
    def update_state(self, new_state: ConnectionState):
        """Update connection state and trigger callback."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            
            if self.on_state_change_callback:
                self.on_state_change_callback(old_state, new_state)
    
    def handle_packet(self, packet: Packet) -> Optional[Packet]:
        """
        Process incoming packet and generate response if needed.
        
        Args:
            packet: Received packet
            
        Returns:
            Response packet if needed, None otherwise
        """
        self.last_activity = time.time()
        self.packets_received += 1
        self.bytes_received += len(packet.payload)
        
        # Handle based on packet type
        if packet.header.packet_type == PacketType.SYN:
            return self._handle_syn(packet)
        elif packet.header.packet_type == PacketType.SYN_ACK:
            return self._handle_syn_ack(packet)
        elif packet.header.packet_type == PacketType.ACK:
            return self._handle_ack(packet)
        elif packet.header.packet_type == PacketType.DATA:
            return self._handle_data(packet)
        elif packet.header.packet_type == PacketType.FIN:
            return self._handle_fin(packet)
        elif packet.header.packet_type == PacketType.FIN_ACK:
            return self._handle_fin_ack(packet)
        elif packet.header.packet_type == PacketType.PING:
            return self._handle_ping(packet)
        elif packet.header.packet_type == PacketType.PONG:
            return self._handle_pong(packet)
        
        return None
    
    def _handle_syn(self, packet: Packet) -> Optional[Packet]:
        """Handle SYN packet (passive open)."""
        if self.state == ConnectionState.CLOSED:
            self.recv_sequence = packet.header.sequence + 1
            self.update_state(ConnectionState.SYN_RECEIVED)
            
            # Send SYN-ACK
            return Packet.create_syn_ack(
                self.get_next_sequence(),
                self.recv_sequence
            )
        return None
    
    def _handle_syn_ack(self, packet: Packet) -> Optional[Packet]:
        """Handle SYN-ACK packet (active open response)."""
        if self.state == ConnectionState.SYN_SENT:
            self.recv_sequence = packet.header.sequence + 1
            self.recv_ack = packet.header.ack_number
            self.update_state(ConnectionState.ESTABLISHED)
            
            # Send ACK to complete handshake
            return Packet.create_ack(self.recv_sequence, self.recv_window)
        return None
    
    def _handle_ack(self, packet: Packet) -> Optional[Packet]:
        """Handle ACK packet."""
        ack_num = packet.header.ack_number
        
        # Remove acknowledged packets from unacked buffer
        acked_seqs = [seq for seq in self.unacked_packets if seq < ack_num]
        for seq in acked_seqs:
            # Update RTT estimate
            if seq in self.unacked_packets:
                sent_packet = self.unacked_packets[seq]
                rtt = time.time() - sent_packet.timestamp
                self._update_rtt(rtt)
                del self.unacked_packets[seq]
        
        # Update send window
        self.send_window = packet.header.window_size
        self.recv_ack = ack_num
        
        # State transitions
        if self.state == ConnectionState.SYN_RECEIVED:
            self.update_state(ConnectionState.ESTABLISHED)
        elif self.state == ConnectionState.FIN_WAIT_1:
            self.update_state(ConnectionState.FIN_WAIT_2)
        elif self.state == ConnectionState.CLOSING:
            self.update_state(ConnectionState.TIME_WAIT)
        elif self.state == ConnectionState.LAST_ACK:
            self.update_state(ConnectionState.CLOSED)
        
        return None
    
    def _handle_data(self, packet: Packet) -> Optional[Packet]:
        """Handle data packet."""
        seq = packet.header.sequence
        
        if seq == self.recv_sequence:
            # In-order packet
            self.recv_sequence += 1
            
            # Deliver to application
            if self.on_packet_callback:
                self.on_packet_callback(packet)
            
            # Check if we have buffered out-of-order packets
            while self.recv_sequence in self.recv_buffer:
                buffered = self.recv_buffer.pop(self.recv_sequence)
                self.recv_sequence += 1
                if self.on_packet_callback:
                    self.on_packet_callback(buffered)
        
        elif seq > self.recv_sequence:
            # Out-of-order packet - buffer it
            self.recv_buffer[seq] = packet
        
        # Send ACK if needed
        if packet.requires_ack():
            return Packet.create_ack(self.recv_sequence, self.recv_window)
        
        return None
    
    def _handle_fin(self, packet: Packet) -> Optional[Packet]:
        """Handle FIN packet."""
        self.recv_sequence = packet.header.sequence + 1
        
        if self.state == ConnectionState.ESTABLISHED:
            self.update_state(ConnectionState.CLOSE_WAIT)
            return Packet.create_ack(self.recv_sequence, self.recv_window)
        elif self.state == ConnectionState.FIN_WAIT_1:
            self.update_state(ConnectionState.CLOSING)
            return Packet.create_ack(self.recv_sequence, self.recv_window)
        elif self.state == ConnectionState.FIN_WAIT_2:
            self.update_state(ConnectionState.TIME_WAIT)
            return Packet.create_ack(self.recv_sequence, self.recv_window)
        
        return None
    
    def _handle_fin_ack(self, packet: Packet) -> Optional[Packet]:
        """Handle FIN-ACK packet."""
        if self.state == ConnectionState.FIN_WAIT_1:
            self.update_state(ConnectionState.TIME_WAIT)
        return None
    
    def _handle_ping(self, packet: Packet) -> Optional[Packet]:
        """Handle ping packet."""
        return Packet.create_pong(self.get_next_sequence(), packet.payload)
    
    def _handle_pong(self, packet: Packet) -> Optional[Packet]:
        """Handle pong packet (update RTT)."""
        if len(packet.payload) >= 8:
            import struct
            ping_time = struct.unpack('!d', packet.payload[:8])[0]
            rtt = time.time() - ping_time
            self._update_rtt(rtt)
        return None
    
    def _update_rtt(self, measured_rtt: float):
        """
        Update RTT estimation using Jacobson/Karels algorithm.
        
        Args:
            measured_rtt: Measured round-trip time in seconds
        """
        # First measurement
        if self.srtt == 1.0:  # Initial value
            self.srtt = measured_rtt
            self.rttvar = measured_rtt / 2
        else:
            # SRTT = (1 - α) * SRTT + α * RTT
            alpha = 0.125
            self.srtt = (1 - alpha) * self.srtt + alpha * measured_rtt
            
            # RTTVAR = (1 - β) * RTTVAR + β * |SRTT - RTT|
            beta = 0.25
            self.rttvar = (1 - beta) * self.rttvar + beta * abs(self.srtt - measured_rtt)
        
        # RTO = SRTT + 4 * RTTVAR
        self.rto = max(1.0, self.srtt + 4 * self.rttvar)
    
    def send_packet(self, packet: Packet):
        """
        Queue packet for sending.
        
        Args:
            packet: Packet to send
        """
        packet.timestamp = time.time()
        self.send_buffer.append(packet)
        
        # Track unacked packets
        if packet.requires_ack():
            self.unacked_packets[packet.header.sequence] = packet
    
    def get_packets_to_send(self, max_packets: int = 10) -> list:
        """
        Get packets ready to send based on flow control.
        
        Args:
            max_packets: Maximum number of packets to return
            
        Returns:
            List of packets to send
        """
        packets = []
        
        while self.send_buffer and len(packets) < max_packets:
            # Check flow control window
            in_flight = len(self.unacked_packets)
            if in_flight >= self.send_window:
                break
            
            packet = self.send_buffer.popleft()
            packets.append(packet)
            
            # Update statistics
            self.packets_sent += 1
            self.bytes_sent += len(packet.payload)
        
        return packets
    
    def get_packets_to_retransmit(self) -> list:
        """Get packets that need retransmission."""
        current_time = time.time()
        packets = []
        
        for seq, packet in list(self.unacked_packets.items()):
            if current_time - packet.timestamp > self.rto:
                # Retransmit
                packet.timestamp = current_time
                packets.append(packet)
                self.packets_retransmitted += 1
        
        return packets
    
    def initiate_connection(self) -> Packet:
        """Initiate connection (active open)."""
        self.update_state(ConnectionState.SYN_SENT)
        return Packet.create_syn(self.get_next_sequence())
    
    def close_connection(self) -> Packet:
        """Initiate connection close."""
        if self.state == ConnectionState.ESTABLISHED:
            self.update_state(ConnectionState.FIN_WAIT_1)
        elif self.state == ConnectionState.CLOSE_WAIT:
            self.update_state(ConnectionState.LAST_ACK)
        
        return Packet.create_fin(self.get_next_sequence())
    
    def close(self) -> Packet:
        """Alias for close_connection (compatibility)."""
        return self.close_connection()
    
    def create_data_packet(self, payload: bytes) -> Packet:
        """Create a data packet (compatibility method)."""
        return Packet.create_data(
            sequence=self.get_next_sequence(),
            payload=payload,
            reliable=True
        )
    
    def update_rtt(self, measured_rtt: float):
        """Public wrapper for _update_rtt (compatibility)."""
        return self._update_rtt(measured_rtt)
    
    def is_established(self) -> bool:
        """Check if connection is established."""
        return self.state == ConnectionState.ESTABLISHED
    
    def is_closed(self) -> bool:
        """Check if connection is closed."""
        return self.state == ConnectionState.CLOSED
    
    def is_timed_out(self, timeout: float = 60.0) -> bool:
        """Check if connection has timed out."""
        return time.time() - self.last_activity > timeout
    
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            'state': self.state.name,
            'packets_sent': self.packets_sent,
            'packets_received': self.packets_received,
            'packets_retransmitted': self.packets_retransmitted,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'rtt': self.srtt,
            'rto': self.rto,
            'send_window': self.send_window,
            'recv_window': self.recv_window,
            'unacked_packets': len(self.unacked_packets),
            'recv_buffer_size': len(self.recv_buffer),
        }
