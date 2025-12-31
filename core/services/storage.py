"""Storage Service - Abstract storage backend for local and S3.

Provides a unified interface for file storage that can use:
- Local filesystem (default)
- Amazon S3 or compatible services (when configured)
"""

import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional

try:
    import boto3
    from botocore.exceptions import ClientError

    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False


@dataclass
class StoredFile:
    """Information about a stored file."""

    key: str  # Storage key/path
    url: str  # Public URL
    size: int
    content_type: str
    last_modified: datetime | None = None


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def put(
        self,
        key: str,
        data: BinaryIO,
        content_type: str = None,
        metadata: dict = None,
    ) -> StoredFile:
        """Store a file."""
        pass

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Get file contents."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a file."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if file exists."""
        pass

    @abstractmethod
    def get_url(self, key: str) -> str:
        """Get public URL for file."""
        pass


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, upload_dir: str, base_url: str = "/uploads"):
        self.upload_dir = Path(upload_dir)
        self.base_url = base_url.rstrip("/")
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def put(
        self,
        key: str,
        data: BinaryIO,
        content_type: str = None,
        metadata: dict = None,
    ) -> StoredFile:
        """Store file to local filesystem."""
        file_path = self.upload_dir / key

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        content = data.read()
        file_path.write_bytes(content)

        # Determine content type
        if not content_type:
            content_type, _ = mimetypes.guess_type(key)
            content_type = content_type or "application/octet-stream"

        return StoredFile(
            key=key,
            url=self.get_url(key),
            size=len(content),
            content_type=content_type,
            last_modified=utcnow(),
        )

    async def get(self, key: str) -> bytes | None:
        """Get file from local filesystem."""
        file_path = self.upload_dir / key
        if not file_path.exists():
            return None
        return file_path.read_bytes()

    async def delete(self, key: str) -> bool:
        """Delete file from local filesystem."""
        file_path = self.upload_dir / key
        if not file_path.exists():
            return False
        file_path.unlink()
        return True

    async def exists(self, key: str) -> bool:
        """Check if file exists."""
        return (self.upload_dir / key).exists()

    def get_url(self, key: str) -> str:
        """Get URL for local file."""
        return f"{self.base_url}/{key}"


class S3StorageBackend(StorageBackend):
    """Amazon S3 storage backend."""

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        access_key: str = None,
        secret_key: str = None,
        endpoint_url: str = None,
        public_url: str = None,
        prefix: str = "",
    ):
        if not S3_AVAILABLE:
            raise ImportError("boto3 is required for S3 storage")

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.public_url = public_url

        # Initialize S3 client
        config = {
            "region_name": region,
        }
        if access_key and secret_key:
            config["aws_access_key_id"] = access_key
            config["aws_secret_access_key"] = secret_key
        if endpoint_url:
            config["endpoint_url"] = endpoint_url

        self.client = boto3.client("s3", **config)

    def _full_key(self, key: str) -> str:
        """Get full key with prefix."""
        if self.prefix:
            return f"{self.prefix}/{key}"
        return key

    async def put(
        self,
        key: str,
        data: BinaryIO,
        content_type: str = None,
        metadata: dict = None,
    ) -> StoredFile:
        """Upload file to S3."""
        full_key = self._full_key(key)

        # Determine content type
        if not content_type:
            content_type, _ = mimetypes.guess_type(key)
            content_type = content_type or "application/octet-stream"

        # Read data
        content = data.read()

        # Upload to S3
        extra_args = {
            "ContentType": content_type,
        }
        if metadata:
            extra_args["Metadata"] = metadata

        self.client.put_object(
            Bucket=self.bucket,
            Key=full_key,
            Body=content,
            **extra_args,
        )

        return StoredFile(
            key=key,
            url=self.get_url(key),
            size=len(content),
            content_type=content_type,
            last_modified=utcnow(),
        )

    async def get(self, key: str) -> bytes | None:
        """Download file from S3."""
        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=self._full_key(key),
            )
            return response["Body"].read()
        except ClientError:
            return None

    async def delete(self, key: str) -> bool:
        """Delete file from S3."""
        try:
            self.client.delete_object(
                Bucket=self.bucket,
                Key=self._full_key(key),
            )
            return True
        except ClientError:
            return False

    async def exists(self, key: str) -> bool:
        """Check if file exists in S3."""
        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=self._full_key(key),
            )
            return True
        except ClientError:
            return False

    def get_url(self, key: str) -> str:
        """Get public URL for S3 file."""
        if self.public_url:
            return f"{self.public_url.rstrip('/')}/{self._full_key(key)}"
        return f"https://{self.bucket}.s3.amazonaws.com/{self._full_key(key)}"


class StorageService:
    """
    Unified storage service.

    Automatically selects local or S3 backend based on configuration.

    Usage:
        storage = StorageService()

        # Store file
        with open("image.jpg", "rb") as f:
            result = await storage.put("images/photo.jpg", f)
            print(result.url)

        # Get file
        data = await storage.get("images/photo.jpg")

        # Delete file
        await storage.delete("images/photo.jpg")
    """

    _instance: Optional["StorageService"] = None
    _backend: StorageBackend | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def configure(
        self,
        backend: str = "local",
        **kwargs,
    ) -> None:
        """
        Configure storage backend.

        Args:
            backend: "local" or "s3"
            **kwargs: Backend-specific configuration
        """
        if backend == "s3":
            self._backend = S3StorageBackend(**kwargs)
        else:
            upload_dir = kwargs.get("upload_dir", "uploads")
            base_url = kwargs.get("base_url", "/uploads")
            self._backend = LocalStorageBackend(upload_dir, base_url)

    @property
    def backend(self) -> StorageBackend:
        if self._backend is None:
            # Default to local storage
            self._backend = LocalStorageBackend("uploads")
        return self._backend

    async def put(
        self,
        key: str,
        data: BinaryIO,
        content_type: str = None,
        metadata: dict = None,
    ) -> StoredFile:
        return await self.backend.put(key, data, content_type, metadata)

    async def get(self, key: str) -> bytes | None:
        return await self.backend.get(key)

    async def delete(self, key: str) -> bool:
        return await self.backend.delete(key)

    async def exists(self, key: str) -> bool:
        return await self.backend.exists(key)

    def get_url(self, key: str) -> str:
        return self.backend.get_url(key)


# Global storage instance
storage_service = StorageService()
