"""
Low-level packet structure and definitions for the transport layer.
"""
import struct
import zlib
import time
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional, List
import hashlib


class PacketType(IntEnum):
    """Packet types for transport layer."""
    DATA = 0x01              # Regular data packet
    ACK = 0x02               # Acknowledgment packet
    SYN = 0x03               # Synchronization (connection start)
    SYN_ACK = 0x04           # SYN acknowledgment
    FIN = 0x05               # Finish (connection close)
    FIN_ACK = 0x06           # FIN acknowledgment
    PING = 0x07              # Keepalive/latency check
    PONG = 0x08              # Ping response
    FRAGMENT = 0x09          # Fragmented packet
    RETRANSMIT = 0x0A        # Retransmission request
    FLOW_CONTROL = 0x0B      # Flow control update
    ERROR = 0x0C             # Error notification


class PacketFlags(IntEnum):
    """Flags for packet behavior."""
    NONE = 0x00
    COMPRESSED = 0x01        # Payload is compressed
    ENCRYPTED = 0x02         # Payload is encrypted
    RELIABLE = 0x04          # Requires acknowledgment
    ORDERED = 0x08           # Must be delivered in order
    FRAGMENTED = 0x10        # Part of fragmented message
    PRIORITY = 0x20          # High priority packet
    LAST_FRAGMENT = 0x40     # Last fragment in sequence
    FIN = 0x80               # Connection close flag (compatibility)
    RST = 0x100              # Reset connection flag (compatibility)


@dataclass
class PacketHeader:
    """
    Packet header structure (32 bytes fixed size).
    
    Format:
    - Magic (2 bytes): 0xBEEF (protocol identifier)
    - Version (1 byte): Protocol version
    - Type (1 byte): Packet type
    - Flags (1 byte): Packet flags
    - Reserved (1 byte): Reserved for future use
    - Sequence (4 bytes): Sequence number
    - Ack (4 bytes): Acknowledgment number
    - Window (2 bytes): Flow control window size
    - Checksum (4 bytes): CRC32 checksum
    - Payload Length (4 bytes): Length of payload
    - Fragment ID (4 bytes): Fragment identifier (0 if not fragmented)
    - Fragment Offset (2 bytes): Offset in original message
    - Fragment Total (2 bytes): Total fragments
    """
    
    MAGIC = 0xBEEF
    VERSION = 0x01
    HEADER_SIZE = 28  # Actual struct size
    
    packet_type: int
    flags: int = 0
    sequence: int = 0
    ack_number: int = 0
    window_size: int = 65535
    checksum: int = 0
    payload_length: int = 0
    fragment_id: int = 0
    fragment_offset: int = 0
    fragment_total: int = 0
    
    # Compatibility properties for tests
    @property
    def sequence_number(self) -> int:
        """Alias for sequence (compatibility)."""
        return self.sequence
    
    @sequence_number.setter
    def sequence_number(self, value: int):
        """Alias for sequence (compatibility)."""
        self.sequence = value
    
    @property
    def fragment_index(self) -> int:
        """Alias for fragment_offset (compatibility)."""
        return self.fragment_offset
    
    @fragment_index.setter
    def fragment_index(self, value: int):
        """Alias for fragment_offset (compatibility)."""
        self.fragment_offset = value
    
    def to_bytes(self) -> bytes:
        """Serialize header to bytes."""
        return struct.pack(
            '!HBBBHIHHIBIHH',    # Network byte order (big-endian)
            self.MAGIC,           # Magic number (H = 2 bytes)
            self.VERSION,         # Protocol version (B = 1 byte)
            self.packet_type,     # Packet type (B = 1 byte)
            self.flags,           # Flags (B = 1 byte)
            0,                    # Reserved (B = 1 byte) + padding (B = 1 byte) -> H = 2 bytes
            self.sequence,        # Sequence number (I = 4 bytes)
            self.ack_number,      # Ack number (I = 4 bytes)
            self.window_size,     # Window size (H = 2 bytes)
            self.checksum,        # Checksum (I = 4 bytes)
            self.payload_length,  # Payload length (I = 4 bytes)
            self.fragment_id,     # Fragment ID (I = 4 bytes)
            self.fragment_offset, # Fragment offset (H = 2 bytes)
            self.fragment_total   # Fragment total (H = 2 bytes)
        )
    
    @classmethod
    def from_bytes(cls, data: bytes) -> Optional['PacketHeader']:
        """Deserialize header from bytes."""
        if len(data) < cls.HEADER_SIZE:
            return None
        
        try:
            unpacked = struct.unpack('!HBBBHIHHIBIHH', data[:cls.HEADER_SIZE])
            
            magic, version, pkt_type, flags, _, seq, ack, window, \
                checksum, payload_len, frag_id, frag_offset, frag_total = unpacked
            
            # Validate magic number and version
            if magic != cls.MAGIC:
                return None
            
            if version != cls.VERSION:
                return None
            
            return cls(
                packet_type=pkt_type,
                flags=flags,
                sequence=seq,
                ack_number=ack,
                window_size=window,
                checksum=checksum,
                payload_length=payload_len,
                fragment_id=frag_id,
                fragment_offset=frag_offset,
                fragment_total=frag_total
            )
        except struct.error:
            return None


@dataclass
class Packet:
    """Complete packet with header and payload."""
    
    header: PacketHeader
    payload: bytes = b''
    timestamp: float = field(default_factory=time.time)
    
    MAX_PAYLOAD_SIZE = 65507 - PacketHeader.HEADER_SIZE  # Max UDP - header
    MTU_SAFE_SIZE = 1472 - PacketHeader.HEADER_SIZE      # MTU safe size
    
    def __post_init__(self):
        """Update header with payload information."""
        self.header.payload_length = len(self.payload)
    
    def compute_checksum(self) -> int:
        """Compute CRC32 checksum of header + payload."""
        # Temporarily set checksum to 0
        original_checksum = self.header.checksum
        self.header.checksum = 0
        
        # Compute checksum
        header_bytes = self.header.to_bytes()
        checksum = zlib.crc32(header_bytes + self.payload) & 0xFFFFFFFF
        
        # Restore and return
        self.header.checksum = original_checksum
        return checksum
    
    def verify_checksum(self) -> bool:
        """Verify packet checksum."""
        stored_checksum = self.header.checksum
        computed_checksum = self.compute_checksum()
        return stored_checksum == computed_checksum
    
    def to_bytes(self) -> bytes:
        """Serialize complete packet to bytes."""
        # Compute and set checksum
        self.header.checksum = self.compute_checksum()
        
        # Serialize
        return self.header.to_bytes() + self.payload
    
    @classmethod
    def from_bytes(cls, data: bytes) -> Optional['Packet']:
        """Deserialize packet from bytes."""
        if len(data) < PacketHeader.HEADER_SIZE:
            return None
        
        # Parse header
        header = PacketHeader.from_bytes(data[:PacketHeader.HEADER_SIZE])
        if not header:
            return None
        
        # Extract payload
        payload_start = PacketHeader.HEADER_SIZE
        payload_end = payload_start + header.payload_length
        
        if len(data) < payload_end:
            return None
        
        payload = data[payload_start:payload_end]
        
        # Create packet
        packet = cls(header=header, payload=payload)
        
        # Verify checksum
        if not packet.verify_checksum():
            raise ValueError("Packet checksum verification failed")
        
        return packet
    
    def compress(self):
        """Compress packet payload."""
        if not (self.header.flags & PacketFlags.COMPRESSED):
            compressed = zlib.compress(self.payload, level=6)
            if len(compressed) < len(self.payload):
                self.payload = compressed
                self.header.flags |= PacketFlags.COMPRESSED
                self.header.payload_length = len(self.payload)
    
    def decompress(self):
        """Decompress packet payload."""
        if self.header.flags & PacketFlags.COMPRESSED:
            self.payload = zlib.decompress(self.payload)
            self.header.flags &= ~PacketFlags.COMPRESSED
            self.header.payload_length = len(self.payload)
    
    @classmethod
    def create_syn(cls, sequence: int) -> 'Packet':
        """Create SYN packet for connection establishment."""
        header = PacketHeader(
            packet_type=PacketType.SYN,
            flags=PacketFlags.RELIABLE,
            sequence=sequence
        )
        return cls(header=header)
    
    @classmethod
    def create_syn_ack(cls, sequence: int, ack_number: int) -> 'Packet':
        """Create SYN-ACK packet."""
        header = PacketHeader(
            packet_type=PacketType.SYN_ACK,
            flags=PacketFlags.RELIABLE,
            sequence=sequence,
            ack_number=ack_number
        )
        return cls(header=header)
    
    @classmethod
    def create_ack(cls, ack_number: int, window_size: int = 65535) -> 'Packet':
        """Create ACK packet."""
        header = PacketHeader(
            packet_type=PacketType.ACK,
            ack_number=ack_number,
            window_size=window_size
        )
        return cls(header=header)
    
    @classmethod
    def create_data(
        cls,
        sequence: int,
        payload: bytes,
        ack_number: int = 0,
        reliable: bool = True,
        ordered: bool = False
    ) -> 'Packet':
        """Create data packet."""
        flags = PacketFlags.NONE
        if reliable:
            flags |= PacketFlags.RELIABLE
        if ordered:
            flags |= PacketFlags.ORDERED
        
        header = PacketHeader(
            packet_type=PacketType.DATA,
            flags=flags,
            sequence=sequence,
            ack_number=ack_number
        )
        return cls(header=header, payload=payload)
    
    @classmethod
    def create_ping(cls, sequence: int) -> 'Packet':
        """Create ping packet."""
        header = PacketHeader(
            packet_type=PacketType.PING,
            sequence=sequence
        )
        # Include timestamp in payload
        timestamp = struct.pack('!d', time.time())
        return cls(header=header, payload=timestamp)
    
    @classmethod
    def create_pong(cls, sequence: int, ping_payload: bytes) -> 'Packet':
        """Create pong packet in response to ping."""
        header = PacketHeader(
            packet_type=PacketType.PONG,
            sequence=sequence
        )
        return cls(header=header, payload=ping_payload)
    
    @classmethod
    def create_fin(cls, sequence: int) -> 'Packet':
        """Create FIN packet for connection termination."""
        header = PacketHeader(
            packet_type=PacketType.FIN,
            flags=PacketFlags.RELIABLE | PacketFlags.FIN,  # Add FIN flag
            sequence=sequence
        )
        return cls(header=header)
    
    def is_control_packet(self) -> bool:
        """Check if this is a control packet."""
        control_types = {
            PacketType.SYN,
            PacketType.SYN_ACK,
            PacketType.FIN,
            PacketType.FIN_ACK,
            PacketType.ACK,
            PacketType.PING,
            PacketType.PONG,
            PacketType.FLOW_CONTROL,
            PacketType.ERROR
        }
        return self.header.packet_type in control_types
    
    def requires_ack(self) -> bool:
        """Check if packet requires acknowledgment."""
        return bool(self.header.flags & PacketFlags.RELIABLE)
    
    def __repr__(self) -> str:
        return (f"Packet(type={PacketType(self.header.packet_type).name}, "
                f"seq={self.header.sequence}, "
                f"ack={self.header.ack_number}, "
                f"len={self.header.payload_length})")


class PacketFragmenter:
    """Handles fragmentation and reassembly of large messages."""
    
    def __init__(self, mtu: int = Packet.MTU_SAFE_SIZE):
        """
        Initialize fragmenter.
        
        Args:
            mtu: Maximum transmission unit (payload size)
        """
        self.mtu = mtu
        self.reassembly_buffer: dict = {}  # fragment_id -> {offset -> fragment}
    
    def fragment(self, payload: bytes, sequence: int = 0, flags: int = 0) -> List[Packet]:
        """
        Fragment large payload into multiple packets.
        
        Args:
            payload: Data to fragment
            sequence: Starting sequence number (default: 0)
            flags: Packet flags
            
        Returns:
            List of fragment packets
        """
        if len(payload) <= self.mtu:
            # No fragmentation needed
            return [Packet.create_data(sequence, payload)]
        
        fragments = []
        fragment_id = hash(payload) & 0xFFFFFFFF  # Use hash as fragment ID
        total_fragments = (len(payload) + self.mtu - 1) // self.mtu
        
        for i in range(total_fragments):
            offset = i * self.mtu
            chunk = payload[offset:offset + self.mtu]
            
            frag_flags = flags | PacketFlags.FRAGMENTED
            if i == total_fragments - 1:
                frag_flags |= PacketFlags.LAST_FRAGMENT
            
            header = PacketHeader(
                packet_type=PacketType.FRAGMENT,
                flags=frag_flags,
                sequence=sequence + i,
                fragment_id=fragment_id,
                fragment_offset=i,
                fragment_total=total_fragments
            )
            
            fragments.append(Packet(header=header, payload=chunk))
        
        return fragments
    
    def reassemble(self, packet: Packet) -> Optional[bytes]:
        """
        Reassemble fragmented packet.
        
        Args:
            packet: Fragment packet
            
        Returns:
            Complete payload if all fragments received, None otherwise
        """
        if not (packet.header.flags & PacketFlags.FRAGMENTED):
            return packet.payload
        
        fragment_id = packet.header.fragment_id
        
        # Initialize reassembly buffer for this fragment ID
        if fragment_id not in self.reassembly_buffer:
            self.reassembly_buffer[fragment_id] = {
                'fragments': {},
                'total': packet.header.fragment_total,
                'timestamp': time.time()
            }
        
        buffer = self.reassembly_buffer[fragment_id]
        
        # Store fragment
        buffer['fragments'][packet.header.fragment_offset] = packet.payload
        
        # Check if we have all fragments
        if len(buffer['fragments']) == buffer['total']:
            # Reassemble in order
            payload = b''.join(
                buffer['fragments'][i] for i in range(buffer['total'])
            )
            
            # Clean up
            del self.reassembly_buffer[fragment_id]
            
            return payload
        
        return None
    
    def add_fragment(self, packet: Packet) -> Optional[bytes]:
        """
        Add a fragment and try to reassemble (compatibility alias).
        
        Args:
            packet: Fragment packet
            
        Returns:
            Complete payload if all fragments received, None otherwise
        """
        return self.reassemble(packet)
    
    def cleanup_stale(self, timeout: float = 30.0):
        """Remove stale reassembly buffers."""
        current_time = time.time()
        stale_ids = [
            frag_id for frag_id, buffer in self.reassembly_buffer.items()
            if current_time - buffer['timestamp'] > timeout
        ]
        
        for frag_id in stale_ids:
            del self.reassembly_buffer[frag_id]
