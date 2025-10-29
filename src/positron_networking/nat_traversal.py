"""
STUN (Session Traversal Utilities for NAT) client implementation.

Provides NAT discovery and public endpoint detection for P2P networking.
Implements RFC 5389 (STUN) and RFC 5780 (NAT Behavior Discovery).
"""
import asyncio
import socket
import struct
import secrets
import hashlib
from typing import Optional, Tuple, Dict
from enum import IntEnum
from dataclasses import dataclass
import structlog


class STUNMessageType(IntEnum):
    """STUN message types."""
    BINDING_REQUEST = 0x0001
    BINDING_RESPONSE = 0x0101
    BINDING_ERROR_RESPONSE = 0x0111


class STUNAttributeType(IntEnum):
    """STUN attribute types."""
    MAPPED_ADDRESS = 0x0001
    XOR_MAPPED_ADDRESS = 0x0020
    CHANGED_ADDRESS = 0x0005
    CHANGE_REQUEST = 0x0003
    SOURCE_ADDRESS = 0x0004
    OTHER_ADDRESS = 0x802C


class NATType(IntEnum):
    """NAT type classifications."""
    UNKNOWN = 0
    OPEN_INTERNET = 1          # No NAT
    FULL_CONE = 2              # Any external host can send
    RESTRICTED_CONE = 3        # Only hosts we've sent to can reply
    PORT_RESTRICTED_CONE = 4   # Only specific host:port can reply
    SYMMETRIC = 5              # Different mapping per destination
    BLOCKED = 6                # STUN failed


@dataclass
class STUNResponse:
    """Response from a STUN server."""
    mapped_address: Optional[Tuple[str, int]] = None
    xor_mapped_address: Optional[Tuple[str, int]] = None
    changed_address: Optional[Tuple[str, int]] = None
    source_address: Optional[Tuple[str, int]] = None
    other_address: Optional[Tuple[str, int]] = None
    
    @property
    def public_endpoint(self) -> Optional[Tuple[str, int]]:
        """Get the public endpoint (prefer XOR-MAPPED-ADDRESS)."""
        return self.xor_mapped_address or self.mapped_address


class STUNClient:
    """
    STUN client for NAT discovery and endpoint detection.
    
    Uses STUN protocol to discover:
    - Public IP address
    - Public port
    - NAT type
    - NAT binding behavior
    """
    
    # Default public STUN servers
    DEFAULT_STUN_SERVERS = [
        ("stun.l.google.com", 19302),
        ("stun1.l.google.com", 19302),
        ("stun2.l.google.com", 19302),
        ("stun.stunprotocol.org", 3478),
    ]
    
    MAGIC_COOKIE = 0x2112A442
    
    def __init__(self, stun_servers: Optional[list] = None, timeout: float = 5.0):
        """
        Initialize STUN client.
        
        Args:
            stun_servers: List of (host, port) tuples for STUN servers
            timeout: Timeout for STUN requests in seconds
        """
        self.stun_servers = stun_servers or self.DEFAULT_STUN_SERVERS
        self.timeout = timeout
        self.logger = structlog.get_logger()
        self._sock: Optional[socket.socket] = None
    
    def _create_binding_request(
        self,
        transaction_id: Optional[bytes] = None,
        change_ip: bool = False,
        change_port: bool = False
    ) -> bytes:
        """
        Create a STUN binding request.
        
        Args:
            transaction_id: 12-byte transaction ID (generated if None)
            change_ip: Request server to respond from different IP
            change_port: Request server to respond from different port
            
        Returns:
            STUN message as bytes
        """
        if transaction_id is None:
            transaction_id = secrets.token_bytes(12)
        
        # Message header: Type (2), Length (2), Magic Cookie (4), Transaction ID (12)
        message = struct.pack(
            "!HHI",
            STUNMessageType.BINDING_REQUEST,
            0,  # Length (updated later)
            self.MAGIC_COOKIE
        )
        message += transaction_id
        
        attributes = b""
        
        # Add CHANGE-REQUEST attribute if requested
        if change_ip or change_port:
            change_flags = 0
            if change_ip:
                change_flags |= 0x04
            if change_port:
                change_flags |= 0x02
            
            attr = struct.pack("!HHI", STUNAttributeType.CHANGE_REQUEST, 4, change_flags)
            attributes += attr
        
        # Update length in header
        message = struct.pack(
            "!HHI",
            STUNMessageType.BINDING_REQUEST,
            len(attributes),
            self.MAGIC_COOKIE
        ) + transaction_id + attributes
        
        return message
    
    def _parse_stun_response(self, data: bytes) -> Optional[STUNResponse]:
        """
        Parse STUN response message.
        
        Args:
            data: Raw STUN message
            
        Returns:
            Parsed STUNResponse or None if invalid
        """
        if len(data) < 20:
            return None
        
        # Parse header
        msg_type, msg_length, magic_cookie = struct.unpack("!HHI", data[:8])
        transaction_id = data[8:20]
        
        if magic_cookie != self.MAGIC_COOKIE:
            return None
        
        if msg_type != STUNMessageType.BINDING_RESPONSE:
            return None
        
        response = STUNResponse()
        
        # Parse attributes
        pos = 20
        while pos < len(data):
            if pos + 4 > len(data):
                break
            
            attr_type, attr_length = struct.unpack("!HH", data[pos:pos+4])
            pos += 4
            
            if pos + attr_length > len(data):
                break
            
            attr_data = data[pos:pos+attr_length]
            pos += attr_length
            
            # Padding to 4-byte boundary
            if attr_length % 4 != 0:
                pos += 4 - (attr_length % 4)
            
            # Parse specific attributes
            if attr_type == STUNAttributeType.MAPPED_ADDRESS:
                response.mapped_address = self._parse_address(attr_data)
            elif attr_type == STUNAttributeType.XOR_MAPPED_ADDRESS:
                response.xor_mapped_address = self._parse_xor_address(attr_data, transaction_id)
            elif attr_type == STUNAttributeType.CHANGED_ADDRESS:
                response.changed_address = self._parse_address(attr_data)
            elif attr_type == STUNAttributeType.SOURCE_ADDRESS:
                response.source_address = self._parse_address(attr_data)
            elif attr_type == STUNAttributeType.OTHER_ADDRESS:
                response.other_address = self._parse_address(attr_data)
        
        return response
    
    def _parse_address(self, data: bytes) -> Optional[Tuple[str, int]]:
        """Parse MAPPED-ADDRESS attribute."""
        if len(data) < 8:
            return None
        
        _, family, port = struct.unpack("!BBH", data[:4])
        
        if family == 1:  # IPv4
            ip = socket.inet_ntop(socket.AF_INET, data[4:8])
            return (ip, port)
        elif family == 2:  # IPv6
            if len(data) < 20:
                return None
            ip = socket.inet_ntop(socket.AF_INET6, data[4:20])
            return (ip, port)
        
        return None
    
    def _parse_xor_address(self, data: bytes, transaction_id: bytes) -> Optional[Tuple[str, int]]:
        """Parse XOR-MAPPED-ADDRESS attribute."""
        if len(data) < 8:
            return None
        
        _, family, xor_port = struct.unpack("!BBH", data[:4])
        
        # XOR port with most significant 16 bits of magic cookie
        port = xor_port ^ (self.MAGIC_COOKIE >> 16)
        
        if family == 1:  # IPv4
            xor_ip_bytes = data[4:8]
            # XOR IP with magic cookie
            magic_bytes = struct.pack("!I", self.MAGIC_COOKIE)
            ip_bytes = bytes(a ^ b for a, b in zip(xor_ip_bytes, magic_bytes))
            ip = socket.inet_ntop(socket.AF_INET, ip_bytes)
            return (ip, port)
        elif family == 2:  # IPv6
            if len(data) < 20:
                return None
            xor_ip_bytes = data[4:20]
            # XOR IP with magic cookie + transaction ID
            xor_key = struct.pack("!I", self.MAGIC_COOKIE) + transaction_id
            ip_bytes = bytes(a ^ b for a, b in zip(xor_ip_bytes, xor_key))
            ip = socket.inet_ntop(socket.AF_INET6, ip_bytes)
            return (ip, port)
        
        return None
    
    async def discover_public_endpoint(
        self,
        local_port: int = 0
    ) -> Optional[Tuple[str, int]]:
        """
        Discover public IP address and port using async UDP.
        
        Args:
            local_port: Local port to bind (0 for random)
            
        Returns:
            (public_ip, public_port) tuple or None if discovery failed
        """
        loop = asyncio.get_event_loop()
        
        for server_host, server_port in self.stun_servers:
            sock = None
            try:
                # Create async UDP socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setblocking(False)
                
                if local_port:
                    sock.bind(("0.0.0.0", local_port))
                
                # Create binding request
                request = self._create_binding_request()
                
                # Resolve server address asynchronously
                try:
                    addr_info = await asyncio.wait_for(
                        loop.getaddrinfo(server_host, server_port, socket.AF_INET, socket.SOCK_DGRAM),
                        timeout=self.timeout
                    )
                    server_addr = (addr_info[0][4][0], addr_info[0][4][1])
                except asyncio.TimeoutError:
                    self.logger.debug("dns_resolution_timeout", server=server_host)
                    continue
                
                # Send request asynchronously
                await loop.sock_sendto(sock, request, server_addr)
                
                # Receive response with timeout
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 2048),
                        timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    self.logger.debug("stun_response_timeout", server=f"{server_host}:{server_port}")
                    continue
                
                # Parse response
                response = self._parse_stun_response(data)
                if response and response.public_endpoint:
                    self.logger.info(
                        "stun_discovery_success",
                        server=f"{server_host}:{server_port}",
                        endpoint=response.public_endpoint
                    )
                    return response.public_endpoint
                
            except Exception as e:
                self.logger.debug(
                    "stun_server_failed",
                    server=f"{server_host}:{server_port}",
                    error=str(e)
                )
            finally:
                if sock:
                    sock.close()
        
        self.logger.warning("stun_discovery_failed", servers_tried=len(self.stun_servers))
        return None
    
    async def detect_nat_type(self, local_port: int = 0) -> NATType:
        """
        Detect NAT type using STUN tests (RFC 5780 algorithm).
        
        Performs multiple STUN tests to determine NAT behavior:
        1. Test if behind NAT (public vs local address)
        2. Test mapping consistency (same public port for different destinations)
        3. Test filtering behavior (can external hosts reach us)
        
        Args:
            local_port: Local port to bind
            
        Returns:
            Detected NAT type
        """
        loop = asyncio.get_event_loop()
        sock = None
        
        try:
            # Test 1: Get initial public endpoint
            endpoint1 = await self.discover_public_endpoint(local_port)
            if not endpoint1:
                return NATType.BLOCKED
            
            # Get local address
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if local_port:
                sock.bind(("0.0.0.0", local_port))
            else:
                sock.bind(("0.0.0.0", 0))
            
            local_addr = sock.getsockname()
            
            # Get our actual external IP for comparison
            try:
                # Connect to a public server to determine our outgoing IP
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_sock.setblocking(False)
                await loop.sock_connect(test_sock, ("8.8.8.8", 80))
                actual_local_ip = test_sock.getsockname()[0]
                test_sock.close()
            except:
                actual_local_ip = local_addr[0]
            
            # If public endpoint matches our actual IP and port, no NAT
            if endpoint1[0] == actual_local_ip:
                sock.close()
                return NATType.OPEN_INTERNET
            
            # Test 2: Check mapping consistency across different STUN servers
            # Use first two different STUN servers
            endpoints_from_different_servers = []
            tested_servers = set()
            
            for server_host, server_port in self.stun_servers[:3]:  # Test with 3 servers
                server_key = f"{server_host}:{server_port}"
                if server_key in tested_servers:
                    continue
                tested_servers.add(server_key)
                
                try:
                    # Resolve server
                    addr_info = await asyncio.wait_for(
                        loop.getaddrinfo(server_host, server_port, socket.AF_INET, socket.SOCK_DGRAM),
                        timeout=self.timeout
                    )
                    server_addr = (addr_info[0][4][0], addr_info[0][4][1])
                    
                    # Send binding request
                    request = self._create_binding_request()
                    await loop.sock_sendto(sock, request, server_addr)
                    
                    # Receive response
                    data, _ = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 2048),
                        timeout=self.timeout
                    )
                    
                    response = self._parse_stun_response(data)
                    if response and response.public_endpoint:
                        endpoints_from_different_servers.append(response.public_endpoint)
                
                except (asyncio.TimeoutError, Exception) as e:
                    self.logger.debug("nat_detection_test_failed", server=server_host, error=str(e))
                    continue
            
            sock.close()
            
            # Analyze results
            if len(endpoints_from_different_servers) >= 2:
                # Check if all endpoints have the same port
                ports = [ep[1] for ep in endpoints_from_different_servers]
                
                if len(set(ports)) == 1:
                    # Same port mapping = Cone NAT (Full or Restricted)
                    # We can't easily distinguish between Full/Restricted/Port-Restricted
                    # without more complex server support, so we'll call it Full Cone
                    return NATType.FULL_CONE
                else:
                    # Different ports for different destinations = Symmetric NAT
                    return NATType.SYMMETRIC
            
            # If we only got one endpoint, assume Full Cone (safest assumption)
            return NATType.FULL_CONE
            
        except Exception as e:
            self.logger.error("nat_detection_error", error=str(e))
            if sock:
                sock.close()
            return NATType.UNKNOWN
            
        except Exception as e:
            self.logger.error("nat_detection_error", error=str(e))
            return NATType.UNKNOWN
    
    async def get_nat_info(self) -> Dict:
        """
        Get comprehensive NAT information.
        
        Returns:
            Dictionary with NAT information
        """
        public_endpoint = await self.discover_public_endpoint()
        nat_type = await self.detect_nat_type()
        
        # Get local IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "127.0.0.1"
        
        return {
            "local_ip": local_ip,
            "public_endpoint": public_endpoint,
            "nat_type": nat_type.name,
            "behind_nat": public_endpoint is not None and public_endpoint[0] != local_ip
        }


@dataclass
class ConnectionCandidate:
    """
    Represents a connection candidate for NAT traversal.
    
    Similar to ICE candidates in WebRTC.
    """
    candidate_type: str  # "host", "srflx" (server reflexive), "relay"
    ip: str
    port: int
    priority: int
    foundation: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "type": self.candidate_type,
            "ip": self.ip,
            "port": self.port,
            "priority": self.priority,
            "foundation": self.foundation,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ConnectionCandidate':
        """Create from dictionary."""
        return cls(
            candidate_type=data["type"],
            ip=data["ip"],
            port=data["port"],
            priority=data["priority"],
            foundation=data.get("foundation", ""),
        )


class HolePuncher:
    """
    Implements UDP hole punching for NAT traversal.
    
    Uses simultaneous open technique to create bidirectional NAT bindings.
    """
    
    def __init__(self, stun_client: Optional[STUNClient] = None):
        """
        Initialize hole puncher.
        
        Args:
            stun_client: STUN client for endpoint discovery
        """
        self.stun_client = stun_client or STUNClient()
        self.logger = structlog.get_logger()
        self._active_punches: Dict[str, asyncio.Task] = {}
    
    async def gather_candidates(self, local_port: int = 0) -> list[ConnectionCandidate]:
        """
        Gather connection candidates for this node.
        
        Args:
            local_port: Local port to use
            
        Returns:
            List of connection candidates
        """
        candidates = []
        
        # Get local addresses
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            # Host candidate (local network)
            candidates.append(ConnectionCandidate(
                candidate_type="host",
                ip=local_ip,
                port=local_port or 0,
                priority=1000,
                foundation=hashlib.md5(f"host-{local_ip}".encode()).hexdigest()[:8]
            ))
        except Exception as e:
            self.logger.debug("failed_to_get_local_ip", error=str(e))
        
        # Get server reflexive address (public endpoint)
        try:
            public_endpoint = await self.stun_client.discover_public_endpoint(local_port)
            if public_endpoint:
                candidates.append(ConnectionCandidate(
                    candidate_type="srflx",
                    ip=public_endpoint[0],
                    port=public_endpoint[1],
                    priority=500,
                    foundation=hashlib.md5(f"srflx-{public_endpoint[0]}".encode()).hexdigest()[:8]
                ))
        except Exception as e:
            self.logger.debug("failed_to_get_public_endpoint", error=str(e))
        
        return candidates
    
    async def punch_hole(
        self,
        local_port: int,
        remote_candidates: list[ConnectionCandidate],
        punch_id: str,
        timeout: float = 10.0,
        max_retries: int = 30
    ) -> Optional[Tuple[str, int]]:
        """
        Attempt UDP hole punching with simultaneous open technique.
        
        This implements the standard UDP hole punching algorithm:
        1. Both peers send packets to each other's public endpoints
        2. These packets create NAT bindings
        3. Subsequent packets can traverse the NAT
        
        Args:
            local_port: Local port to use
            remote_candidates: Remote peer's connection candidates (sorted by priority)
            punch_id: Unique identifier for this punch attempt
            timeout: Total timeout in seconds
            max_retries: Maximum number of punch attempts per candidate
            
        Returns:
            (ip, port) of successful connection or None
        """
        self.logger.info(
            "starting_hole_punch",
            punch_id=punch_id,
            local_port=local_port,
            remote_candidates=len(remote_candidates)
        )
        
        loop = asyncio.get_event_loop()
        
        # Create UDP socket with proper options for hole punching
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # On some systems, SO_REUSEPORT helps with simultaneous binding
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass  # Not all systems support SO_REUSEPORT
        
        sock.bind(("0.0.0.0", local_port))
        sock.setblocking(False)
        
        # Punch messages (simple protocol)
        punch_message = f"PUNCH:{punch_id}".encode()
        ack_message = f"PUNCH_ACK:{punch_id}".encode()
        confirm_message = f"PUNCH_CONFIRM:{punch_id}".encode()
        
        # Sort candidates by priority (highest first)
        sorted_candidates = sorted(remote_candidates, key=lambda c: c.priority, reverse=True)
        
        start_time = loop.time()
        retry_count = 0
        last_send_time = 0
        send_interval = 0.2  # Send every 200ms
        
        # Track which candidates we've tried
        candidate_attempts = {i: 0 for i in range(len(sorted_candidates))}
        successful_candidate = None
        
        try:
            while loop.time() - start_time < timeout and retry_count < max_retries:
                current_time = loop.time()
                
                # Send punch packets periodically
                if current_time - last_send_time >= send_interval:
                    for idx, candidate in enumerate(sorted_candidates):
                        if candidate_attempts[idx] < max_retries // len(sorted_candidates) or len(sorted_candidates) == 1:
                            try:
                                await loop.sock_sendto(sock, punch_message, (candidate.ip, candidate.port))
                                candidate_attempts[idx] += 1
                                
                                self.logger.debug(
                                    "punch_packet_sent",
                                    candidate=f"{candidate.ip}:{candidate.port}",
                                    attempt=candidate_attempts[idx]
                                )
                            except Exception as e:
                                self.logger.debug(
                                    "punch_send_failed",
                                    candidate=f"{candidate.ip}:{candidate.port}",
                                    error=str(e)
                                )
                    
                    last_send_time = current_time
                    retry_count += 1
                
                # Try to receive response (non-blocking with short timeout)
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 1024),
                        timeout=0.05  # Short timeout to check frequently
                    )
                    
                    # Check if it's a valid punch message
                    if data.startswith(b"PUNCH:") and punch_id.encode() in data:
                        # Received punch request from peer
                        self.logger.info(
                            "received_punch_request",
                            punch_id=punch_id,
                            remote_addr=addr
                        )
                        
                        # Send multiple ACKs to ensure receipt
                        for _ in range(3):
                            await loop.sock_sendto(sock, ack_message, addr)
                            await asyncio.sleep(0.05)
                        
                        successful_candidate = addr
                        
                    elif data.startswith(b"PUNCH_ACK:") and punch_id.encode() in data:
                        # Received ACK from peer - connection established!
                        self.logger.info(
                            "received_punch_ack",
                            punch_id=punch_id,
                            remote_addr=addr
                        )
                        
                        # Send confirmation
                        await loop.sock_sendto(sock, confirm_message, addr)
                        
                        # Verify connection with a few more packets
                        for _ in range(3):
                            await loop.sock_sendto(sock, confirm_message, addr)
                            await asyncio.sleep(0.05)
                        
                        self.logger.info(
                            "hole_punch_successful",
                            punch_id=punch_id,
                            remote_addr=addr,
                            attempts=retry_count
                        )
                        
                        return addr
                    
                    elif data.startswith(b"PUNCH_CONFIRM:") and punch_id.encode() in data:
                        # Received confirmation - we're good!
                        if successful_candidate:
                            self.logger.info(
                                "hole_punch_confirmed",
                                punch_id=punch_id,
                                remote_addr=addr
                            )
                            return successful_candidate
                
                except asyncio.TimeoutError:
                    # No data received, continue trying
                    continue
                except Exception as e:
                    self.logger.debug("punch_receive_error", error=str(e))
                
                # Small delay before next iteration
                await asyncio.sleep(0.02)
        
        finally:
            sock.close()
        
        self.logger.warning(
            "hole_punch_failed",
            punch_id=punch_id,
            total_attempts=retry_count,
            duration=loop.time() - start_time
        )
        return None
    
    async def maintain_binding(
        self,
        sock: socket.socket,
        remote_addr: Tuple[str, int],
        interval: float = 25.0,
        timeout: float = 5.0
    ):
        """
        Maintain NAT binding with bidirectional keep-alive packets.
        
        Sends periodic packets to keep the NAT port mapping alive.
        Most NATs have timeouts between 30-120 seconds, so 25s is safe.
        
        Args:
            sock: Socket to use for keep-alive (must be non-blocking)
            remote_addr: Remote address to send to
            interval: Keep-alive interval in seconds (default 25s)
            timeout: Timeout for expecting response
        """
        loop = asyncio.get_event_loop()
        keep_alive_message = b"KEEP_ALIVE"
        keep_alive_ack = b"KEEP_ALIVE_ACK"
        
        consecutive_failures = 0
        max_failures = 3
        
        self.logger.info(
            "nat_keepalive_started",
            remote_addr=remote_addr,
            interval=interval
        )
        
        while True:
            try:
                send_time = loop.time()
                
                # Send keep-alive packet
                await loop.sock_sendto(sock, keep_alive_message, remote_addr)
                
                # Wait for optional ACK (non-critical if not received)
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 64),
                        timeout=timeout
                    )
                    
                    if data == keep_alive_message:
                        # Peer sent keep-alive, send ACK
                        await loop.sock_sendto(sock, keep_alive_ack, addr)
                    elif data == keep_alive_ack:
                        # Received ACK, connection is healthy
                        consecutive_failures = 0
                    
                except asyncio.TimeoutError:
                    # No response, but this is not critical
                    consecutive_failures += 1
                    
                    if consecutive_failures >= max_failures:
                        self.logger.warning(
                            "nat_keepalive_no_response",
                            remote_addr=remote_addr,
                            failures=consecutive_failures
                        )
                        # Reset counter but continue
                        consecutive_failures = 0
                
                self.logger.debug(
                    "nat_keepalive_sent",
                    remote_addr=remote_addr,
                    next_in=interval
                )
                
                # Wait for next interval
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                self.logger.info(
                    "nat_keepalive_cancelled",
                    remote_addr=remote_addr
                )
                break
            except Exception as e:
                self.logger.error(
                    "nat_keepalive_error",
                    remote_addr=remote_addr,
                    error=str(e)
                )
                # Wait a bit before retrying
                await asyncio.sleep(5.0)
                await asyncio.sleep(interval)


class NATTraversalManager:
    """
    High-level NAT traversal manager.
    
    Coordinates STUN discovery, hole punching, and connection management.
    """
    
    def __init__(
        self,
        local_port: int = 0,
        stun_servers: Optional[list] = None,
        enable_keepalive: bool = True,
        keepalive_interval: float = 25.0
    ):
        """
        Initialize NAT traversal manager.
        
        Args:
            local_port: Local port to use
            stun_servers: List of STUN servers
            enable_keepalive: Enable NAT binding keep-alive
            keepalive_interval: Keep-alive interval in seconds
        """
        self.local_port = local_port
        self.stun_client = STUNClient(stun_servers)
        self.hole_puncher = HolePuncher(self.stun_client)
        self.enable_keepalive = enable_keepalive
        self.keepalive_interval = keepalive_interval
        self.logger = structlog.get_logger()
        
        self._nat_info: Optional[Dict] = None
        self._candidates: Optional[list[ConnectionCandidate]] = None
        self._keepalive_tasks: Dict[str, asyncio.Task] = {}
    
    async def initialize(self):
        """Initialize NAT traversal (discover NAT info)."""
        self.logger.info("initializing_nat_traversal")
        
        # Discover NAT information
        self._nat_info = await self.stun_client.get_nat_info()
        self.logger.info("nat_info_discovered", **self._nat_info)
        
        # Gather connection candidates
        self._candidates = await self.hole_puncher.gather_candidates(self.local_port)
        self.logger.info("candidates_gathered", count=len(self._candidates))
    
    async def get_candidates(self) -> list[ConnectionCandidate]:
        """Get connection candidates for this node."""
        if self._candidates is None:
            await self.initialize()
        return self._candidates or []
    
    async def connect_to_peer(
        self,
        peer_id: str,
        remote_candidates: list[ConnectionCandidate],
        local_port: int = 0
    ) -> Optional[Tuple[str, int]]:
        """
        Establish connection to a peer through NAT.
        
        Args:
            peer_id: Peer identifier
            remote_candidates: Peer's connection candidates
            local_port: Local port to use
            
        Returns:
            Connected endpoint or None
        """
        # Attempt hole punching
        port = local_port or self.local_port
        endpoint = await self.hole_puncher.punch_hole(
            local_port=port,
            remote_candidates=remote_candidates,
            punch_id=f"{peer_id}_{int(asyncio.get_event_loop().time())}"
        )
        
        if endpoint and self.enable_keepalive:
            # Start keep-alive task
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", port))
            
            task = asyncio.create_task(
                self.hole_puncher.maintain_binding(
                    sock, endpoint, self.keepalive_interval
                )
            )
            self._keepalive_tasks[peer_id] = task
        
        return endpoint
    
    def get_nat_info(self) -> Optional[Dict]:
        """Get NAT information."""
        return self._nat_info
    
    def is_behind_nat(self) -> bool:
        """Check if this node is behind NAT."""
        if self._nat_info:
            return self._nat_info.get("behind_nat", False)
        return False
    
    async def stop(self):
        """Stop NAT traversal manager and clean up."""
        # Cancel all keep-alive tasks
        for task in self._keepalive_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._keepalive_tasks.clear()
        self.logger.info("nat_traversal_stopped")
