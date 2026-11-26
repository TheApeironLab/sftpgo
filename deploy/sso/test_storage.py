import os
import ssl
import unittest
from unittest.mock import patch

# The production directory CA is mounted by the Chart.
with patch.object(ssl, "create_default_context", wraps=lambda **kwargs: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)):
    from sync import account


class StorageMappingTests(unittest.TestCase):
    @patch.dict(os.environ, S3_ENDPOINT="http://storage.example.internal")
    def test_credentials_follow_their_bucket(self):
        personal = {"accessKey": "personal", "secretKey": "one"}
        team = {"accessKey": "team", "secretKey": "two"}
        for shared_keys in (None, team):
            with self.subTest(shared_keys=shared_keys):
                folders = account("subject", "files-personal", "files-team", personal, shared_keys)["virtual_folders"]
                self.assertEqual(
                    [(folder["filesystem"]["s3config"]["bucket"],
                      folder["filesystem"]["s3config"]["access_key"],
                      folder["filesystem"]["s3config"]["access_secret"]["payload"]) for folder in folders],
                    [("files-personal", "personal", "one"),
                     ("files-team", "team", "two") if shared_keys else ("files-team", "personal", "one")],
                )
