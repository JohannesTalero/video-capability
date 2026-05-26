"""
StorageAdapter — abstraction over Cloudflare R2 / AWS S3.
All pipeline components use this class. Never import boto3 directly elsewhere.
Changing storage provider = change only this file.
"""

import logging
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from pipeline.config import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    R2_ACCESS_KEY_ID,
    R2_BUCKET_NAME,
    R2_ENDPOINT_URL,
    R2_SECRET_KEY,
    S3_BUCKET_NAME,
    STORAGE_PROVIDER,
)

logger = logging.getLogger(__name__)


class StorageKeyNotFoundError(Exception):
    pass


class UploadVerificationError(Exception):
    pass


class StorageAdapter:
    """
    Unified interface for Cloudflare R2 and AWS S3.
    Uses the S3-compatible API (boto3) for both providers.
    """

    def __init__(self, provider: str | None = None):
        self._provider = provider or STORAGE_PROVIDER
        self._client, self._bucket = self._build_client()
        logger.info(f"StorageAdapter initialized: provider={self._provider}, bucket={self._bucket}")

    def _build_client(self):
        if self._provider == "r2":
            client = boto3.client(
                "s3",
                endpoint_url=R2_ENDPOINT_URL,
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_KEY,
                config=Config(signature_version="s3v4"),
                region_name="auto",
            )
            return client, R2_BUCKET_NAME
        elif self._provider == "s3":
            client = boto3.client(
                "s3",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION,
            )
            return client, S3_BUCKET_NAME
        else:
            raise ValueError(f"Unknown storage provider: {self._provider}. Use 'r2' or 's3'.")

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def upload(self, local_path: str | Path, remote_key: str) -> str:
        """
        Upload a local file to storage.
        Idempotent: uploading same key twice overwrites silently.
        Returns the remote_key on success.
        Raises UploadVerificationError if the file can't be verified after upload.
        """
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        if local_path.stat().st_size == 0:
            raise ValueError(f"File is empty (0 bytes): {local_path}")

        logger.info(f"Uploading {local_path} → s3://{self._bucket}/{remote_key}")
        self._client.upload_file(str(local_path), self._bucket, remote_key)

        # Verify the object actually landed
        if not self.exists(remote_key):
            raise UploadVerificationError(
                f"Upload appeared to succeed but key not found afterwards: {remote_key}"
            )

        logger.info(f"Upload verified: {remote_key} ({local_path.stat().st_size / 1024:.1f} KB)")
        return remote_key

    def upload_bytes(
        self, data: bytes, remote_key: str, content_type: str = "application/octet-stream"
    ) -> str:
        """Upload raw bytes (e.g., JSON state) to storage."""
        if not data:
            raise ValueError("Cannot upload empty bytes.")
        logger.info(f"Uploading {len(data)} bytes → {remote_key}")
        self._client.put_object(
            Bucket=self._bucket,
            Key=remote_key,
            Body=data,
            ContentType=content_type,
        )
        return remote_key

    def download(self, remote_key: str, local_path: str | Path) -> Path:
        """
        Download a file from storage to a local path.
        Creates parent directories if needed.
        Raises StorageKeyNotFoundError if key doesn't exist.
        """
        if not self.exists(remote_key):
            raise StorageKeyNotFoundError(f"Key not found in storage: {remote_key}")

        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading s3://{self._bucket}/{remote_key} → {local_path}")
        self._client.download_file(self._bucket, remote_key, str(local_path))

        if local_path.stat().st_size == 0:
            raise ValueError(f"Downloaded file is empty: {local_path}")

        logger.info(f"Download complete: {local_path} ({local_path.stat().st_size / 1024:.1f} KB)")
        return local_path

    def download_bytes(self, remote_key: str) -> bytes:
        """Download a file as raw bytes (e.g., JSON state)."""
        if not self.exists(remote_key):
            raise StorageKeyNotFoundError(f"Key not found in storage: {remote_key}")
        response = self._client.get_object(Bucket=self._bucket, Key=remote_key)
        return response["Body"].read()

    def exists(self, remote_key: str) -> bool:
        """Return True if the key exists in storage."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=remote_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    def delete(self, remote_key: str) -> None:
        """Delete a key from storage. No-op if key doesn't exist."""
        logger.info(f"Deleting: {remote_key}")
        self._client.delete_object(Bucket=self._bucket, Key=remote_key)

    def get_presigned_url(self, remote_key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for downloading a file."""
        if not self.exists(remote_key):
            raise StorageKeyNotFoundError(f"Key not found: {remote_key}")
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": remote_key},
            ExpiresIn=expires_in,
        )
        return url

    def list_prefix(self, prefix: str) -> list[str]:
        """List all keys under a given prefix."""
        paginator = self._client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def get_object_size_mb(self, remote_key: str) -> float:
        """Return file size in MB."""
        response = self._client.head_object(Bucket=self._bucket, Key=remote_key)
        return response["ContentLength"] / (1024 * 1024)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def upload_json(self, data: str, remote_key: str) -> str:
        """Upload a JSON string to storage."""
        return self.upload_bytes(data.encode("utf-8"), remote_key, content_type="application/json")

    def download_json(self, remote_key: str) -> str:
        """Download a JSON file and return as string."""
        return self.download_bytes(remote_key).decode("utf-8")
