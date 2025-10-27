"""
High-performance async networking layer for peer communication.
"""
import asyncio
from typing import Optional, Dict, Callable, Tuple
from positron_networking.protocol import Message, MessageFactory, MessageType
from positron_networking.identity import Identity
import struct


class Connection:
    """Represents a connection to a peer."""
    
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer_address: str,
        peer_node_id: Optional[str] = None
    ):
        """
        Initialize connection.
        
        Args:
            reader: Stream reader
            writer: Stream writer
            peer_address: Peer's address
            peer_node_id: Peer's node ID (if known)
        """
        self.reader = reader
        self.writer = writer
        self.peer_address = peer_address
        self.peer_node_id = peer_node_id
        self.is_open = True
        self._lock = asyncio.Lock()
    
    async def send_message(self, message: Message):
        """
        Send a message over this connection.
        
        Args:
            message: Message to send
        """
        async with self._lock:
            if not self.is_open:
                raise ConnectionError("Connection is closed")
            
            try:
                # Serialize message
                data = message.to_bytes()
                
                # Send length prefix (4 bytes, big-endian)
                length = struct.pack(">I", len(data))
                self.writer.write(length + data)
                await self.writer.drain()
            except Exception as e:
                self.is_open = False
                raise e
    
    async def receive_message(self) -> Optional[Message]:
        """
        Receive a message from this connection.
        
        Returns:
            Received message or None if connection closed
        """
        try:
            # Read length prefix
            length_data = await self.reader.readexactly(4)
            length = struct.unpack(">I", length_data)[0]
            
            # Validate length (max 10MB)
            if length > 10 * 1024 * 1024:
                raise ValueError("Message too large")
            
            # Read message data
            data = await self.reader.readexactly(length)
            
            # Deserialize message
            return Message.from_bytes(data)
        except asyncio.IncompleteReadError:
            self.is_open = False
            return None
        except Exception as e:
            self.is_open = False
            raise e
    
    async def close(self):
        """Close the connection."""
        self.is_open = False
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
    
    def __str__(self) -> str:
        return f"Connection({self.peer_address}, {self.peer_node_id})"


class NetworkTransport:
    """Handles network transport for the decentralized network."""
    
    def __init__(
        self,
        identity: Identity,
        host: str = "0.0.0.0",
        port: int = 8888,
        max_connections: int = 100,
        connection_timeout: float = 10.0
    ):
        """
        Initialize network transport.
        
        Args:
            identity: Node identity
            host: Host to bind to
            port: Port to bind to
            max_connections: Maximum concurrent connections
            max_connections: Maximum number of concurrent connections
            connection_timeout: Timeout for connection attempts
        """
        self.identity = identity
        self.host = host
        self.port = port
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        
        # Active connections
        self.connections: Dict[str, Connection] = {}
        
        # Message handler
        self.message_handler: Optional[Callable] = None
        
        # Server
        self.server: Optional[asyncio.Server] = None
        
        # Connection semaphore to limit concurrent connections
        self._connection_semaphore = asyncio.Semaphore(max_connections)
    
    async def start(self):
        """Start the network transport server."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port
        )
        
        addr = self.server.sockets[0].getsockname()
        print(f"Network transport listening on {addr[0]}:{addr[1]}")
    
    async def stop(self):
        """Stop the network transport server."""
        # Close all connections
        close_tasks = [conn.close() for conn in self.connections.values()]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        self.connections.clear()
        
        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
    
    def set_message_handler(self, handler: Callable):
        """
        Set the handler for received messages.
        
        Args:
            handler: Async function to handle messages
        """
        self.message_handler = handler
    
    async def connect(self, address: str) -> Optional[Connection]:
        """
        Connect to a peer.
        
        Args:
            address: Peer address in "host:port" format
            
        Returns:
            Connection object or None if failed
        """
        host, port = self._parse_address(address)
        
        try:
            async with asyncio.timeout(self.connection_timeout):
                reader, writer = await asyncio.open_connection(host, port)
            
            connection = Connection(reader, writer, address)
            
            # Perform handshake
            if not await self._perform_handshake(connection):
                await connection.close()
                return None
            
            # Store connection
            if connection.peer_node_id:
                self.connections[connection.peer_node_id] = connection
            
            # Start receiving messages from this connection
            asyncio.create_task(self._receive_loop(connection))
            
            return connection
        except Exception as e:
            print(f"Failed to connect to {address}: {e}")
            return None
    
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ):
        """
        Handle incoming client connection.
        
        Args:
            reader: Stream reader
            writer: Stream writer
        """
        async with self._connection_semaphore:
            peer_addr = writer.get_extra_info('peername')
            address = f"{peer_addr[0]}:{peer_addr[1]}"
            connection = Connection(reader, writer, address)
            
            try:
                # Wait for handshake
                if not await self._handle_handshake(connection):
                    await connection.close()
                    return
                
                # Store connection
                if connection.peer_node_id:
                    self.connections[connection.peer_node_id] = connection
                
                # Start receiving messages
                await self._receive_loop(connection)
                
            except Exception as e:
                print(f"Error handling client {address}: {e}")
            finally:
                if connection.peer_node_id and connection.peer_node_id in self.connections:
                    del self.connections[connection.peer_node_id]
                await connection.close()
    
    async def _perform_handshake(self, connection: Connection) -> bool:
        """
        Perform handshake as initiator.
        
        Args:
            connection: Connection to handshake with
            
        Returns:
            True if handshake successful
        """
        try:
            # Send handshake
            handshake = MessageFactory.create_handshake(
                self.identity.node_id,
                self.identity.get_public_key_bytes(),
                f"{self.host}:{self.port}"
            )
            
            # Sign the handshake
            handshake.signature = self.identity.sign(handshake.get_signable_data())
            
            await connection.send_message(handshake)
            
            # Wait for handshake ack
            async with asyncio.timeout(self.connection_timeout):
                response = await connection.receive_message()
            
            if not response or response.msg_type != MessageType.HANDSHAKE_ACK:
                return False
            
            # Verify signature
            if response.signature:
                public_key = response.payload.get("public_key")
                if not self.identity.verify(
                    public_key,
                    response.get_signable_data(),
                    response.signature
                ):
                    return False
            
            connection.peer_node_id = response.sender_id
            return True
            
        except Exception as e:
            print(f"Handshake failed: {e}")
            return False
    
    async def _handle_handshake(self, connection: Connection) -> bool:
        """
        Handle handshake as receiver.
        
        Args:
            connection: Connection to handshake with
            
        Returns:
            True if handshake successful
        """
        try:
            # Wait for handshake
            async with asyncio.timeout(self.connection_timeout):
                handshake = await connection.receive_message()
            
            if not handshake or handshake.msg_type != MessageType.HANDSHAKE:
                return False
            
            # Verify signature
            if handshake.signature:
                public_key = handshake.payload.get("public_key")
                if not self.identity.verify(
                    public_key,
                    handshake.get_signable_data(),
                    handshake.signature
                ):
                    return False
            
            connection.peer_node_id = handshake.sender_id
            
            # Send handshake ack
            ack = MessageFactory.create_handshake_ack(
                self.identity.node_id,
                self.identity.get_public_key_bytes(),
                []  # Empty peer list for now
            )
            
            # Sign the ack
            ack.signature = self.identity.sign(ack.get_signable_data())
            
            await connection.send_message(ack)
            
            return True
            
        except Exception as e:
            print(f"Handshake handling failed: {e}")
            return False
    
    async def _receive_loop(self, connection: Connection):
        """
        Receive messages from a connection.
        
        Args:
            connection: Connection to receive from
        """
        while connection.is_open:
            try:
                message = await connection.receive_message()
                if message is None:
                    break
                
                # Handle message
                if self.message_handler:
                    asyncio.create_task(
                        self.message_handler(message, connection.peer_address)
                    )
                
            except Exception as e:
                print(f"Error receiving from {connection.peer_address}: {e}")
                break
    
    async def send_to_peer(self, node_id: str, message: Message) -> bool:
        """
        Send a message to a specific peer.
        
        Args:
            node_id: Target peer's node ID
            message: Message to send
            
        Returns:
            True if sent successfully
        """
        connection = self.connections.get(node_id)
        if not connection or not connection.is_open:
            return False
        
        try:
            # Sign message
            message.signature = self.identity.sign(message.get_signable_data())
            await connection.send_message(message)
            return True
        except Exception as e:
            print(f"Failed to send to {node_id}: {e}")
            return False
    
    async def broadcast_to_peers(self, message: Message, peer_ids: Optional[list] = None):
        """
        Broadcast a message to multiple peers.
        
        Args:
            message: Message to broadcast
            peer_ids: List of peer IDs to send to (None = all peers)
        """
        # Sign message once
        message.signature = self.identity.sign(message.get_signable_data())
        
        targets = peer_ids if peer_ids else list(self.connections.keys())
        
        send_tasks = [
            self.send_to_peer(peer_id, message)
            for peer_id in targets
        ]
        
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)
    
    def _parse_address(self, address: str) -> Tuple[str, int]:
        """Parse address string into host and port."""
        if ":" in address:
            host, port_str = address.rsplit(":", 1)
            return host, int(port_str)
        return address, 8888
    
    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.connections)
    
    def is_connected_to(self, node_id: str) -> bool:
        """Check if connected to a specific peer."""
        return node_id in self.connections and self.connections[node_id].is_open
