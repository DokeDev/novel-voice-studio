"""Publish generated audiobook artifacts to S3-compatible object storage."""

import hashlib
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class ObjectStorageError(RuntimeError):
    pass


class ObjectStoragePublisher:
    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        region: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        public_base_url: Optional[str] = None,
        prefix: str = "audiobooks",
        client=None,
    ):
        if not bucket:
            raise ObjectStorageError("ALEXANDRIA_S3_BUCKET is not configured")
        self.bucket = bucket
        self.endpoint_url = endpoint_url or None
        self.region = region or None
        self.public_base_url = (public_base_url or "").rstrip("/")
        self.prefix = prefix.strip("/")
        self._client = client or self._create_client(access_key_id, secret_access_key)

    @classmethod
    def from_env(cls):
        return cls(
            bucket=os.environ.get("ALEXANDRIA_S3_BUCKET", ""),
            endpoint_url=os.environ.get("ALEXANDRIA_S3_ENDPOINT"),
            region=os.environ.get("ALEXANDRIA_S3_REGION"),
            access_key_id=os.environ.get("ALEXANDRIA_S3_ACCESS_KEY_ID"),
            secret_access_key=os.environ.get("ALEXANDRIA_S3_SECRET_ACCESS_KEY"),
            public_base_url=os.environ.get("ALEXANDRIA_S3_PUBLIC_BASE_URL"),
            prefix=os.environ.get("ALEXANDRIA_S3_PREFIX", "audiobooks"),
        )

    @staticmethod
    def configuration_status() -> dict:
        return {
            "configured": bool(os.environ.get("ALEXANDRIA_S3_BUCKET")),
            "bucket": os.environ.get("ALEXANDRIA_S3_BUCKET", ""),
            "endpoint": os.environ.get("ALEXANDRIA_S3_ENDPOINT", ""),
            "region": os.environ.get("ALEXANDRIA_S3_REGION", ""),
            "prefix": os.environ.get("ALEXANDRIA_S3_PREFIX", "audiobooks"),
            "public_base_url": os.environ.get("ALEXANDRIA_S3_PUBLIC_BASE_URL", ""),
        }

    def _create_client(self, access_key_id, secret_access_key):
        try:
            import boto3
        except ImportError as exc:
            raise ObjectStorageError("boto3 is required for object storage publishing") from exc

        kwargs = {}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.region:
            kwargs["region_name"] = self.region
        if access_key_id:
            kwargs["aws_access_key_id"] = access_key_id
        if secret_access_key:
            kwargs["aws_secret_access_key"] = secret_access_key
        return boto3.client("s3", **kwargs)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _key(self, book_id: str, filename: str) -> str:
        parts = [part for part in (self.prefix, book_id, filename) if part]
        return "/".join(parts)

    def _url(self, key: str) -> Optional[str]:
        if not self.public_base_url:
            return None
        return f"{self.public_base_url}/{key}"

    def publish(self, book_id: str, title: str, audio_path: str) -> dict:
        path = Path(audio_path).resolve()
        if not path.is_file():
            raise ObjectStorageError(f"Generated audio file not found: {path}")

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        audio_key = self._key(book_id, path.name)
        self._client.upload_file(
            str(path),
            self.bucket,
            audio_key,
            ExtraArgs={"ContentType": content_type},
        )

        manifest = {
            "schema_version": 1,
            "book_id": book_id,
            "title": title,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "audio": {
                "key": audio_key,
                "url": self._url(audio_key),
                "filename": path.name,
                "content_type": content_type,
                "bytes": path.stat().st_size,
                "sha256": self._sha256(path),
            },
        }
        manifest_key = self._key(book_id, "manifest.json")
        self._client.put_object(
            Bucket=self.bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        return {
            "bucket": self.bucket,
            "audio_key": audio_key,
            "audio_url": self._url(audio_key),
            "manifest_key": manifest_key,
            "manifest_url": self._url(manifest_key),
        }
