"""
UDP-based transport layer with reliability and ordering options.
"""
import asyncio
from typing import Optional, Dict, Callable, Tuple
import socket
from positron_networking.transport.packet import Packet, PacketType, PacketFragmenter
from positron_networking.transport.connection import Connection, ConnectionState
import time


class UDPTransport:
    """
    UDP-based transport with optional reliability.
    Provides both unreliable (raw UDP) and reliable (UDP + retransmission) modes.
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 0,
        mtu: int = 1472
    ):
        """
        Initialize UDP transport.
        
        Args:
            host: Host to bind to
            port: Port to bind to (0 for random)
            mtu: Maximum transmission unit
        """
        self.host = host
        self.port = port
        self.mtu = mtu
        
        # Socket and transport
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.protocol: Optional['UDPProtocol'] = None
        
        # Connections (for reliable mode)
        self.connections: Dict[str, Connection] = {}
        
        # Fragmenter
        self.fragmenter = PacketFragmenter(mtu=mtu)
        
        # Callbacks
        self.on_packet_callback: Optional[Callable] = None
        self.on_connection_callback: Optional[Callable] = None
        
        # Background tasks
        self._maintenance_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            'packets_sent': 0,
            'packets_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0,
            'errors': 0,
        }
    
    async def start(self):
        """Start the UDP transport."""
        loop = asyncio.get_event_loop()
        
        # Create protocol
        self.protocol = UDPProtocol(self)
        
        # Create UDP endpoint
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self.protocol,
            local_addr=(self.host, self.port)
        )
        
        # Get actual bound port
        sock = self.transport.get_extra_info('socket')
        if sock:
            self.port = sock.getsockname()[1]
        
        # Start maintenance task
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        
        print(f"UDP transport listening on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop the UDP transport."""
        # Stop maintenance task
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        for connection in list(self.connections.values()):
            await self.close_connection(connection.connection_id)
        
        # Close transport
        if self.transport:
            self.transport.close()
    
    def send_packet(self, packet: Packet, addr: Tuple[str, int]):
        """
        Send a packet (unreliable).
        
        Args:
            packet: Packet to send
            addr: Destination (host, port) tuple
        """
        if not self.transport:
            return
        
        data = packet.to_bytes()
        self.transport.sendto(data, addr)
        
        self.stats['packets_sent'] += 1
        self.stats['bytes_sent'] += len(data)
    
    def send_unreliable(self, payload: bytes, addr: Tuple[str, int]):
        """
        Send data unreliably (no retransmission, no ordering).
        
        Args:
            payload: Data to send
            addr: Destination address
        """
        # Fragment if needed
        packets = self.fragmenter.fragment(payload, 0)
        
        for packet in packets:
            self.send_packet(packet, addr)
    
    async def connect(self, addr: Tuple[str, int]) -> Optional[str]:
        """
        Establish a reliable connection.
        
        Args:
            addr: Remote address (host, port)
            
        Returns:
            Connection ID if successful, None otherwise
        """
        connection_id = f"{addr[0]}:{addr[1]}"
        
        if connection_id in self.connections:
            return connection_id
        
        # Create connection
        connection = Connection(
            connection_id=connection_id,
            local_addr=(self.host, self.port),
            remote_addr=addr
        )
        
        # Set callbacks
        connection.on_packet_callback = self._on_connection_packet
        
        self.connections[connection_id] = connection
        
        # Send SYN
        syn = connection.initiate_connection()
        self.send_packet(syn, addr)
        
        # Wait for connection to establish
        for _ in range(30):  # 3 second timeout
            await asyncio.sleep(0.1)
            if connection.is_established():
                if self.on_connection_callback:
                    await self.on_connection_callback(connection_id, 'connected')
                return connection_id
        
        # Connection failed
        del self.connections[connection_id]
        return None
    
    async def send_reliable(self, connection_id: str, payload: bytes):
        """
        Send data reliably over a connection.
        
        Args:
            connection_id: Connection identifier
            payload: Data to send
        """
        connection = self.connections.get(connection_id)
        if not connection or not connection.is_established():
            raise ValueError(f"No established connection: {connection_id}")
        
        # Fragment if needed
        packets = self.fragmenter.fragment(
            payload,
            connection.send_sequence,
            flags=0
        )
        
        # Queue packets for sending
        for packet in packets:
            packet.header.sequence = connection.get_next_sequence()
            connection.send_packet(packet)
        
        # Trigger sending
        await self._send_connection_packets(connection)
    
    async def close_connection(self, connection_id: str):
        """
        Close a reliable connection.
        
        Args:
            connection_id: Connection identifier
        """
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        # Send FIN
        fin = connection.close_connection()
        self.send_packet(fin, connection.remote_addr)
        
        # Wait for close to complete
        for _ in range(30):
            await asyncio.sleep(0.1)
            if connection.is_closed():
                break
        
        # Remove connection
        if connection_id in self.connections:
            del self.connections[connection_id]
            
            if self.on_connection_callback:
                await self.on_connection_callback(connection_id, 'closed')
    
    def _on_connection_packet(self, packet: Packet):
        """Callback when connection receives a complete packet."""
        if self.on_packet_callback:
            asyncio.create_task(self.on_packet_callback(packet))
    
    async def _handle_packet(self, packet: Packet, addr: Tuple[str, int]):
        """Handle incoming packet."""
        self.stats['packets_received'] += 1
        self.stats['bytes_received'] += len(packet.to_bytes())
        
        # Check if it's for an existing connection
        connection_id = f"{addr[0]}:{addr[1]}"
        connection = self.connections.get(connection_id)
        
        if connection:
            # Handle with connection
            response = connection.handle_packet(packet)
            if response:
                self.send_packet(response, addr)
        else:
            # Handle new connection or unreliable packet
            if packet.header.packet_type == PacketType.SYN:
                # Incoming connection
                connection = Connection(
                    connection_id=connection_id,
                    local_addr=(self.host, self.port),
                    remote_addr=addr
                )
                connection.on_packet_callback = self._on_connection_packet
                self.connections[connection_id] = connection
                
                response = connection.handle_packet(packet)
                if response:
                    self.send_packet(response, addr)
                
                if self.on_connection_callback:
                    await self.on_connection_callback(connection_id, 'accepted')
            
            elif packet.is_control_packet():
                # Control packet without connection - ignore
                pass
            else:
                # Unreliable data packet
                if packet.header.packet_type == PacketType.FRAGMENT:
                    # Try to reassemble
                    payload = self.fragmenter.reassemble(packet)
                    if payload and self.on_packet_callback:
                        packet.payload = payload
                        await self.on_packet_callback(packet)
                elif self.on_packet_callback:
                    await self.on_packet_callback(packet)
    
    async def _send_connection_packets(self, connection: Connection):
        """Send queued packets for a connection."""
        packets = connection.get_packets_to_send()
        
        for packet in packets:
            self.send_packet(packet, connection.remote_addr)
    
    async def _maintenance_loop(self):
        """Background maintenance task."""
        while True:
            try:
                await asyncio.sleep(0.1)  # 100ms
                
                current_time = time.time()
                
                for connection_id, connection in list(self.connections.items()):
                    # Send queued packets
                    await self._send_connection_packets(connection)
                    
                    # Handle retransmissions
                    retransmit_packets = connection.get_packets_to_retransmit()
                    for packet in retransmit_packets:
                        self.send_packet(packet, connection.remote_addr)
                    
                    # Check for timeout
                    if connection.is_timed_out(timeout=60.0):
                        await self.close_connection(connection_id)
                
                # Cleanup stale fragment buffers
                if int(current_time) % 30 == 0:  # Every 30 seconds
                    self.fragmenter.cleanup_stale()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in UDP maintenance loop: {e}")
                self.stats['errors'] += 1
    
    def get_stats(self) -> dict:
        """Get transport statistics."""
        return {
            **self.stats,
            'connections': len(self.connections),
            'connection_stats': {
                conn_id: conn.get_stats()
                for conn_id, conn in self.connections.items()
            }
        }


class UDPProtocol(asyncio.DatagramProtocol):
    """Asyncio UDP protocol handler."""
    
    def __init__(self, transport_layer: UDPTransport):
        self.transport_layer = transport_layer
        super().__init__()
    
    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        """Handle received datagram."""
        # Parse packet
        packet = Packet.from_bytes(data)
        if packet:
            asyncio.create_task(self.transport_layer._handle_packet(packet, addr))
    
    def error_received(self, exc: Exception):
        """Handle error."""
        print(f"UDP error: {exc}")
        self.transport_layer.stats['errors'] += 1
