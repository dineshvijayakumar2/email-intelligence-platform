"""Storage adapters for handling files from multiple sources"""
from .storage_adapter import (
    StorageAdapter,
    StorageManager,
    LocalStorageAdapter,
    GoogleDriveAdapter,
    S3StorageAdapter,
)

__all__ = [
    'StorageAdapter',
    'StorageManager',
    'LocalStorageAdapter',
    'GoogleDriveAdapter',
    'S3StorageAdapter',
]
