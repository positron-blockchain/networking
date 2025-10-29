"""
Command-line interface for the Positron Networking node.
"""
import asyncio
import click
import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
import signal
import sys

from positron_networking.node import Node
from positron_networking.config import NetworkConfig


console = Console()


@click.group()
def main():
    """Positron Networking - Production-ready decentralized P2P networking layer."""
    pass


@main.command()
@click.option("--config", "-c", type=click.Path(), help="Path to configuration file")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", type=int, default=8888, help="Port to bind to")
@click.option("--bootstrap", "-b", multiple=True, help="Bootstrap node addresses")
@click.option("--data-dir", "-d", default="node_data", help="Data directory")
@click.option("--log-level", "-l", default="INFO", help="Log level")
def start(config, host, port, bootstrap, data_dir, log_level):
    """Start a decentralized network node."""
    
    # Load or create configuration
    if config and Path(config).exists():
        net_config = NetworkConfig.from_file(config)
        console.print(f"[green]Loaded configuration from {config}[/green]")
    else:
        net_config = NetworkConfig(
            host=host,
            port=port,
            bootstrap_nodes=list(bootstrap),
            data_dir=data_dir,
            log_level=log_level
        )
    
    # Override with CLI arguments if provided
    if host != "0.0.0.0":
        net_config.host = host
    if port != 8888:
        net_config.port = port
    if bootstrap:
        net_config.bootstrap_nodes = list(bootstrap)
    
    console.print(Panel.fit(
        f"[bold cyan]Starting Decentralized Network Node[/bold cyan]\n"
        f"Host: {net_config.host}\n"
        f"Port: {net_config.port}\n"
        f"Bootstrap Nodes: {', '.join(net_config.bootstrap_nodes) or 'None'}\n"
        f"Data Directory: {net_config.data_dir}",
        border_style="cyan"
    ))
    
    # Create and run node
    node = Node(net_config)
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        console.print("\n[yellow]Shutting down...[/yellow]")
        asyncio.create_task(node.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run node
    try:
        asyncio.run(_run_node(node))
    except KeyboardInterrupt:
        console.print("[yellow]Node stopped[/yellow]")


async def _run_node(node: Node):
    """Run the node with status display."""
    await node.start()
    
    try:
        # Keep running and display status
        while True:
            await asyncio.sleep(5)
            stats = node.get_stats()
            
            console.print(f"\r[dim]Active Peers: {stats['active_peers']} | "
                         f"Known Peers: {stats['known_peers']} | "
                         f"Connections: {stats['connections']}[/dim]", end="")
    except asyncio.CancelledError:
        await node.stop()


@main.command()
@click.option("--config", "-c", type=click.Path(), help="Path to configuration file")
@click.option("--output", "-o", type=click.Path(), help="Output file for stats")
@click.option("--data-dir", "-d", default="node_data", help="Data directory")
def stats(config, output, data_dir):
    """Display node statistics from storage."""
    
    asyncio.run(_display_stats(config, output, data_dir))


async def _display_stats(config: Optional[str], output: Optional[str], data_dir: str):
    """Fetch and display statistics from node storage."""
    
    # Load configuration to get data directory
    if config and Path(config).exists():
        net_config = NetworkConfig.from_file(config)
    else:
        net_config = NetworkConfig(data_dir=data_dir)
    
    try:
        # Load storage to get persisted stats
        from positron_networking.storage import Storage
        
        storage = Storage(net_config.db_path)
        await storage.initialize()
        
        # Fetch stats from storage
        peers = await storage.get_all_peers()
        
        # Get identity if available
        identity = None
        if Path(net_config.private_key_path).exists():
            from positron_networking.identity import Identity
            identity = Identity.load_or_generate(
                net_config.private_key_path,
                net_config.public_key_path
            )
        
        # Create statistics table
        table = Table(title="Network Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        if identity:
            table.add_row("Node ID", identity.node_id[:16] + "...")
        table.add_row("Data Directory", net_config.data_dir)
        table.add_row("Known Peers", str(len(peers)))
        table.add_row("Database Path", net_config.db_path)
        
        console.print(table)
        
        # Show peer list if available
        if peers:
            peer_table = Table(title="Known Peers")
            peer_table.add_column("Node ID", style="cyan")
            peer_table.add_column("Address", style="blue")
            peer_table.add_column("Trust Score", style="green")
            
            for peer in peers[:10]:  # Show first 10
                peer_table.add_row(
                    peer.node_id[:16] + "...",
                    peer.address,
                    f"{peer.trust_score:.2f}"
                )
            
            if len(peers) > 10:
                console.print(f"\n[dim]Showing 10 of {len(peers)} peers[/dim]")
            
            console.print(peer_table)
        
        await storage.close()
        
        # Save to file if requested
        if output:
            stats_data = {
                "node_id": identity.node_id if identity else None,
                "data_dir": net_config.data_dir,
                "known_peers": len(peers),
                "peers": [
                    {
                        "node_id": p.node_id,
                        "address": p.address,
                        "trust_score": p.trust_score
                    }
                    for p in peers
                ]
            }
            
            with open(output, 'w') as f:
                json.dump(stats_data, f, indent=2)
            
            console.print(f"\n[green]Statistics saved to {output}[/green]")
            
    except Exception as e:
        console.print(f"[red]Error loading statistics: {e}[/red]")
        console.print("[yellow]Note: Stats are loaded from storage. Start a node first to generate data.[/yellow]")


@main.command()
@click.argument("output", type=click.Path())
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", type=int, default=8888, help="Port to bind to")
@click.option("--bootstrap", "-b", multiple=True, help="Bootstrap node addresses")
def generate_config(output, host, port, bootstrap):
    """Generate a configuration file."""
    
    config = NetworkConfig(
        host=host,
        port=port,
        bootstrap_nodes=list(bootstrap)
    )
    
    config.to_file(output)
    console.print(f"[green]Configuration saved to {output}[/green]")


@main.command()
@click.option("--count", "-n", type=int, default=3, help="Number of nodes to start")
@click.option("--base-port", "-p", type=int, default=8888, help="Base port number")
def simulate(count, base_port):
    """Simulate a local network with multiple nodes."""
    
    console.print(Panel.fit(
        f"[bold cyan]Starting Network Simulation[/bold cyan]\n"
        f"Nodes: {count}\n"
        f"Base Port: {base_port}",
        border_style="cyan"
    ))
    
    asyncio.run(_run_simulation(count, base_port))


async def _run_simulation(count: int, base_port: int):
    """Run a simulation with multiple nodes."""
    nodes = []
    
    try:
        # Create first node (bootstrap)
        bootstrap_config = NetworkConfig(
            host="127.0.0.1",
            port=base_port,
            data_dir=f"sim_data/node_0",
            db_path=f"sim_data/node_0/network.db",
            private_key_path=f"sim_data/node_0/keys/private_key.pem",
            public_key_path=f"sim_data/node_0/keys/public_key.pem",
        )
        bootstrap_node = Node(bootstrap_config)
        await bootstrap_node.start()
        nodes.append(bootstrap_node)
        
        console.print(f"[green]Bootstrap node started on port {base_port}[/green]")
        
        # Create remaining nodes
        bootstrap_addr = f"127.0.0.1:{base_port}"
        
        for i in range(1, count):
            port = base_port + i
            config = NetworkConfig(
                host="127.0.0.1",
                port=port,
                bootstrap_nodes=[bootstrap_addr],
                data_dir=f"sim_data/node_{i}",
                db_path=f"sim_data/node_{i}/network.db",
                private_key_path=f"sim_data/node_{i}/keys/private_key.pem",
                public_key_path=f"sim_data/node_{i}/keys/public_key.pem",
            )
            node = Node(config)
            await node.start()
            nodes.append(node)
            
            console.print(f"[green]Node {i} started on port {port}[/green]")
            
            # Small delay between starts
            await asyncio.sleep(1)
        
        console.print(Panel.fit(
            "[bold green]Simulation Running[/bold green]\n"
            "Press Ctrl+C to stop",
            border_style="green"
        ))
        
        # Keep running and display status
        while True:
            await asyncio.sleep(10)
            
            # Display network status
            table = Table(title="Network Status")
            table.add_column("Node", style="cyan")
            table.add_column("Port", style="blue")
            table.add_column("Peers", style="green")
            table.add_column("Messages", style="yellow")
            
            for i, node in enumerate(nodes):
                stats = node.get_stats()
                table.add_row(
                    f"Node {i}",
                    str(base_port + i),
                    str(stats['active_peers']),
                    str(stats['gossip_stats']['messages_received'])
                )
            
            console.clear()
            console.print(table)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping simulation...[/yellow]")
    finally:
        # Stop all nodes
        for node in nodes:
            await node.stop()
        console.print("[green]Simulation stopped[/green]")


@main.command()
def version():
    """Display version information."""
    from . import __version__
    console.print(f"[cyan]Decentralized Network v{__version__}[/cyan]")


if __name__ == "__main__":
    main()
