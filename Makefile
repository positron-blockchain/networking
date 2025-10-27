.PHONY: install test clean lint run-demo help

help:
	@echo "Decentralized Network - Makefile Commands"
	@echo "=========================================="
	@echo ""
	@echo "  make install     - Install dependencies and package"
	@echo "  make test        - Run all tests"
	@echo "  make test-unit   - Run unit tests only"
	@echo "  make test-int    - Run integration tests only"
	@echo "  make coverage    - Run tests with coverage report"
	@echo "  make lint        - Run code linters"
	@echo "  make clean       - Clean up generated files"
	@echo "  make run-demo    - Run quick start demo"
	@echo "  make format      - Format code with black"
	@echo ""

install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt
	pip install -e .
	@echo "✓ Installation complete!"

test:
	@echo "Running all tests..."
	pytest tests/ -v

test-unit:
	@echo "Running unit tests..."
	pytest tests/test_identity.py tests/test_protocol.py -v

test-int:
	@echo "Running integration tests..."
	pytest tests/test_integration.py -v

coverage:
	@echo "Running tests with coverage..."
	pytest tests/ --cov=decentralized_network --cov-report=html --cov-report=term
	@echo "✓ Coverage report generated in htmlcov/"

lint:
	@echo "Running linters..."
	flake8 src/ --max-line-length=100 --exclude=__pycache__
	mypy src/ --ignore-missing-imports

format:
	@echo "Formatting code..."
	black src/ tests/ examples/

clean:
	@echo "Cleaning up..."
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache/ .coverage htmlcov/
	rm -rf __pycache__/ */__pycache__/ */*/__pycache__/
	rm -rf demo_data/ sim_data/ node_data/
	rm -rf keys/ *.db *.log
	find . -name "*.pyc" -delete
	@echo "✓ Cleanup complete!"

run-demo:
	@echo "Starting demo network..."
	python quickstart.py

dev-install:
	@echo "Installing development dependencies..."
	pip install -r requirements.txt
	pip install -e ".[dev]"
	@echo "✓ Development setup complete!"
