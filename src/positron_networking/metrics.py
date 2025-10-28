"""
Enhanced metrics collection and monitoring system for the network.

Provides comprehensive metrics tracking for performance monitoring, debugging,
and network health analysis.
"""
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict, deque
import asyncio
import structlog


@dataclass
class MetricPoint:
    """A single metric data point."""
    timestamp: float
    value: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSummary:
    """Summary statistics for a metric."""
    count: int
    sum: float
    min: float
    max: float
    mean: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


class Counter:
    """
    A monotonically increasing counter metric.
    
    Used for tracking counts of events (e.g., messages sent, errors).
    """
    
    def __init__(self, name: str, description: str = ""):
        """
        Initialize counter.
        
        Args:
            name: Metric name
            description: Human-readable description
        """
        self.name = name
        self.description = description
        self.value = 0
        self.created_at = time.time()
    
    def increment(self, amount: float = 1.0):
        """Increment the counter."""
        self.value += amount
    
    def reset(self):
        """Reset the counter to zero."""
        self.value = 0
    
    def get(self) -> float:
        """Get current value."""
        return self.value


class Gauge:
    """
    A gauge metric that can go up and down.
    
    Used for tracking current values (e.g., active connections, memory usage).
    """
    
    def __init__(self, name: str, description: str = ""):
        """
        Initialize gauge.
        
        Args:
            name: Metric name
            description: Human-readable description
        """
        self.name = name
        self.description = description
        self.value = 0.0
        self.created_at = time.time()
    
    def set(self, value: float):
        """Set the gauge to a specific value."""
        self.value = value
    
    def increment(self, amount: float = 1.0):
        """Increment the gauge."""
        self.value += amount
    
    def decrement(self, amount: float = 1.0):
        """Decrement the gauge."""
        self.value -= amount
    
    def get(self) -> float:
        """Get current value."""
        return self.value


class Histogram:
    """
    A histogram metric for tracking distributions.
    
    Used for tracking distributions (e.g., message sizes, latencies).
    """
    
    def __init__(self, name: str, description: str = "", max_size: int = 1000):
        """
        Initialize histogram.
        
        Args:
            name: Metric name
            description: Human-readable description
            max_size: Maximum number of samples to keep
        """
        self.name = name
        self.description = description
        self.max_size = max_size
        self.samples: deque = deque(maxlen=max_size)
        self.created_at = time.time()
    
    def observe(self, value: float):
        """Add a sample to the histogram."""
        self.samples.append(value)
    
    def get_summary(self) -> Optional[MetricSummary]:
        """
        Get summary statistics.
        
        Returns:
            MetricSummary or None if no samples
        """
        if not self.samples:
            return None
        
        sorted_samples = sorted(self.samples)
        count = len(sorted_samples)
        total = sum(sorted_samples)
        
        return MetricSummary(
            count=count,
            sum=total,
            min=sorted_samples[0],
            max=sorted_samples[-1],
            mean=total / count,
        )
    
    def get_percentile(self, percentile: float) -> Optional[float]:
        """
        Get a specific percentile value.
        
        Args:
            percentile: Percentile to calculate (0.0 to 1.0)
            
        Returns:
            Percentile value or None if no samples
        """
        if not self.samples:
            return None
        
        sorted_samples = sorted(self.samples)
        index = int(len(sorted_samples) * percentile)
        index = min(index, len(sorted_samples) - 1)
        return sorted_samples[index]
    
    def clear(self):
        """Clear all samples."""
        self.samples.clear()


class Timer:
    """
    A timer metric for measuring durations.
    
    Context manager for easy timing of code blocks.
    """
    
    def __init__(self, histogram: Histogram):
        """
        Initialize timer.
        
        Args:
            histogram: Histogram to record duration to
        """
        self.histogram = histogram
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and record duration."""
        if self.start_time is not None:
            duration = time.time() - self.start_time
            self.histogram.observe(duration)
        return False


class MetricsCollector:
    """
    Central metrics collection system.
    
    Provides a unified interface for creating and managing metrics
    across the entire networking system.
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self.logger = structlog.get_logger()
        
        self.counters: Dict[str, Counter] = {}
        self.gauges: Dict[str, Gauge] = {}
        self.histograms: Dict[str, Histogram] = {}
        
        self.created_at = time.time()
        
        # Initialize default metrics
        self._init_default_metrics()
    
    def _init_default_metrics(self):
        """Initialize default network metrics."""
        # Message metrics
        self.counter("messages.sent.total", "Total messages sent")
        self.counter("messages.received.total", "Total messages received")
        self.counter("messages.dropped.total", "Total messages dropped")
        self.counter("messages.duplicates.total", "Total duplicate messages")
        
        # Connection metrics
        self.gauge("connections.active", "Active network connections")
        self.counter("connections.total", "Total connections established")
        self.counter("connections.failed", "Failed connection attempts")
        
        # Peer metrics
        self.gauge("peers.active", "Active peers")
        self.gauge("peers.known", "Known peers")
        self.counter("peers.discovered", "Peers discovered")
        
        # Gossip metrics
        self.counter("gossip.messages.propagated", "Messages propagated via gossip")
        self.counter("gossip.rounds.total", "Total gossip rounds")
        
        # Trust metrics
        self.counter("trust.updates.total", "Total trust updates")
        self.gauge("trust.average", "Average trust score")
        
        # DHT metrics
        self.counter("dht.stores.total", "Total DHT store operations")
        self.counter("dht.retrievals.total", "Total DHT retrieve operations")
        self.gauge("dht.keys.stored", "Keys stored in DHT")
        
        # Performance metrics
        self.histogram("message.size.bytes", "Message size distribution")
        self.histogram("message.latency.seconds", "Message latency distribution")
        self.histogram("connection.duration.seconds", "Connection duration distribution")
        
        # Error metrics
        self.counter("errors.network.total", "Network errors")
        self.counter("errors.protocol.total", "Protocol errors")
        self.counter("errors.validation.total", "Validation errors")
    
    def counter(self, name: str, description: str = "") -> Counter:
        """
        Get or create a counter metric.
        
        Args:
            name: Metric name
            description: Human-readable description
            
        Returns:
            Counter instance
        """
        if name not in self.counters:
            self.counters[name] = Counter(name, description)
        return self.counters[name]
    
    def gauge(self, name: str, description: str = "") -> Gauge:
        """
        Get or create a gauge metric.
        
        Args:
            name: Metric name
            description: Human-readable description
            
        Returns:
            Gauge instance
        """
        if name not in self.gauges:
            self.gauges[name] = Gauge(name, description)
        return self.gauges[name]
    
    def histogram(self, name: str, description: str = "", max_size: int = 1000) -> Histogram:
        """
        Get or create a histogram metric.
        
        Args:
            name: Metric name
            description: Human-readable description
            max_size: Maximum samples to keep
            
        Returns:
            Histogram instance
        """
        if name not in self.histograms:
            self.histograms[name] = Histogram(name, description, max_size)
        return self.histograms[name]
    
    def timer(self, name: str, description: str = "") -> Timer:
        """
        Get a timer for measuring durations.
        
        Args:
            name: Metric name
            description: Human-readable description
            
        Returns:
            Timer context manager
        """
        hist = self.histogram(name, description)
        return Timer(hist)
    
    def increment_counter(self, name: str, amount: float = 1.0):
        """Increment a counter by name."""
        if name in self.counters:
            self.counters[name].increment(amount)
    
    def set_gauge(self, name: str, value: float):
        """Set a gauge value by name."""
        if name in self.gauges:
            self.gauges[name].set(value)
    
    def observe_histogram(self, name: str, value: float):
        """Add a sample to a histogram by name."""
        if name in self.histograms:
            self.histograms[name].observe(value)
    
    def get_all_metrics(self) -> dict:
        """
        Get all metrics as a dictionary.
        
        Returns:
            Dictionary with all current metric values
        """
        metrics = {
            'timestamp': time.time(),
            'uptime_seconds': time.time() - self.created_at,
            'counters': {},
            'gauges': {},
            'histograms': {},
        }
        
        # Collect counters
        for name, counter in self.counters.items():
            metrics['counters'][name] = {
                'value': counter.get(),
                'description': counter.description,
            }
        
        # Collect gauges
        for name, gauge in self.gauges.items():
            metrics['gauges'][name] = {
                'value': gauge.get(),
                'description': gauge.description,
            }
        
        # Collect histograms
        for name, histogram in self.histograms.items():
            summary = histogram.get_summary()
            metrics['histograms'][name] = {
                'description': histogram.description,
                'summary': summary.to_dict() if summary else None,
                'p50': histogram.get_percentile(0.5),
                'p95': histogram.get_percentile(0.95),
                'p99': histogram.get_percentile(0.99),
            }
        
        return metrics
    
    def get_summary(self) -> dict:
        """
        Get a summary of key metrics.
        
        Returns:
            Dictionary with summary statistics
        """
        return {
            'uptime_seconds': time.time() - self.created_at,
            'messages': {
                'sent': self.counters.get('messages.sent.total', Counter('', '')).get(),
                'received': self.counters.get('messages.received.total', Counter('', '')).get(),
                'dropped': self.counters.get('messages.dropped.total', Counter('', '')).get(),
                'duplicates': self.counters.get('messages.duplicates.total', Counter('', '')).get(),
            },
            'connections': {
                'active': self.gauges.get('connections.active', Gauge('', '')).get(),
                'total': self.counters.get('connections.total', Counter('', '')).get(),
                'failed': self.counters.get('connections.failed', Counter('', '')).get(),
            },
            'peers': {
                'active': self.gauges.get('peers.active', Gauge('', '')).get(),
                'known': self.gauges.get('peers.known', Gauge('', '')).get(),
            },
            'dht': {
                'stores': self.counters.get('dht.stores.total', Counter('', '')).get(),
                'retrievals': self.counters.get('dht.retrievals.total', Counter('', '')).get(),
                'keys_stored': self.gauges.get('dht.keys.stored', Gauge('', '')).get(),
            },
        }
    
    def reset_all(self):
        """Reset all metrics to initial state."""
        for counter in self.counters.values():
            counter.reset()
        for gauge in self.gauges.values():
            gauge.set(0)
        for histogram in self.histograms.values():
            histogram.clear()
    
    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus text format.
        
        Returns:
            Prometheus-formatted metrics string
        """
        lines = []
        
        # Export counters
        for name, counter in self.counters.items():
            prometheus_name = name.replace('.', '_')
            if counter.description:
                lines.append(f"# HELP {prometheus_name} {counter.description}")
            lines.append(f"# TYPE {prometheus_name} counter")
            lines.append(f"{prometheus_name} {counter.get()}")
        
        # Export gauges
        for name, gauge in self.gauges.items():
            prometheus_name = name.replace('.', '_')
            if gauge.description:
                lines.append(f"# HELP {prometheus_name} {gauge.description}")
            lines.append(f"# TYPE {prometheus_name} gauge")
            lines.append(f"{prometheus_name} {gauge.get()}")
        
        # Export histograms
        for name, histogram in self.histograms.items():
            prometheus_name = name.replace('.', '_')
            summary = histogram.get_summary()
            if summary:
                if histogram.description:
                    lines.append(f"# HELP {prometheus_name} {histogram.description}")
                lines.append(f"# TYPE {prometheus_name} summary")
                lines.append(f"{prometheus_name}_count {summary.count}")
                lines.append(f"{prometheus_name}_sum {summary.sum}")
                
                # Add percentiles
                p50 = histogram.get_percentile(0.5)
                p95 = histogram.get_percentile(0.95)
                p99 = histogram.get_percentile(0.99)
                
                if p50 is not None:
                    lines.append(f'{prometheus_name}{{quantile="0.5"}} {p50}')
                if p95 is not None:
                    lines.append(f'{prometheus_name}{{quantile="0.95"}} {p95}')
                if p99 is not None:
                    lines.append(f'{prometheus_name}{{quantile="0.99"}} {p99}')
        
        return '\n'.join(lines) + '\n'


# Global metrics collector instance
_global_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """
    Get the global metrics collector instance.
    
    Returns:
        Global MetricsCollector instance
    """
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = MetricsCollector()
    return _global_metrics


def reset_metrics():
    """Reset the global metrics collector."""
    global _global_metrics
    _global_metrics = None
