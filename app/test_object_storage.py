import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from object_storage import ObjectStorageError, ObjectStoragePublisher


class FakeS3Client:
    def __init__(self):
        self.uploads = []
        self.objects = []

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.uploads.append((path, bucket, key, ExtraArgs))

    def put_object(self, **kwargs):
        self.objects.append(kwargs)


class ObjectStoragePublisherTest(unittest.TestCase):
    def test_configuration_status_does_not_expose_credentials(self):
        env = {
            "ALEXANDRIA_S3_BUCKET": "books",
            "ALEXANDRIA_S3_ACCESS_KEY_ID": "secret-id",
            "ALEXANDRIA_S3_SECRET_ACCESS_KEY": "secret-key",
        }
        with patch.dict(os.environ, env, clear=True):
            status = ObjectStoragePublisher.configuration_status()
        self.assertTrue(status["configured"])
        self.assertNotIn("access_key_id", status)
        self.assertNotIn("secret_access_key", status)

    def test_publish_uploads_audio_and_manifest(self):
        fake = FakeS3Client()
        publisher = ObjectStoragePublisher(
            bucket="books",
            public_base_url="https://media.example.com",
            prefix="library",
            client=fake,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "audiobook.m4b"
            audio.write_bytes(b"audio-content")
            result = publisher.publish("book-42", "Test Book", str(audio))

        self.assertEqual(result["audio_key"], "library/book-42/audiobook.m4b")
        self.assertEqual(result["audio_url"], "https://media.example.com/library/book-42/audiobook.m4b")
        self.assertEqual(fake.uploads[0][1:3], ("books", "library/book-42/audiobook.m4b"))
        manifest = json.loads(fake.objects[0]["Body"].decode("utf-8"))
        self.assertEqual(manifest["book_id"], "book-42")
        self.assertEqual(manifest["audio"]["bytes"], len(b"audio-content"))

    def test_bucket_is_required(self):
        with self.assertRaisesRegex(ObjectStorageError, "not configured"):
            ObjectStoragePublisher(bucket="", client=FakeS3Client())


if __name__ == "__main__":
    unittest.main()
