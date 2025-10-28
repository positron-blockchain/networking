"""
Bloom filter implementation for efficient message deduplication and anti-entropy.

A Bloom filter is a space-efficient probabilistic data structure used to test
whether an element is a member of a set. False positive matches are possible,
but false negatives are not.
"""
import math
import hashlib
import struct
from typing import Optional, List


class BloomFilter:
    """
    Space-efficient probabilistic set membership data structure.
    
    This implementation uses multiple hash functions to achieve the desired
    false positive rate while minimizing memory usage.
    """
    
    def __init__(self, expected_elements: int, false_positive_rate: float = 0.01):
        """
        Initialize a Bloom filter.
        
        Args:
            expected_elements: Expected number of elements to be inserted
            false_positive_rate: Desired false positive probability (default: 0.01 = 1%)
        
        Raises:
            ValueError: If parameters are invalid
        """
        if expected_elements <= 0:
            raise ValueError("expected_elements must be positive")
        if not 0 < false_positive_rate < 1:
            raise ValueError("false_positive_rate must be between 0 and 1")
        
        self.expected_elements = expected_elements
        self.false_positive_rate = false_positive_rate
        
        # Calculate optimal bit array size (m) and number of hash functions (k)
        # m = -n * ln(p) / (ln(2)^2)
        # k = (m / n) * ln(2)
        self.size = self._calculate_size(expected_elements, false_positive_rate)
        self.num_hashes = self._calculate_num_hashes(self.size, expected_elements)
        
        # Bit array stored as bytes
        self.bit_array = bytearray((self.size + 7) // 8)
        self.num_items = 0
    
    @staticmethod
    def _calculate_size(n: int, p: float) -> int:
        """Calculate optimal bit array size."""
        size = -n * math.log(p) / (math.log(2) ** 2)
        return int(math.ceil(size))
    
    @staticmethod
    def _calculate_num_hashes(m: int, n: int) -> int:
        """Calculate optimal number of hash functions."""
        num_hashes = (m / n) * math.log(2)
        return max(1, int(math.ceil(num_hashes)))
    
    def _hash(self, item: str, seed: int) -> int:
        """
        Generate a hash value for an item with a given seed.
        
        Args:
            item: String to hash
            seed: Seed for hash function
            
        Returns:
            Hash value in range [0, size)
        """
        # Use SHA-256 with seed for cryptographic strength
        hasher = hashlib.sha256()
        hasher.update(struct.pack('I', seed))
        hasher.update(item.encode('utf-8'))
        hash_bytes = hasher.digest()
        
        # Convert first 8 bytes to integer
        hash_int = struct.unpack('Q', hash_bytes[:8])[0]
        return hash_int % self.size
    
    def _set_bit(self, position: int) -> None:
        """Set a bit at the given position."""
        byte_index = position // 8
        bit_index = position % 8
        self.bit_array[byte_index] |= (1 << bit_index)
    
    def _get_bit(self, position: int) -> bool:
        """Get the value of a bit at the given position."""
        byte_index = position // 8
        bit_index = position % 8
        return bool(self.bit_array[byte_index] & (1 << bit_index))
    
    def add(self, item: str) -> None:
        """
        Add an item to the Bloom filter.
        
        Args:
            item: String to add to the filter
        """
        for seed in range(self.num_hashes):
            position = self._hash(item, seed)
            self._set_bit(position)
        self.num_items += 1
    
    def contains(self, item: str) -> bool:
        """
        Check if an item might be in the set.
        
        Args:
            item: String to check
            
        Returns:
            True if the item might be in the set (possible false positive),
            False if the item is definitely not in the set
        """
        for seed in range(self.num_hashes):
            position = self._hash(item, seed)
            if not self._get_bit(position):
                return False
        return True
    
    def __contains__(self, item: str) -> bool:
        """Support 'in' operator."""
        return self.contains(item)
    
    def clear(self) -> None:
        """Clear all items from the filter."""
        self.bit_array = bytearray((self.size + 7) // 8)
        self.num_items = 0
    
    def current_false_positive_rate(self) -> float:
        """
        Calculate the current false positive rate based on items added.
        
        Returns:
            Estimated current false positive rate
        """
        if self.num_items == 0:
            return 0.0
        
        # p = (1 - e^(-k*n/m))^k
        exponent = -self.num_hashes * self.num_items / self.size
        return (1 - math.exp(exponent)) ** self.num_hashes
    
    def is_full(self) -> bool:
        """
        Check if the filter is approaching capacity.
        
        Returns:
            True if the filter has exceeded expected capacity
        """
        return self.num_items >= self.expected_elements
    
    def serialize(self) -> bytes:
        """
        Serialize the Bloom filter to bytes.
        
        Returns:
            Serialized filter as bytes
        """
        # Header: expected_elements (4 bytes), false_positive_rate (4 bytes),
        # size (4 bytes), num_hashes (2 bytes), num_items (4 bytes)
        header = struct.pack(
            '!IfIHI',
            self.expected_elements,
            self.false_positive_rate,
            self.size,
            self.num_hashes,
            self.num_items
        )
        return header + bytes(self.bit_array)
    
    @classmethod
    def deserialize(cls, data: bytes) -> 'BloomFilter':
        """
        Deserialize a Bloom filter from bytes.
        
        Args:
            data: Serialized filter bytes
            
        Returns:
            Deserialized BloomFilter instance
            
        Raises:
            ValueError: If data is invalid
        """
        # Calculate header size: I(4) + f(4) + I(4) + H(2) + I(4) = 18 bytes
        header_size = 18
        
        if len(data) < header_size:
            raise ValueError("Invalid serialized data: too short")
        
        # Unpack header
        expected_elements, false_positive_rate, size, num_hashes, num_items = \
            struct.unpack('!IfIHI', data[:header_size])
        
        # Validate
        expected_byte_size = (size + 7) // 8
        if len(data) != header_size + expected_byte_size:
            raise ValueError("Invalid serialized data: size mismatch")
        
        # Create filter and restore state
        bloom = cls.__new__(cls)
        bloom.expected_elements = expected_elements
        bloom.false_positive_rate = false_positive_rate
        bloom.size = size
        bloom.num_hashes = num_hashes
        bloom.num_items = num_items
        bloom.bit_array = bytearray(data[header_size:])
        
        return bloom
    
    def get_stats(self) -> dict:
        """
        Get statistics about the Bloom filter.
        
        Returns:
            Dictionary with filter statistics
        """
        return {
            'expected_elements': self.expected_elements,
            'current_elements': self.num_items,
            'size_bits': self.size,
            'size_bytes': len(self.bit_array),
            'num_hash_functions': self.num_hashes,
            'target_false_positive_rate': self.false_positive_rate,
            'current_false_positive_rate': self.current_false_positive_rate(),
            'utilization': self.num_items / self.expected_elements if self.expected_elements > 0 else 0,
            'is_full': self.is_full(),
        }
    
    def __repr__(self) -> str:
        """String representation."""
        return (f"BloomFilter(expected={self.expected_elements}, "
                f"items={self.num_items}, "
                f"size={self.size} bits, "
                f"hashes={self.num_hashes}, "
                f"fpr={self.current_false_positive_rate():.4f})")


class ScalableBloomFilter:
    """
    Scalable Bloom filter that automatically adds new filters as capacity is reached.
    
    This allows the filter to handle more elements than initially expected while
    maintaining the target false positive rate.
    """
    
    def __init__(
        self,
        initial_capacity: int,
        false_positive_rate: float = 0.01,
        growth_factor: int = 2,
        tightening_ratio: float = 0.9
    ):
        """
        Initialize a scalable Bloom filter.
        
        Args:
            initial_capacity: Initial capacity of the first filter
            false_positive_rate: Target false positive rate
            growth_factor: Factor by which to grow each new filter
            tightening_ratio: Factor to tighten FPR for new filters
        """
        self.initial_capacity = initial_capacity
        self.false_positive_rate = false_positive_rate
        self.growth_factor = growth_factor
        self.tightening_ratio = tightening_ratio
        
        self.filters: List[BloomFilter] = []
        self._add_filter()
    
    def _add_filter(self) -> None:
        """Add a new Bloom filter to the sequence."""
        if not self.filters:
            # First filter
            capacity = self.initial_capacity
            fpr = self.false_positive_rate
        else:
            # Subsequent filters grow in capacity and tighten FPR
            capacity = len(self.filters[-1].bit_array) * self.growth_factor
            fpr = self.false_positive_rate * (self.tightening_ratio ** len(self.filters))
        
        self.filters.append(BloomFilter(capacity, fpr))
    
    def add(self, item: str) -> None:
        """
        Add an item to the scalable Bloom filter.
        
        Args:
            item: String to add
        """
        # Check if current filter is full
        if self.filters[-1].is_full():
            self._add_filter()
        
        self.filters[-1].add(item)
    
    def contains(self, item: str) -> bool:
        """
        Check if an item might be in the set.
        
        Args:
            item: String to check
            
        Returns:
            True if item might be in set, False if definitely not
        """
        return any(bf.contains(item) for bf in self.filters)
    
    def __contains__(self, item: str) -> bool:
        """Support 'in' operator."""
        return self.contains(item)
    
    def clear(self) -> None:
        """Clear all filters."""
        self.filters = []
        self._add_filter()
    
    def get_stats(self) -> dict:
        """
        Get statistics about the scalable Bloom filter.
        
        Returns:
            Dictionary with filter statistics
        """
        total_items = sum(bf.num_items for bf in self.filters)
        total_size_bytes = sum(len(bf.bit_array) for bf in self.filters)
        
        return {
            'num_filters': len(self.filters),
            'total_items': total_items,
            'total_size_bytes': total_size_bytes,
            'filters': [bf.get_stats() for bf in self.filters],
        }
    
    def __repr__(self) -> str:
        """String representation."""
        total_items = sum(bf.num_items for bf in self.filters)
        return (f"ScalableBloomFilter(filters={len(self.filters)}, "
                f"items={total_items})")
