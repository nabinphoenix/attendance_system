from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class ProfileMediaUnavailable(RuntimeError):
    """Raised when profile-media storage cannot be reached."""


class ProfileMediaNotFound(FileNotFoundError):
    """Raised when a requested profile image no longer exists."""


@dataclass(frozen=True)
class ProfileMedia:
    content: bytes
    media_type: str


class ProfileMediaStore:
    """Persist profile images in S3, with a filesystem fallback for local use."""

    def __init__(
        self,
        *,
        bucket: str | None,
        prefix: str,
        local_directory: Path,
        region: str | None = None,
        s3_client: object | None = None,
    ) -> None:
        self.bucket = bucket.strip() if bucket else None
        self.prefix = prefix.strip("/")
        self.local_directory = local_directory
        self.region = region
        self._s3_client = s3_client

    @property
    def uses_s3(self) -> bool:
        return self.bucket is not None

    def save(self, avatar_key: str, content: bytes, media_type: str) -> None:
        if not self.uses_s3:
            self._save_local(avatar_key, content)
            return

        try:
            self._client().put_object(
                Bucket=self.bucket,
                Key=self._object_key(avatar_key),
                Body=content,
                ContentType=media_type,
                CacheControl="private, max-age=31536000, immutable",
            )
            return
        except (BotoCoreError, ClientError) as exc:
            # A bad bucket policy or temporary S3 outage should not prevent an
            # account holder from updating their photo on a single instance.
            # The managed state directory is also used when S3 is not set up.
            try:
                self._save_local(avatar_key, content)
            except ProfileMediaUnavailable as local_exc:
                raise ProfileMediaUnavailable("Profile image storage is temporarily unavailable") from local_exc

    def read(self, avatar_key: str) -> ProfileMedia:
        if not self.uses_s3:
            return self._read_local(avatar_key)

        try:
            response = self._client().get_object(Bucket=self.bucket, Key=self._object_key(avatar_key))
            body = response["Body"]
            try:
                content = body.read()
            finally:
                body.close()
            return ProfileMedia(content, response.get("ContentType") or _media_type_from_key(avatar_key))
        except ClientError as exc:
            return self._read_local_after_s3_failure(avatar_key, exc)
        except BotoCoreError as exc:
            return self._read_local_after_s3_failure(avatar_key, exc)

    def delete(self, avatar_key: str) -> None:
        if not self.uses_s3:
            self._delete_local(avatar_key)
            return

        try:
            self._client().delete_object(Bucket=self.bucket, Key=self._object_key(avatar_key))
        except (BotoCoreError, ClientError):
            # An old S3 object can be retried later; remove the fallback file
            # now so a newly uploaded profile image never shows a stale one.
            pass
        self._delete_local(avatar_key)

    def _save_local(self, avatar_key: str, content: bytes) -> None:
        try:
            self.local_directory.mkdir(parents=True, exist_ok=True)
            (self.local_directory / avatar_key).write_bytes(content)
        except OSError as exc:
            raise ProfileMediaUnavailable("Profile image storage is temporarily unavailable") from exc

    def _read_local(self, avatar_key: str) -> ProfileMedia:
        image_file = self.local_directory / avatar_key
        try:
            return ProfileMedia(image_file.read_bytes(), _media_type_from_key(avatar_key))
        except FileNotFoundError as exc:
            raise ProfileMediaNotFound from exc
        except OSError as exc:
            raise ProfileMediaUnavailable("Profile image storage is temporarily unavailable") from exc

    def _read_local_after_s3_failure(self, avatar_key: str, s3_error: Exception) -> ProfileMedia:
        try:
            return self._read_local(avatar_key)
        except ProfileMediaNotFound as local_exc:
            if isinstance(s3_error, ClientError) and str(s3_error.response.get("Error", {}).get("Code", "")) in {"404", "NoSuchKey", "NotFound"}:
                raise local_exc
            raise ProfileMediaUnavailable("Profile image storage is temporarily unavailable") from s3_error

    def _delete_local(self, avatar_key: str) -> None:
        try:
            (self.local_directory / avatar_key).unlink(missing_ok=True)
        except OSError as exc:
            raise ProfileMediaUnavailable("Profile image storage is temporarily unavailable") from exc

    def _client(self):
        if self._s3_client is None:
            self._s3_client = boto3.client("s3", region_name=self.region)
        return self._s3_client

    def _object_key(self, avatar_key: str) -> str:
        return f"{self.prefix}/{avatar_key}" if self.prefix else avatar_key


def _media_type_from_key(avatar_key: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(Path(avatar_key).suffix.lower(), "application/octet-stream")
