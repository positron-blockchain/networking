"""
Example: Data sharing application using the decentralized network.
"""
import asyncio
import json
import hashlib
from typing import Dict, Set
from positron_networking import Node, NetworkConfig


class DataSharingApp:
    """Simple data sharing application."""
    
    def __init__(self, node: Node):
        self.node = node
        self.stored_data: Dict[str, dict] = {}
        self.data_hashes: Set[str] = set()
        
        # Register handlers
        node.register_data_handler("data_store", self.handle_store_request)
        node.register_data_handler("data_query", self.handle_query_request)
        node.register_data_handler("data_response", self.handle_data_response)
    
    async def handle_store_request(self, sender_id: str, data: dict):
        """Handle data storage request."""
        if "key" in data and "value" in data:
            key = data["key"]
            value = data["value"]
            
            # Store the data
            self.stored_data[key] = {
                "value": value,
                "stored_by": sender_id,
                "timestamp": data.get("timestamp")
            }
            
            # Calculate and store hash
            data_hash = hashlib.sha256(
                json.dumps(value, sort_keys=True).encode()
            ).hexdigest()
            self.data_hashes.add(data_hash)
            
            print(f"Stored data: {key} (from {sender_id[:8]})")
    
    async def handle_query_request(self, sender_id: str, data: dict):
        """Handle data query request."""
        if "key" in data:
            key = data["key"]
            
            if key in self.stored_data:
                # Send response back
                response = {
                    "key": key,
                    "value": self.stored_data[key]["value"],
                    "found": True
                }
                await self.node.send_to_peer(sender_id, response)
                print(f"Responded to query for {key} from {sender_id[:8]}")
    
    async def handle_data_response(self, sender_id: str, data: dict):
        """Handle data query response."""
        if data.get("found"):
            print(f"\nReceived data from {sender_id[:8]}:")
            print(f"  Key: {data['key']}")
            print(f"  Value: {data['value']}")
    
    async def store(self, key: str, value: dict):
        """Store data in the network."""
        data = {
            "key": key,
            "value": value,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Broadcast to network
        await self.node.broadcast({"type": "store", "data": data})
        
        # Also store locally
        await self.handle_store_request(self.node.node_id, data)
    
    async def query(self, key: str):
        """Query data from the network."""
        data = {"key": key}
        
        # Broadcast query to network
        await self.node.broadcast({"type": "query", "data": data})
        print(f"Querying network for: {key}")


async def main():
    """Run the data sharing application."""
    config = NetworkConfig(
        host="0.0.0.0",
        port=8888,
        bootstrap_nodes=[],
        log_level="INFO"
    )
    
    node = Node(config)
    await node.start()
    
    app = DataSharingApp(node)
    
    print(f"\nData Sharing App Started")
    print(f"Node ID: {node.node_id}")
    print(f"Address: {node.address}")
    print("\nCommands:")
    print("  store <key> <value>  - Store data")
    print("  query <key>          - Query data")
    print("  stats                - Show statistics")
    print("  quit                 - Exit")
    
    try:
        # Demo: Store some sample data
        await asyncio.sleep(2)
        await app.store("test_key", {"message": "Hello, network!"})
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        await node.stop()


if __name__ == "__main__":
    asyncio.run(main())
