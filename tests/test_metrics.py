"""
Comprehensive tests for enhanced metrics system.
"""
import pytest
import time
import asyncio
from positron_networking.metrics import (
    Counter, Gauge, Histogram, Timer, MetricsCollector,
    get_metrics, reset_metrics
)


class TestCounter:
    """Test cases for Counter metric."""
    
    def test_initialization(self):
        """Test counter initialization."""
        counter = Counter("test_counter", "Test counter")
        
        assert counter.name == "test_counter"
        assert counter.description == "Test counter"
        assert counter.value == 0
        assert counter.created_at > 0
    
    def test_increment(self):
        """Test incrementing counter."""
        counter = Counter("test")
        
        counter.increment()
        assert counter.get() == 1
        
        counter.increment(5)
        assert counter.get() == 6
    
    def test_reset(self):
        """Test resetting counter."""
        counter = Counter("test")
        counter.increment(10)
        
        counter.reset()
        assert counter.get() == 0


class TestGauge:
    """Test cases for Gauge metric."""
    
    def test_initialization(self):
        """Test gauge initialization."""
        gauge = Gauge("test_gauge", "Test gauge")
        
        assert gauge.name == "test_gauge"
        assert gauge.description == "Test gauge"
        assert gauge.value == 0.0
    
    def test_set(self):
        """Test setting gauge value."""
        gauge = Gauge("test")
        
        gauge.set(42.5)
        assert gauge.get() == 42.5
    
    def test_increment_decrement(self):
        """Test incrementing and decrementing gauge."""
        gauge = Gauge("test")
        gauge.set(10)
        
        gauge.increment(5)
        assert gauge.get() == 15
        
        gauge.decrement(3)
        assert gauge.get() == 12


class TestHistogram:
    """Test cases for Histogram metric."""
    
    def test_initialization(self):
        """Test histogram initialization."""
        histogram = Histogram("test_histogram", "Test histogram", max_size=100)
        
        assert histogram.name == "test_histogram"
        assert histogram.description == "Test histogram"
        assert histogram.max_size == 100
        assert len(histogram.samples) == 0
    
    def test_observe(self):
        """Test adding samples to histogram."""
        histogram = Histogram("test", max_size=10)
        
        histogram.observe(1.0)
        histogram.observe(2.0)
        histogram.observe(3.0)
        
        assert len(histogram.samples) == 3
    
    def test_max_size(self):
        """Test histogram max size enforcement."""
        histogram = Histogram("test", max_size=5)
        
        for i in range(10):
            histogram.observe(float(i))
        
        # Should only keep last 5 samples
        assert len(histogram.samples) == 5
    
    def test_summary(self):
        """Test getting summary statistics."""
        histogram = Histogram("test")
        
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for value in values:
            histogram.observe(value)
        
        summary = histogram.get_summary()
        
        assert summary is not None
        assert summary.count == 5
        assert summary.sum == 15.0
        assert summary.min == 1.0
        assert summary.max == 5.0
        assert summary.mean == 3.0
    
    def test_empty_summary(self):
        """Test summary with no samples."""
        histogram = Histogram("test")
        
        summary = histogram.get_summary()
        assert summary is None
    
    def test_percentiles(self):
        """Test percentile calculation."""
        histogram = Histogram("test")
        
        # Add 100 samples: 0.0 to 99.0
        for i in range(100):
            histogram.observe(float(i))
        
        p50 = histogram.get_percentile(0.5)
        p95 = histogram.get_percentile(0.95)
        p99 = histogram.get_percentile(0.99)
        
        assert p50 is not None
        assert p95 is not None
        assert p99 is not None
        
        # Rough checks (exact values depend on rounding)
        assert 45 <= p50 <= 55
        assert 90 <= p95 <= 99
        assert 95 <= p99 <= 99
    
    def test_percentile_empty(self):
        """Test percentile with no samples."""
        histogram = Histogram("test")
        
        p50 = histogram.get_percentile(0.5)
        assert p50 is None
    
    def test_clear(self):
        """Test clearing histogram."""
        histogram = Histogram("test")
        
        for i in range(10):
            histogram.observe(float(i))
        
        histogram.clear()
        assert len(histogram.samples) == 0


class TestTimer:
    """Test cases for Timer context manager."""
    
    def test_timer_basic(self):
        """Test basic timer functionality."""
        histogram = Histogram("test")
        
        with Timer(histogram):
            time.sleep(0.1)
        
        assert len(histogram.samples) == 1
        # Should be approximately 0.1 seconds
        assert 0.05 < histogram.samples[0] < 0.2
    
    def test_timer_multiple(self):
        """Test multiple timer measurements."""
        histogram = Histogram("test")
        
        for _ in range(5):
            with Timer(histogram):
                time.sleep(0.01)
        
        assert len(histogram.samples) == 5


class TestMetricsCollector:
    """Test cases for MetricsCollector."""
    
    def test_initialization(self):
        """Test metrics collector initialization."""
        collector = MetricsCollector()
        
        assert len(collector.counters) > 0  # Should have default metrics
        assert len(collector.gauges) > 0
        assert len(collector.histograms) > 0
    
    def test_counter_creation(self):
        """Test creating counters."""
        collector = MetricsCollector()
        
        counter = collector.counter("custom.counter", "Custom counter")
        
        assert counter.name == "custom.counter"
        assert "custom.counter" in collector.counters
        
        # Getting same counter should return same instance
        counter2 = collector.counter("custom.counter")
        assert counter2 is counter
    
    def test_gauge_creation(self):
        """Test creating gauges."""
        collector = MetricsCollector()
        
        gauge = collector.gauge("custom.gauge", "Custom gauge")
        
        assert gauge.name == "custom.gauge"
        assert "custom.gauge" in collector.gauges
    
    def test_histogram_creation(self):
        """Test creating histograms."""
        collector = MetricsCollector()
        
        histogram = collector.histogram("custom.histogram", "Custom histogram")
        
        assert histogram.name == "custom.histogram"
        assert "custom.histogram" in collector.histograms
    
    def test_timer_creation(self):
        """Test creating timers."""
        collector = MetricsCollector()
        
        timer = collector.timer("test.duration", "Test duration")
        
        assert isinstance(timer, Timer)
    
    def test_increment_counter(self):
        """Test incrementing counter by name."""
        collector = MetricsCollector()
        collector.counter("test.counter")
        
        collector.increment_counter("test.counter", 5)
        
        assert collector.counters["test.counter"].get() == 5
    
    def test_set_gauge(self):
        """Test setting gauge by name."""
        collector = MetricsCollector()
        collector.gauge("test.gauge")
        
        collector.set_gauge("test.gauge", 42.0)
        
        assert collector.gauges["test.gauge"].get() == 42.0
    
    def test_observe_histogram(self):
        """Test adding histogram sample by name."""
        collector = MetricsCollector()
        collector.histogram("test.histogram")
        
        collector.observe_histogram("test.histogram", 10.5)
        
        assert len(collector.histograms["test.histogram"].samples) == 1
    
    def test_get_all_metrics(self):
        """Test getting all metrics."""
        collector = MetricsCollector()
        
        # Add some custom metrics
        collector.counter("test.counter").increment(5)
        collector.gauge("test.gauge").set(42)
        collector.histogram("test.histogram").observe(1.5)
        
        metrics = collector.get_all_metrics()
        
        assert isinstance(metrics, dict)
        assert 'timestamp' in metrics
        assert 'uptime_seconds' in metrics
        assert 'counters' in metrics
        assert 'gauges' in metrics
        assert 'histograms' in metrics
        
        assert 'test.counter' in metrics['counters']
        assert metrics['counters']['test.counter']['value'] == 5
        
        assert 'test.gauge' in metrics['gauges']
        assert metrics['gauges']['test.gauge']['value'] == 42
        
        assert 'test.histogram' in metrics['histograms']
    
    def test_get_summary(self):
        """Test getting metrics summary."""
        collector = MetricsCollector()
        
        # Simulate some activity
        collector.increment_counter("messages.sent.total", 100)
        collector.increment_counter("messages.received.total", 95)
        collector.set_gauge("peers.active", 10)
        
        summary = collector.get_summary()
        
        assert isinstance(summary, dict)
        assert summary['messages']['sent'] == 100
        assert summary['messages']['received'] == 95
        assert summary['peers']['active'] == 10
    
    def test_reset_all(self):
        """Test resetting all metrics."""
        collector = MetricsCollector()
        
        # Add some data
        collector.counter("test.counter").increment(10)
        collector.gauge("test.gauge").set(50)
        collector.histogram("test.histogram").observe(5.0)
        
        collector.reset_all()
        
        assert collector.counters["test.counter"].get() == 0
        assert collector.gauges["test.gauge"].get() == 0
        assert len(collector.histograms["test.histogram"].samples) == 0
    
    def test_export_prometheus(self):
        """Test exporting metrics in Prometheus format."""
        collector = MetricsCollector()
        
        # Add some metrics
        collector.counter("test_counter").increment(5)
        collector.gauge("test_gauge").set(42)
        
        histogram = collector.histogram("test_histogram")
        for i in range(10):
            histogram.observe(float(i))
        
        prometheus_output = collector.export_prometheus()
        
        assert isinstance(prometheus_output, str)
        assert "test_counter 5" in prometheus_output
        assert "test_gauge 42" in prometheus_output
        assert "test_histogram_count" in prometheus_output


class TestGlobalMetrics:
    """Test global metrics accessor functions."""
    
    def setup_method(self):
        """Reset global metrics before each test."""
        reset_metrics()
    
    def test_get_metrics(self):
        """Test getting global metrics instance."""
        metrics1 = get_metrics()
        metrics2 = get_metrics()
        
        # Should return same instance
        assert metrics1 is metrics2
    
    def test_reset_metrics(self):
        """Test resetting global metrics."""
        metrics1 = get_metrics()
        metrics1.counter("test").increment(5)
        
        reset_metrics()
        
        metrics2 = get_metrics()
        # Should be a new instance
        assert metrics2 is not metrics1
        # Should not have the previous counter value
        assert "test" not in metrics2.counters or metrics2.counters["test"].get() == 0


class TestMetricsIntegration:
    """Integration tests for metrics system."""
    
    def test_network_metrics_flow(self):
        """Test typical network metrics flow."""
        collector = MetricsCollector()
        
        # Simulate network activity
        collector.increment_counter("messages.sent.total", 1)
        collector.increment_counter("connections.total", 1)
        collector.set_gauge("connections.active", 5)
        collector.set_gauge("peers.active", 3)
        
        # Measure message latency
        with collector.timer("message.latency.seconds"):
            time.sleep(0.01)
        
        # Measure message size
        collector.observe_histogram("message.size.bytes", 1024)
        collector.observe_histogram("message.size.bytes", 2048)
        
        # Get summary
        summary = collector.get_summary()
        
        assert summary['messages']['sent'] == 1
        assert summary['connections']['active'] == 5
        assert summary['peers']['active'] == 3
        
        # Check histogram has samples
        latency_hist = collector.histograms["message.latency.seconds"]
        assert len(latency_hist.samples) == 1
        
        size_hist = collector.histograms["message.size.bytes"]
        assert len(size_hist.samples) == 2
    
    def test_concurrent_updates(self):
        """Test concurrent metric updates."""
        collector = MetricsCollector()
        counter = collector.counter("concurrent.counter")
        
        def increment_many():
            for _ in range(100):
                counter.increment()
        
        import threading
        threads = [threading.Thread(target=increment_many) for _ in range(5)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should have incremented 500 times total
        assert counter.get() == 500
    
    def test_metrics_over_time(self):
        """Test metrics collection over time."""
        collector = MetricsCollector()
        counter = collector.counter("periodic.counter")
        
        start_time = time.time()
        
        # Simulate periodic updates
        for _ in range(5):
            counter.increment()
            time.sleep(0.01)
        
        elapsed = time.time() - start_time
        
        assert counter.get() == 5
        # Uptime should be approximately the elapsed time
        metrics = collector.get_all_metrics()
        assert metrics['uptime_seconds'] >= elapsed - 0.01


class TestMetricsEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_negative_values(self):
        """Test handling negative values."""
        collector = MetricsCollector()
        
        gauge = collector.gauge("test.gauge")
        gauge.set(-10)
        
        assert gauge.get() == -10
        
        gauge.increment(-5)
        assert gauge.get() == -15
    
    def test_large_values(self):
        """Test handling very large values."""
        collector = MetricsCollector()
        
        counter = collector.counter("large.counter")
        counter.increment(1e15)
        
        assert counter.get() == 1e15
    
    def test_float_precision(self):
        """Test floating point precision."""
        collector = MetricsCollector()
        
        histogram = collector.histogram("precision.test")
        
        # Add many small values
        for i in range(1000):
            histogram.observe(0.001)
        
        summary = histogram.get_summary()
        
        # Sum should be close to 1.0
        assert 0.99 < summary.sum < 1.01
    
    def test_empty_metrics_export(self):
        """Test exporting with no custom metrics."""
        collector = MetricsCollector()
        
        # Should still export default metrics
        prometheus_output = collector.export_prometheus()
        
        assert isinstance(prometheus_output, str)
        assert len(prometheus_output) > 0
