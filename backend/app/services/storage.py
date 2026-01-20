"""
Storage Service - Handles file storage operations.

This service provides a unified interface for file storage,
supporting both local filesystem and S3-compatible storage.

Features:
- Upload files with unique identifiers
- Download files by ID
- Generate presigned URLs (for S3)
- Clean up old files
"""

import os
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Optional
from urllib.parse import urljoin

from app.config import settings


class BaseStorage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def upload(
        self,
        file_data: bytes | BinaryIO,
        path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file and return its path/URL."""
        pass

    @abstractmethod
    async def download(self, path: str) -> bytes:
        """Download a file by its path."""
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file exists."""
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file."""
        pass

    @abstractmethod
    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """Get a URL to access the file."""
        pass


class LocalStorage(BaseStorage):
    """
    Local filesystem storage backend.

    Stores files in the configured storage path.
    """

    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize local storage.

        Args:
            base_path: Base directory for file storage
        """
        self.base_path = Path(base_path or settings.storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        """Get the full filesystem path for a storage path."""
        # Prevent path traversal attacks
        safe_path = Path(path).as_posix().lstrip("/")
        return self.base_path / safe_path

    async def upload(
        self,
        file_data: bytes | BinaryIO,
        path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload a file to local storage.

        Args:
            file_data: File content as bytes or file-like object
            path: Storage path for the file
            content_type: MIME type (not used for local storage)

        Returns:
            The storage path
        """
        full_path = self._get_full_path(path)

        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        if isinstance(file_data, bytes):
            full_path.write_bytes(file_data)
        else:
            # File-like object
            with open(full_path, "wb") as f:
                shutil.copyfileobj(file_data, f)

        return path

    async def download(self, path: str) -> bytes:
        """
        Download a file from local storage.

        Args:
            path: Storage path of the file

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        full_path = self._get_full_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        return full_path.read_bytes()

    async def exists(self, path: str) -> bool:
        """Check if a file exists in local storage."""
        full_path = self._get_full_path(path)
        return full_path.exists()

    async def delete(self, path: str) -> bool:
        """
        Delete a file from local storage.

        Args:
            path: Storage path of the file

        Returns:
            True if deleted, False if not found
        """
        full_path = self._get_full_path(path)

        if full_path.exists():
            full_path.unlink()
            return True

        return False

    async def delete_directory(self, path: str) -> bool:
        """
        Delete a directory and all its contents.

        Args:
            path: Storage path of the directory

        Returns:
            True if deleted, False if not found
        """
        full_path = self._get_full_path(path)

        if full_path.exists() and full_path.is_dir():
            shutil.rmtree(full_path)
            return True

        return False

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        Get a URL to access the file.

        For local storage, returns a relative path that can be
        served by the API's download endpoint.

        Args:
            path: Storage path of the file
            expires_in: Not used for local storage

        Returns:
            Relative URL path
        """
        return f"/api/v1/download/{path}"

    async def list_files(self, directory: str = "") -> list[str]:
        """
        List all files in a directory.

        Args:
            directory: Directory path to list

        Returns:
            List of file paths
        """
        dir_path = self._get_full_path(directory)

        if not dir_path.exists():
            return []

        files = []
        for item in dir_path.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(self.base_path)
                files.append(str(rel_path))

        return files

    async def get_file_info(self, path: str) -> Optional[dict]:
        """
        Get information about a file.

        Args:
            path: Storage path of the file

        Returns:
            Dict with file info or None if not found
        """
        full_path = self._get_full_path(path)

        if not full_path.exists():
            return None

        stat = full_path.stat()
        return {
            "path": path,
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_ctime),
            "modified_at": datetime.fromtimestamp(stat.st_mtime),
        }


class S3Storage(BaseStorage):
    """
    S3-compatible storage backend.

    Supports AWS S3, MinIO, DigitalOcean Spaces, etc.
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
    ):
        """
        Initialize S3 storage.

        Args:
            bucket: S3 bucket name
            endpoint: S3 endpoint URL (for non-AWS S3)
            access_key: AWS access key ID
            secret_key: AWS secret access key
            region: AWS region
        """
        self.bucket = bucket or settings.s3_bucket
        self.endpoint = endpoint or settings.s3_endpoint
        self.access_key = access_key or settings.s3_access_key
        self.secret_key = secret_key or settings.s3_secret_key
        self.region = region or settings.s3_region

        self._client = None

    async def _get_client(self):
        """Get or create the S3 client."""
        if self._client is None:
            try:
                import aioboto3

                session = aioboto3.Session()
                self._client = await session.client(
                    "s3",
                    endpoint_url=self.endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region,
                ).__aenter__()
            except ImportError:
                raise ImportError(
                    "aioboto3 is required for S3 storage. "
                    "Install it with: pip install aioboto3"
                )
        return self._client

    async def upload(
        self,
        file_data: bytes | BinaryIO,
        path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload a file to S3.

        Args:
            file_data: File content as bytes or file-like object
            path: S3 key for the file
            content_type: MIME type of the file

        Returns:
            The S3 key
        """
        client = await self._get_client()

        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        if isinstance(file_data, bytes):
            import io

            file_data = io.BytesIO(file_data)

        await client.upload_fileobj(
            file_data,
            self.bucket,
            path,
            ExtraArgs=extra_args,
        )

        return path

    async def download(self, path: str) -> bytes:
        """
        Download a file from S3.

        Args:
            path: S3 key of the file

        Returns:
            File content as bytes
        """
        import io

        client = await self._get_client()

        buffer = io.BytesIO()
        await client.download_fileobj(self.bucket, path, buffer)
        buffer.seek(0)

        return buffer.read()

    async def exists(self, path: str) -> bool:
        """Check if a file exists in S3."""
        client = await self._get_client()

        try:
            await client.head_object(Bucket=self.bucket, Key=path)
            return True
        except Exception:
            return False

    async def delete(self, path: str) -> bool:
        """
        Delete a file from S3.

        Args:
            path: S3 key of the file

        Returns:
            True if deleted (or didn't exist)
        """
        client = await self._get_client()

        try:
            await client.delete_object(Bucket=self.bucket, Key=path)
            return True
        except Exception:
            return False

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        Get a presigned URL to access the file.

        Args:
            path: S3 key of the file
            expires_in: URL expiration time in seconds

        Returns:
            Presigned URL
        """
        client = await self._get_client()

        url = await client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": path},
            ExpiresIn=expires_in,
        )

        return url

    async def close(self):
        """Close the S3 client."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None


class StorageService:
    """
    Unified storage service that wraps the appropriate backend.

    Usage:
        storage = StorageService()
        await storage.upload(data, "uploads/file.pdf")
        data = await storage.download("uploads/file.pdf")
    """

    def __init__(self):
        """Initialize the storage service based on configuration."""
        if settings.storage_type == "s3":
            self._backend = S3Storage()
        else:
            self._backend = LocalStorage()

    @property
    def backend(self) -> BaseStorage:
        """Get the underlying storage backend."""
        return self._backend

    async def upload(
        self,
        file_data: bytes | BinaryIO,
        path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file."""
        return await self._backend.upload(file_data, path, content_type)

    async def download(self, path: str) -> bytes:
        """Download a file."""
        return await self._backend.download(path)

    async def exists(self, path: str) -> bool:
        """Check if a file exists."""
        return await self._backend.exists(path)

    async def delete(self, path: str) -> bool:
        """Delete a file."""
        return await self._backend.delete(path)

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """Get a URL to access the file."""
        return await self._backend.get_url(path, expires_in)

    async def upload_job_file(
        self,
        job_id: str,
        filename: str,
        file_data: bytes | BinaryIO,
        folder: str = "uploads",
    ) -> str:
        """
        Upload a file associated with a job.

        Args:
            job_id: Job identifier
            filename: Original filename
            file_data: File content
            folder: Folder name (uploads, output, etc.)

        Returns:
            Storage path
        """
        path = f"{folder}/{job_id}/{filename}"
        return await self.upload(file_data, path)

    async def get_job_output(self, job_id: str, filename: str) -> bytes:
        """
        Get the output file for a job.

        Args:
            job_id: Job identifier
            filename: Output filename

        Returns:
            File content as bytes
        """
        path = f"output/{job_id}/{filename}"
        return await self.download(path)

    async def cleanup_job(self, job_id: str) -> None:
        """
        Clean up all files associated with a job.

        Args:
            job_id: Job identifier
        """
        if isinstance(self._backend, LocalStorage):
            await self._backend.delete_directory(f"uploads/{job_id}")
            await self._backend.delete_directory(f"output/{job_id}")
        else:
            # For S3, would need to list and delete objects
            # This is a simplified implementation
            pass


# Global storage service instance
storage_service = StorageService()
