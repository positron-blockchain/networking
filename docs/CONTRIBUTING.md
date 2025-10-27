# Contributing to Decentralized Network

Thank you for your interest in contributing! This document provides guidelines and information for contributors.

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive feedback
- Prioritize the project's goals and community

## Getting Started

### Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/yourusername/decentralized-network.git
   cd decentralized-network
   ```

2. **Install Dependencies**
   ```bash
   make dev-install
   # or
   pip install -r requirements.txt
   pip install -e ".[dev]"
   ```

3. **Run Tests**
   ```bash
   make test
   ```

4. **Try the Demo**
   ```bash
   make run-demo
   ```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test additions/improvements

### 2. Make Changes

- Write clean, readable code
- Follow PEP 8 style guidelines
- Add docstrings to functions and classes
- Keep functions focused and modular

### 3. Write Tests

- Add unit tests for new functionality
- Update integration tests if needed
- Ensure all tests pass: `make test`
- Aim for >80% code coverage

### 4. Format and Lint

```bash
make format  # Format with black
make lint    # Check with flake8 and mypy
```

### 5. Commit Changes

Write clear commit messages:
```bash
git commit -m "feat: add DHT implementation"
git commit -m "fix: resolve peer timeout issue"
git commit -m "docs: update API documentation"
```

Commit message prefixes:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `test:` - Tests
- `refactor:` - Code refactoring
- `perf:` - Performance improvement
- `chore:` - Maintenance tasks

### 6. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub with:
- Clear description of changes
- Link to related issues
- Test results
- Any breaking changes noted

## Code Style

### Python Style

Follow PEP 8 with these specifics:
- Maximum line length: 100 characters
- Use type hints where appropriate
- Use async/await for asynchronous code
- Prefer f-strings for formatting

Example:
```python
async def process_message(
    self,
    message: Message,
    sender_id: str,
    timeout: float = 10.0
) -> bool:
    """
    Process an incoming message.
    
    Args:
        message: The message to process
        sender_id: ID of the sender
        timeout: Processing timeout in seconds
        
    Returns:
        True if processed successfully
    """
    # Implementation
    pass
```

### Documentation

- All public APIs must have docstrings
- Use Google-style docstring format
- Include examples for complex functionality
- Keep README.md and ARCHITECTURE.md updated

### Testing

```python
import pytest
from positron_networking import Node, NetworkConfig

@pytest.mark.asyncio
async def test_feature():
    """Test description."""
    # Arrange
    node = Node(NetworkConfig())
    
    # Act
    result = await node.some_method()
    
    # Assert
    assert result is not None
```

## Areas for Contribution

### High Priority

1. **Performance Optimization**
   - Rust extensions for critical paths
   - Better caching strategies
   - Connection pooling improvements

2. **Features**
   - DHT implementation
   - NAT traversal
   - Enhanced Byzantine fault tolerance
   - Network visualization

3. **Testing**
   - More integration tests
   - Performance benchmarks
   - Chaos engineering tests
   - Security audits

4. **Documentation**
   - More examples
   - Video tutorials
   - API reference
   - Deployment guides

### Good First Issues

Look for issues tagged with `good-first-issue`:
- Documentation improvements
- Example scripts
- Test coverage
- Minor bug fixes

## Pull Request Process

1. **Before Submitting**
   - [ ] All tests pass
   - [ ] Code is formatted
   - [ ] Documentation is updated
   - [ ] CHANGELOG.md is updated (if applicable)

2. **PR Requirements**
   - Clear title and description
   - Link to related issue(s)
   - Test coverage maintained or improved
   - No merge conflicts

3. **Review Process**
   - At least one maintainer review required
   - Address review comments
   - Keep discussions constructive
   - Be patient with review time

4. **After Merge**
   - Delete your branch
   - Thank reviewers
   - Close related issues

## Testing Guidelines

### Unit Tests

Test individual components in isolation:
```python
def test_identity_generation():
    """Test that identity generation works."""
    identity = Identity.generate()
    assert identity.node_id is not None
```

### Integration Tests

Test component interactions:
```python
@pytest.mark.asyncio
async def test_two_node_connection():
    """Test that two nodes can connect."""
    node1 = await setup_node(port=8888)
    node2 = await setup_node(port=8889, bootstrap=["127.0.0.1:8888"])
    
    await asyncio.sleep(2)
    
    assert node1.peer_manager.get_peer(node2.node_id) is not None
```

### Performance Tests

Measure performance characteristics:
```python
async def test_message_throughput():
    """Test message throughput."""
    start = time.time()
    for i in range(1000):
        await node.broadcast({"data": i})
    duration = time.time() - start
    
    throughput = 1000 / duration
    assert throughput > 100  # messages/second
```

## Architecture Decisions

For significant changes, please:

1. Open an issue for discussion
2. Propose your approach
3. Get feedback from maintainers
4. Document the decision in ARCHITECTURE.md

Consider:
- Backward compatibility
- Performance impact
- Security implications
- Complexity vs. benefit

## Release Process

Maintainers follow this process:

1. Update version in `__init__.py` and `setup.py`
2. Update CHANGELOG.md
3. Create release tag: `git tag -a v0.1.0 -m "Release v0.1.0"`
4. Push tag: `git push origin v0.1.0`
5. Create GitHub release with notes
6. Build and upload to PyPI (if applicable)

## Questions?

- Open an issue for questions
- Join discussions in pull requests
- Check existing issues and PRs first

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in relevant documentation

Thank you for contributing to making decentralized networking better! 🎉
