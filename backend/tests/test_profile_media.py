from io import BytesIO
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from app.core.profile_media import ProfileMediaNotFound, ProfileMediaStore


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}

    def put_object(self, **kwargs) -> None:
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = {
            "Body": kwargs["Body"],
            "ContentType": kwargs["ContentType"],
            "CacheControl": kwargs["CacheControl"],
        }

    def get_object(self, *, Bucket: str, Key: str):
        try:
            item = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject") from exc
        return {"Body": BytesIO(item["Body"]), "ContentType": item["ContentType"]}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


def test_s3_profile_media_store_uses_private_prefix(tmp_path: Path) -> None:
    client = FakeS3()
    store = ProfileMediaStore(
        bucket="profile-media-bucket",
        prefix="profile-media",
        local_directory=tmp_path,
        s3_client=client,
    )

    store.save("avatar.png", b"image-bytes", "image/png")

    assert client.objects[("profile-media-bucket", "profile-media/avatar.png")]["CacheControl"] == "private, max-age=31536000, immutable"
    image = store.read("avatar.png")
    assert image.content == b"image-bytes"
    assert image.media_type == "image/png"

    store.delete("avatar.png")
    with pytest.raises(ProfileMediaNotFound):
        store.read("avatar.png")
