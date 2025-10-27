"""
Flow control and congestion control mechanisms.
"""
import time
from typing import Optional
from collections import deque


class FlowController:
    """
    Implements flow control using sliding window.
    Prevents sender from overwhelming receiver.
    """
    
    def __init__(self, initial_window: int = 65535):
        """
        Initialize flow controller.
        
        Args:
            initial_window: Initial window size in bytes
        """
        self.window_size = initial_window
        self.max_window = 65535
        self.min_window = 1024
        
        # Bytes in flight
        self.bytes_in_flight = 0
        
        # Receiver's advertised window
        self.receiver_window = initial_window
    
    def can_send(self, data_size: int) -> bool:
        """
        Check if we can send data of given size.
        
        Args:
            data_size: Size of data to send
            
        Returns:
            True if we can send
        """
        effective_window = min(self.window_size, self.receiver_window)
        return self.bytes_in_flight + data_size <= effective_window
    
    def on_send(self, data_size: int):
        """
        Called when data is sent.
        
        Args:
            data_size: Size of data sent
        """
        self.bytes_in_flight += data_size
    
    def on_ack(self, data_size: int, receiver_window: int):
        """
        Called when acknowledgment is received.
        
        Args:
            data_size: Size of data acknowledged
            receiver_window: Receiver's advertised window
        """
        self.bytes_in_flight = max(0, self.bytes_in_flight - data_size)
        self.receiver_window = receiver_window
    
    def get_available_window(self) -> int:
        """Get available window size."""
        effective_window = min(self.window_size, self.receiver_window)
        return max(0, effective_window - self.bytes_in_flight)


class CongestionController:
    """
    Implements TCP-like congestion control.
    Uses slow start, congestion avoidance, fast retransmit, and fast recovery.
    """
    
    def __init__(self, mss: int = 1400):
        """
        Initialize congestion controller.
        
        Args:
            mss: Maximum segment size in bytes
        """
        self.mss = mss  # Maximum segment size
        
        # Congestion window (in bytes)
        self.cwnd = mss  # Start with 1 MSS
        
        # Slow start threshold
        self.ssthresh = 65535  # Start with large threshold
        
        # State
        self.in_slow_start = True
        self.in_fast_recovery = False
        
        # Duplicate ACK tracking
        self.last_ack = 0
        self.duplicate_ack_count = 0
        
        # RTT tracking for congestion
        self.min_rtt = float('inf')
        self.rtt_measurements = deque(maxlen=10)
        
        # Timestamps
        self.last_loss_time = 0
        
        # Statistics
        self.losses = 0
        self.fast_retransmits = 0
    
    def get_send_window(self) -> int:
        """Get current congestion window size."""
        return int(self.cwnd)
    
    def on_ack(self, rtt: Optional[float] = None):
        """
        Called when ACK is received.
        
        Args:
            rtt: Round-trip time for this ACK (optional)
        """
        if rtt:
            self.rtt_measurements.append(rtt)
            self.min_rtt = min(self.min_rtt, rtt)
        
        if self.in_fast_recovery:
            # Exit fast recovery
            self.cwnd = self.ssthresh
            self.in_fast_recovery = False
        elif self.in_slow_start:
            # Slow start: increase cwnd by 1 MSS per ACK
            self.cwnd += self.mss
            
            # Check if we should exit slow start
            if self.cwnd >= self.ssthresh:
                self.in_slow_start = False
        else:
            # Congestion avoidance: increase cwnd by MSS * (MSS / cwnd) per ACK
            # This gives linear increase instead of exponential
            increment = self.mss * self.mss / self.cwnd
            self.cwnd += increment
        
        # Reset duplicate ACK counter
        self.duplicate_ack_count = 0
    
    def on_duplicate_ack(self, ack_number: int):
        """
        Called when duplicate ACK is received.
        
        Args:
            ack_number: ACK number received
        """
        if ack_number == self.last_ack:
            self.duplicate_ack_count += 1
            
            # Fast retransmit after 3 duplicate ACKs
            if self.duplicate_ack_count == 3:
                self._on_fast_retransmit()
        else:
            self.last_ack = ack_number
            self.duplicate_ack_count = 1
    
    def _on_fast_retransmit(self):
        """Handle fast retransmit."""
        self.fast_retransmits += 1
        
        # Enter fast recovery
        self.ssthresh = max(self.cwnd / 2, 2 * self.mss)
        self.cwnd = self.ssthresh + 3 * self.mss
        self.in_fast_recovery = True
        self.in_slow_start = False
    
    def on_timeout(self):
        """Called when retransmission timeout occurs."""
        self.losses += 1
        self.last_loss_time = time.time()
        
        # Multiplicative decrease
        self.ssthresh = max(self.cwnd / 2, 2 * self.mss)
        self.cwnd = self.mss
        
        # Enter slow start
        self.in_slow_start = True
        self.in_fast_recovery = False
        
        # Reset duplicate ACK tracking
        self.duplicate_ack_count = 0
    
    def on_ecn(self):
        """Called when Explicit Congestion Notification is received."""
        # Similar to timeout but less aggressive
        if not self.in_fast_recovery:
            self.ssthresh = max(self.cwnd / 2, 2 * self.mss)
            self.cwnd = self.ssthresh
            self.in_slow_start = False
    
    def is_network_congested(self) -> bool:
        """
        Detect if network is congested based on RTT increase.
        
        Returns:
            True if congestion detected
        """
        if len(self.rtt_measurements) < 5:
            return False
        
        recent_rtt = sum(list(self.rtt_measurements)[-3:]) / 3
        return recent_rtt > self.min_rtt * 1.5
    
    def get_stats(self) -> dict:
        """Get congestion control statistics."""
        return {
            'cwnd': int(self.cwnd),
            'ssthresh': int(self.ssthresh),
            'in_slow_start': self.in_slow_start,
            'in_fast_recovery': self.in_fast_recovery,
            'losses': self.losses,
            'fast_retransmits': self.fast_retransmits,
            'duplicate_acks': self.duplicate_ack_count,
            'min_rtt': self.min_rtt if self.min_rtt != float('inf') else 0,
        }


class AdaptiveFlowController:
    """
    Adaptive flow control that combines flow control and congestion control.
    """
    
    def __init__(self, mss: int = 1400, initial_window: int = 65535):
        """
        Initialize adaptive flow controller.
        
        Args:
            mss: Maximum segment size
            initial_window: Initial window size
        """
        self.flow_controller = FlowController(initial_window)
        self.congestion_controller = CongestionController(mss)
    
    def can_send(self, data_size: int) -> bool:
        """Check if we can send data."""
        # Respect both flow control and congestion control
        flow_ok = self.flow_controller.can_send(data_size)
        
        congestion_window = self.congestion_controller.get_send_window()
        congestion_ok = self.flow_controller.bytes_in_flight + data_size <= congestion_window
        
        return flow_ok and congestion_ok
    
    def on_send(self, data_size: int):
        """Called when data is sent."""
        self.flow_controller.on_send(data_size)
    
    def on_ack(self, data_size: int, receiver_window: int, rtt: Optional[float] = None):
        """Called when ACK is received."""
        self.flow_controller.on_ack(data_size, receiver_window)
        self.congestion_controller.on_ack(rtt)
    
    def on_duplicate_ack(self, ack_number: int):
        """Called on duplicate ACK."""
        self.congestion_controller.on_duplicate_ack(ack_number)
    
    def on_timeout(self):
        """Called on timeout."""
        self.congestion_controller.on_timeout()
    
    def get_effective_window(self) -> int:
        """Get effective send window."""
        flow_window = self.flow_controller.get_available_window()
        congestion_window = self.congestion_controller.get_send_window()
        return min(flow_window, congestion_window)
    
    def get_stats(self) -> dict:
        """Get combined statistics."""
        return {
            'flow_control': {
                'window_size': self.flow_controller.window_size,
                'receiver_window': self.flow_controller.receiver_window,
                'bytes_in_flight': self.flow_controller.bytes_in_flight,
                'available': self.flow_controller.get_available_window(),
            },
            'congestion_control': self.congestion_controller.get_stats(),
            'effective_window': self.get_effective_window(),
        }
