"""
TCP-based transport layer (improved over the basic network.py).
"""
import asyncio
from typing import Optional, Dict, Callable, Tuple
from positron_networking.transport.packet import Packet, PacketFragmenter
from positron_networking.transport.connection import Connection
import struct


class TCPTransport:
    """
    TCP-based transport with packet framing.
    Uses our packet format over TCP for consistency.
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 0,
        max_connections: int = 100
    ):
        """
        Initialize TCP transport.
        
        Args:
            host: Host to bind to
            port: Port to bind to
            max_connections: Maximum concurrent connections
        """
        self.host = host
        self.port = port
        self.max_connections = max_connections
        
        # Server
        self.server: Optional[asyncio.Server] = None
        
        # Connections
        self.connections: Dict[str, TCPConnection] = {}
        
        # Fragmenter
        self.fragmenter = PacketFragmenter()
        
        # Callbacks
        self.on_packet_callback: Optional[Callable] = None
        self.on_connection_callback: Optional[Callable] = None
        
        # Connection semaphore
        self._connection_semaphore = asyncio.Semaphore(max_connections)
        
        # Statistics
        self.stats = {
            'packets_sent': 0,
            'packets_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0,
            'connections_accepted': 0,
            'connections_established': 0,
            'errors': 0,
        }
    
    async def start(self):
        """Start the TCP transport server."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port
        )
        
        # Get actual bound port
        addr = self.server.sockets[0].getsockname()
        self.port = addr[1]
        
        print(f"TCP transport listening on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop the TCP transport server."""
        # Close all connections
        close_tasks = []
        for conn_id in list(self.connections.keys()):
            close_tasks.append(self.close_connection(conn_id))
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
    
    async def connect(self, host: str, port: int) -> Optional[str]:
        """
        Connect to a remote peer.
        
        Args:
            host: Remote host
            port: Remote port
            
        Returns:
            Connection ID if successful
        """
        try:
            reader, writer = await asyncio.open_connection(host, port)
            
            # Create connection
            connection_id = f"{host}:{port}"
            connection = TCPConnection(reader, writer, (host, port), self)
            self.connections[connection_id] = connection
            
            # Start receiving
            asyncio.create_task(connection.receive_loop())
            
            self.stats['connections_established'] += 1
            
            if self.on_connection_callback:
                await self.on_connection_callback(connection_id, 'connected')
            
            return connection_id
            
        except Exception as e:
            print(f"Failed to connect to {host}:{port}: {e}")
            self.stats['errors'] += 1
            return None
    
    async def send_packet(self, connection_id: str, packet: Packet):
        """
        Send packet over TCP connection.
        
        Args:
            connection_id: Connection identifier
            packet: Packet to send
        """
        connection = self.connections.get(connection_id)
        if not connection:
            raise ValueError(f"No connection: {connection_id}")
        
        await connection.send_packet(packet)
        
        self.stats['packets_sent'] += 1
        self.stats['bytes_sent'] += len(packet.payload)
    
    async def send_data(self, connection_id: str, payload: bytes):
        """
        Send data over TCP connection.
        
        Args:
            connection_id: Connection identifier
            payload: Data to send
        """
        # Fragment if needed
        packets = self.fragmenter.fragment(payload, 0)
        
        for packet in packets:
            await self.send_packet(connection_id, packet)
    
    async def close_connection(self, connection_id: str):
        """
        Close a TCP connection.
        
        Args:
            connection_id: Connection identifier
        """
        connection = self.connections.get(connection_id)
        if connection:
            await connection.close()
            del self.connections[connection_id]
            
            if self.on_connection_callback:
                await self.on_connection_callback(connection_id, 'closed')
    
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ):
        """Handle incoming client connection."""
        async with self._connection_semaphore:
            peer_addr = writer.get_extra_info('peername')
            connection_id = f"{peer_addr[0]}:{peer_addr[1]}"
            
            connection = TCPConnection(reader, writer, peer_addr, self)
            self.connections[connection_id] = connection
            
            self.stats['connections_accepted'] += 1
            
            if self.on_connection_callback:
                await self.on_connection_callback(connection_id, 'accepted')
            
            try:
                await connection.receive_loop()
            finally:
                if connection_id in self.connections:
                    del self.connections[connection_id]
                await connection.close()
    
    def get_stats(self) -> dict:
        """Get transport statistics."""
        return {
            **self.stats,
            'active_connections': len(self.connections),
        }


class TCPConnection:
    """Represents a single TCP connection."""
    
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer_addr: Tuple,
        transport: TCPTransport
    ):
        self.reader = reader
        self.writer = writer
        self.peer_addr = peer_addr
        self.transport = transport
        self.is_open = True
        self._lock = asyncio.Lock()
    
    async def send_packet(self, packet: Packet):
        """Send packet over TCP with length framing."""
        async with self._lock:
            if not self.is_open:
                raise ConnectionError("Connection closed")
            
            try:
                data = packet.to_bytes()
                
                # Send length prefix (4 bytes)
                length = struct.pack('>I', len(data))
                self.writer.write(length + data)
                await self.writer.drain()
                
            except Exception as e:
                self.is_open = False
                raise e
    
    async def receive_packet(self) -> Optional[Packet]:
        """Receive packet from TCP connection."""
        try:
            # Read length prefix
            length_data = await self.reader.readexactly(4)
            length = struct.unpack('>I', length_data)[0]
            
            # Validate length (max 10MB)
            if length > 10 * 1024 * 1024:
                raise ValueError("Packet too large")
            
            # Read packet data
            data = await self.reader.readexactly(length)
            
            # Parse packet
            return Packet.from_bytes(data)
            
        except asyncio.IncompleteReadError:
            self.is_open = False
            return None
        except Exception as e:
            self.is_open = False
            self.transport.stats['errors'] += 1
            raise e
    
    async def receive_loop(self):
        """Receive packets in a loop."""
        while self.is_open:
            try:
                packet = await self.receive_packet()
                if packet is None:
                    break
                
                self.transport.stats['packets_received'] += 1
                self.transport.stats['bytes_received'] += len(packet.payload)
                
                # Handle fragmentation
                if packet.header.packet_type == packet.header.packet_type.FRAGMENT:
                    payload = self.transport.fragmenter.reassemble(packet)
                    if payload and self.transport.on_packet_callback:
                        packet.payload = payload
                        await self.transport.on_packet_callback(packet)
                elif self.transport.on_packet_callback:
                    await self.transport.on_packet_callback(packet)
                
            except Exception as e:
                print(f"Error receiving from {self.peer_addr}: {e}")
                break
    
    async def close(self):
        """Close the TCP connection."""
        self.is_open = False
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
