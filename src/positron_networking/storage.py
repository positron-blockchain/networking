"""
Persistent storage for network state, peers, and trust data.
"""
import aiosqlite
import json
from typing import List, Optional, Dict, Any
from positron_networking.protocol import PeerInfo
import time


class Storage:
    """Handles persistent storage of network state."""
    
    def __init__(self, db_path: str):
        """
        Initialize storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        """Initialize database and create tables."""
        self.db = await aiosqlite.connect(self.db_path)
        await self._create_tables()
    
    async def close(self):
        """Close database connection."""
        if self.db:
            await self.db.close()
    
    async def _create_tables(self):
        """Create database tables if they don't exist."""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS peers (
                node_id TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                public_key BLOB NOT NULL,
                last_seen REAL NOT NULL,
                trust_score REAL NOT NULL,
                first_seen REAL NOT NULL,
                connection_count INTEGER DEFAULT 0,
                valid_messages INTEGER DEFAULT 0,
                invalid_messages INTEGER DEFAULT 0
            )
        """)
        
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS messages_seen (
                message_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                sender_id TEXT NOT NULL
            )
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
            ON messages_seen(timestamp)
        """)
        
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS trust_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                trust_delta REAL NOT NULL,
                timestamp REAL NOT NULL,
                reason TEXT
            )
        """)
        
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS network_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        
        await self.db.commit()
    
    async def save_peer(self, peer: PeerInfo):
        """Save or update peer information."""
        async with self.db.execute(
            "SELECT first_seen FROM peers WHERE node_id = ?",
            (peer.node_id,)
        ) as cursor:
            row = await cursor.fetchone()
            first_seen = row[0] if row else time.time()
        
        await self.db.execute("""
            INSERT OR REPLACE INTO peers 
            (node_id, address, public_key, last_seen, trust_score, first_seen)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            peer.node_id,
            peer.address,
            peer.public_key,
            peer.last_seen,
            peer.trust_score,
            first_seen
        ))
        await self.db.commit()
    
    async def get_peer(self, node_id: str) -> Optional[PeerInfo]:
        """Get peer information by node ID."""
        async with self.db.execute(
            "SELECT node_id, address, public_key, last_seen, trust_score FROM peers WHERE node_id = ?",
            (node_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return PeerInfo(
                    node_id=row[0],
                    address=row[1],
                    public_key=row[2],
                    last_seen=row[3],
                    trust_score=row[4]
                )
        return None
    
    async def get_all_peers(self) -> List[PeerInfo]:
        """Get all stored peers."""
        peers = []
        async with self.db.execute(
            "SELECT node_id, address, public_key, last_seen, trust_score FROM peers"
        ) as cursor:
            async for row in cursor:
                peers.append(PeerInfo(
                    node_id=row[0],
                    address=row[1],
                    public_key=row[2],
                    last_seen=row[3],
                    trust_score=row[4]
                ))
        return peers
    
    async def get_trusted_peers(self, min_trust: float = 0.7) -> List[PeerInfo]:
        """Get peers with trust score above threshold."""
        peers = []
        async with self.db.execute(
            "SELECT node_id, address, public_key, last_seen, trust_score FROM peers WHERE trust_score >= ? ORDER BY trust_score DESC",
            (min_trust,)
        ) as cursor:
            async for row in cursor:
                peers.append(PeerInfo(
                    node_id=row[0],
                    address=row[1],
                    public_key=row[2],
                    last_seen=row[3],
                    trust_score=row[4]
                ))
        return peers
    
    async def update_peer_trust(self, node_id: str, trust_score: float):
        """Update peer's trust score."""
        await self.db.execute(
            "UPDATE peers SET trust_score = ? WHERE node_id = ?",
            (trust_score, node_id)
        )
        await self.db.commit()
    
    async def remove_peer(self, node_id: str):
        """Remove peer from storage."""
        await self.db.execute("DELETE FROM peers WHERE node_id = ?", (node_id,))
        await self.db.commit()
    
    async def increment_peer_stats(
        self,
        node_id: str,
        valid_messages: int = 0,
        invalid_messages: int = 0
    ):
        """Increment peer statistics."""
        await self.db.execute("""
            UPDATE peers 
            SET valid_messages = valid_messages + ?,
                invalid_messages = invalid_messages + ?
            WHERE node_id = ?
        """, (valid_messages, invalid_messages, node_id))
        await self.db.commit()
    
    async def has_seen_message(self, message_id: str) -> bool:
        """Check if a message has been seen before."""
        async with self.db.execute(
            "SELECT 1 FROM messages_seen WHERE message_id = ?",
            (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None
    
    async def mark_message_seen(self, message_id: str, sender_id: str):
        """Mark a message as seen."""
        await self.db.execute(
            "INSERT OR IGNORE INTO messages_seen (message_id, timestamp, sender_id) VALUES (?, ?, ?)",
            (message_id, time.time(), sender_id)
        )
        await self.db.commit()
    
    async def cleanup_old_messages(self, max_age: float = 3600):
        """Remove old message records to prevent database growth."""
        cutoff = time.time() - max_age
        await self.db.execute(
            "DELETE FROM messages_seen WHERE timestamp < ?",
            (cutoff,)
        )
        await self.db.commit()
    
    async def log_trust_event(
        self,
        node_id: str,
        event_type: str,
        trust_delta: float,
        reason: str = ""
    ):
        """Log a trust-related event."""
        await self.db.execute("""
            INSERT INTO trust_events (node_id, event_type, trust_delta, timestamp, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (node_id, event_type, trust_delta, time.time(), reason))
        await self.db.commit()
    
    async def get_trust_history(self, node_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get trust event history for a node."""
        events = []
        async with self.db.execute("""
            SELECT event_type, trust_delta, timestamp, reason
            FROM trust_events
            WHERE node_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (node_id, limit)) as cursor:
            async for row in cursor:
                events.append({
                    "event_type": row[0],
                    "trust_delta": row[1],
                    "timestamp": row[2],
                    "reason": row[3]
                })
        return events
    
    async def set_state(self, key: str, value: Any):
        """Store arbitrary state data."""
        await self.db.execute("""
            INSERT OR REPLACE INTO network_state (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, json.dumps(value), time.time()))
        await self.db.commit()
    
    async def get_state(self, key: str) -> Optional[Any]:
        """Retrieve state data."""
        async with self.db.execute(
            "SELECT value FROM network_state WHERE key = ?",
            (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
        return None
