"""
Example: Basic network node with custom message handling.
"""
import asyncio
from positron_networking import Node, NetworkConfig


async def handle_chat_message(sender_id: str, data: dict):
    """Handle incoming chat messages."""
    if "message" in data:
        print(f"\n[{sender_id[:8]}]: {data['message']}")


async def main():
    """Run a simple chat node."""
    # Configuration
    config = NetworkConfig(
        host="0.0.0.0",
        port=8888,
        bootstrap_nodes=[],  # Add bootstrap nodes here
        log_level="INFO"
    )
    
    # Create and start node
    node = Node(config)
    node.register_data_handler("chat", handle_chat_message)
    
    await node.start()
    
    print(f"\nNode started: {node.node_id}")
    print(f"Address: {node.address}")
    print("\nType messages to broadcast (or 'quit' to exit):")
    
    try:
        # Simple input loop (in production, use proper async input)
        while True:
            await asyncio.sleep(1)
            
            # In a real application, you'd use aioconsole or similar
            # for proper async input handling
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        await node.stop()


if __name__ == "__main__":
    asyncio.run(main())
