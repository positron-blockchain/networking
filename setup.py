from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="positron-networking",
    version="0.1.0",
    author="Positron Blockchain Team",
    description="Production-ready decentralized P2P networking layer with packet-based transport, gossip protocol, trust management, and cryptographic identity",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/positron-blockchain/networking",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: System :: Networking",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "cryptography>=41.0.0",
        "pynacl>=1.5.0",
        "msgpack>=1.0.7",
        "aiofiles>=23.2.1",
        "asyncio-throttle>=1.0.1",
        "aiosqlite>=0.19.0",
        "click>=8.1.7",
        "rich>=13.7.0",
        "structlog>=23.2.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "pytest-cov>=4.1.0",
            "black>=23.12.0",
            "mypy>=1.7.1",
            "flake8>=6.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "positron-net=positron_networking.cli:main",
        ],
    },
)
