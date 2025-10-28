"""
Comprehensive tests for Bloom filter implementation.
"""
import pytest
import time
from positron_networking.bloom_filter import BloomFilter, ScalableBloomFilter


class TestBloomFilter:
    """Test cases for BloomFilter class."""
    
    def test_initialization(self):
        """Test Bloom filter initialization."""
        bf = BloomFilter(expected_elements=1000, false_positive_rate=0.01)
        
        assert bf.expected_elements == 1000
        assert bf.false_positive_rate == 0.01
        assert bf.num_items == 0
        assert bf.size > 0
        assert bf.num_hashes > 0
    
    def test_invalid_parameters(self):
        """Test that invalid parameters raise errors."""
        with pytest.raises(ValueError):
            BloomFilter(expected_elements=0, false_positive_rate=0.01)
        
        with pytest.raises(ValueError):
            BloomFilter(expected_elements=1000, false_positive_rate=0)
        
        with pytest.raises(ValueError):
            BloomFilter(expected_elements=1000, false_positive_rate=1.5)
    
    def test_add_and_contains(self):
        """Test adding items and checking membership."""
        bf = BloomFilter(expected_elements=100, false_positive_rate=0.01)
        
        # Add items
        items = [f"item_{i}" for i in range(50)]
        for item in items:
            bf.add(item)
        
        # Check all added items are found
        for item in items:
            assert item in bf
        
        assert bf.num_items == 50
    
    def test_false_negatives_impossible(self):
        """Test that false negatives never occur."""
        bf = BloomFilter(expected_elements=1000, false_positive_rate=0.01)
        
        items = [f"test_item_{i}" for i in range(500)]
        for item in items:
            bf.add(item)
        
        # All added items must be found (no false negatives)
        for item in items:
            assert bf.contains(item), f"False negative for {item}"
    
    def test_false_positive_rate(self):
        """Test that false positive rate is within expected bounds."""
        expected_elements = 1000
        target_fpr = 0.01
        bf = BloomFilter(expected_elements=expected_elements, false_positive_rate=target_fpr)
        
        # Add expected number of elements
        added_items = set()
        for i in range(expected_elements):
            item = f"item_{i}"
            bf.add(item)
            added_items.add(item)
        
        # Test with items not added
        false_positives = 0
        test_count = 10000
        
        for i in range(test_count):
            test_item = f"not_added_{i}"
            if test_item not in added_items and bf.contains(test_item):
                false_positives += 1
        
        actual_fpr = false_positives / test_count
        
        # Allow 50% margin of error (actual FPR should be close to target)
        assert actual_fpr <= target_fpr * 1.5, \
            f"False positive rate {actual_fpr} exceeds threshold {target_fpr * 1.5}"
    
    def test_clear(self):
        """Test clearing the filter."""
        bf = BloomFilter(expected_elements=100, false_positive_rate=0.01)
        
        # Add items
        for i in range(50):
            bf.add(f"item_{i}")
        
        assert bf.num_items == 50
        
        # Clear
        bf.clear()
        
        assert bf.num_items == 0
        # Previously added items should no longer be found
        # (though this isn't guaranteed due to hash collisions with new empty state)
    
    def test_serialization(self):
        """Test serialization and deserialization."""
        bf1 = BloomFilter(expected_elements=100, false_positive_rate=0.01)
        
        # Add items
        items = [f"item_{i}" for i in range(50)]
        for item in items:
            bf1.add(item)
        
        # Serialize
        data = bf1.serialize()
        assert isinstance(data, bytes)
        assert len(data) > 0
        
        # Deserialize
        bf2 = BloomFilter.deserialize(data)
        
        # Check properties match
        assert bf2.expected_elements == bf1.expected_elements
        assert abs(bf2.false_positive_rate - bf1.false_positive_rate) < 0.0001  # Float precision tolerance
        assert bf2.size == bf1.size
        assert bf2.num_hashes == bf1.num_hashes
        assert bf2.num_items == bf1.num_items
        
        # Check all items are still found
        for item in items:
            assert item in bf2
    
    def test_deserialization_invalid_data(self):
        """Test that invalid data raises errors."""
        with pytest.raises(ValueError):
            BloomFilter.deserialize(b"invalid")
        
        with pytest.raises(ValueError):
            BloomFilter.deserialize(b"")
    
    def test_current_false_positive_rate(self):
        """Test calculation of current false positive rate."""
        bf = BloomFilter(expected_elements=1000, false_positive_rate=0.01)
        
        # Empty filter should have 0 FPR
        assert bf.current_false_positive_rate() == 0.0
        
        # Add items and check FPR increases
        for i in range(500):
            bf.add(f"item_{i}")
        
        fpr = bf.current_false_positive_rate()
        assert 0 < fpr < 1.0
    
    def test_is_full(self):
        """Test checking if filter is full."""
        bf = BloomFilter(expected_elements=10, false_positive_rate=0.01)
        
        assert not bf.is_full()
        
        # Add expected number of items
        for i in range(10):
            bf.add(f"item_{i}")
        
        assert bf.is_full()
    
    def test_get_stats(self):
        """Test getting filter statistics."""
        bf = BloomFilter(expected_elements=100, false_positive_rate=0.01)
        
        for i in range(50):
            bf.add(f"item_{i}")
        
        stats = bf.get_stats()
        
        assert isinstance(stats, dict)
        assert stats['expected_elements'] == 100
        assert stats['current_elements'] == 50
        assert stats['size_bits'] > 0
        assert stats['size_bytes'] > 0
        assert stats['num_hash_functions'] > 0
        assert 0 <= stats['utilization'] <= 1
        assert isinstance(stats['is_full'], bool)
    
    def test_repr(self):
        """Test string representation."""
        bf = BloomFilter(expected_elements=100, false_positive_rate=0.01)
        repr_str = repr(bf)
        
        assert isinstance(repr_str, str)
        assert "BloomFilter" in repr_str


class TestScalableBloomFilter:
    """Test cases for ScalableBloomFilter class."""
    
    def test_initialization(self):
        """Test scalable Bloom filter initialization."""
        sbf = ScalableBloomFilter(initial_capacity=100, false_positive_rate=0.01)
        
        assert sbf.initial_capacity == 100
        assert sbf.false_positive_rate == 0.01
        assert len(sbf.filters) == 1  # Should start with one filter
    
    def test_add_and_contains(self):
        """Test adding items and checking membership."""
        sbf = ScalableBloomFilter(initial_capacity=100, false_positive_rate=0.01)
        
        items = [f"item_{i}" for i in range(50)]
        for item in items:
            sbf.add(item)
        
        for item in items:
            assert item in sbf
    
    def test_scaling(self):
        """Test that new filters are added when capacity is reached."""
        sbf = ScalableBloomFilter(initial_capacity=10, false_positive_rate=0.01)
        
        assert len(sbf.filters) == 1
        
        # Add more items than initial capacity
        for i in range(25):
            sbf.add(f"item_{i}")
        
        # Should have created additional filters
        assert len(sbf.filters) > 1
    
    def test_false_negatives_impossible_scalable(self):
        """Test that false negatives never occur in scalable filter."""
        sbf = ScalableBloomFilter(initial_capacity=50, false_positive_rate=0.01)
        
        # Add many items to force scaling
        items = [f"test_item_{i}" for i in range(500)]
        for item in items:
            sbf.add(item)
        
        # All added items must be found
        for item in items:
            assert sbf.contains(item), f"False negative for {item}"
    
    def test_clear_scalable(self):
        """Test clearing scalable filter."""
        sbf = ScalableBloomFilter(initial_capacity=10, false_positive_rate=0.01)
        
        # Add many items to create multiple filters
        for i in range(100):
            sbf.add(f"item_{i}")
        
        assert len(sbf.filters) > 1
        
        sbf.clear()
        
        # Should reset to single filter
        assert len(sbf.filters) == 1
    
    def test_get_stats_scalable(self):
        """Test getting statistics from scalable filter."""
        sbf = ScalableBloomFilter(initial_capacity=10, false_positive_rate=0.01)
        
        for i in range(50):
            sbf.add(f"item_{i}")
        
        stats = sbf.get_stats()
        
        assert isinstance(stats, dict)
        assert stats['num_filters'] > 0
        assert stats['total_items'] == 50
        assert stats['total_size_bytes'] > 0
        assert isinstance(stats['filters'], list)
    
    def test_repr_scalable(self):
        """Test string representation."""
        sbf = ScalableBloomFilter(initial_capacity=100)
        repr_str = repr(sbf)
        
        assert isinstance(repr_str, str)
        assert "ScalableBloomFilter" in repr_str


class TestBloomFilterPerformance:
    """Performance and stress tests for Bloom filters."""
    
    def test_large_scale_additions(self):
        """Test adding large number of items."""
        bf = BloomFilter(expected_elements=100000, false_positive_rate=0.001)
        
        start_time = time.time()
        
        for i in range(100000):
            bf.add(f"item_{i}")
        
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time (adjust based on hardware)
        assert elapsed < 10.0, f"Took too long: {elapsed}s"
        assert bf.num_items == 100000
    
    def test_large_scale_lookups(self):
        """Test looking up large number of items."""
        bf = BloomFilter(expected_elements=10000, false_positive_rate=0.01)
        
        # Add items
        for i in range(10000):
            bf.add(f"item_{i}")
        
        start_time = time.time()
        
        # Lookup all items
        for i in range(10000):
            assert f"item_{i}" in bf
        
        elapsed = time.time() - start_time
        
        # Lookups should be fast
        assert elapsed < 5.0, f"Lookups took too long: {elapsed}s"
    
    def test_serialization_performance(self):
        """Test serialization performance."""
        bf = BloomFilter(expected_elements=10000, false_positive_rate=0.01)
        
        for i in range(10000):
            bf.add(f"item_{i}")
        
        # Serialize
        start_time = time.time()
        data = bf.serialize()
        serialize_time = time.time() - start_time
        
        # Deserialize
        start_time = time.time()
        bf2 = BloomFilter.deserialize(data)
        deserialize_time = time.time() - start_time
        
        # Should be fast
        assert serialize_time < 1.0
        assert deserialize_time < 1.0
    
    def test_memory_efficiency(self):
        """Test memory efficiency compared to set."""
        import sys
        
        # Create a Bloom filter
        bf = BloomFilter(expected_elements=10000, false_positive_rate=0.01)
        for i in range(10000):
            bf.add(f"item_{i:06d}")
        
        # Create equivalent set
        item_set = set()
        for i in range(10000):
            item_set.add(f"item_{i:06d}")
        
        bf_size = len(bf.bit_array)
        set_size = sys.getsizeof(item_set) + sum(sys.getsizeof(item) for item in item_set)
        
        # Bloom filter should be significantly smaller
        assert bf_size < set_size * 0.5, \
            f"Bloom filter ({bf_size} bytes) not significantly smaller than set ({set_size} bytes)"


class TestBloomFilterEdgeCases:
    """Test edge cases and unusual scenarios."""
    
    def test_empty_strings(self):
        """Test with empty strings."""
        bf = BloomFilter(expected_elements=100, false_positive_rate=0.01)
        
        bf.add("")
        assert "" in bf
    
    def test_unicode_strings(self):
        """Test with Unicode strings."""
        bf = BloomFilter(expected_elements=100, false_positive_rate=0.01)
        
        items = ["你好", "مرحبا", "Привет", "🎉", "test™"]
        for item in items:
            bf.add(item)
        
        for item in items:
            assert item in bf
    
    def test_very_long_strings(self):
        """Test with very long strings."""
        bf = BloomFilter(expected_elements=10, false_positive_rate=0.01)
        
        long_string = "a" * 100000
        bf.add(long_string)
        
        assert long_string in bf
    
    def test_duplicate_additions(self):
        """Test adding the same item multiple times."""
        bf = BloomFilter(expected_elements=100, false_positive_rate=0.01)
        
        # Add same item multiple times
        for _ in range(10):
            bf.add("duplicate_item")
        
        # num_items should still increase (filter doesn't track uniqueness)
        assert bf.num_items == 10
        assert "duplicate_item" in bf
