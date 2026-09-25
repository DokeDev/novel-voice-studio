import json
import tempfile
import unittest
from pathlib import Path

from model_manager import MODEL_CATALOG, ModelDownloadError, ModelManager


class ModelManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = ModelManager(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _install_stub(self, model_key):
        path = self.manager.path_for(model_key)
        path.mkdir(parents=True)
        (path / "config.json").write_text(json.dumps({"model_type": "test"}))
        (path / "weights.safetensors").write_bytes(b"test-only")
        return path

    def test_catalog_starts_uninstalled_without_downloading(self):
        models = self.manager.list_models()
        self.assertEqual(len(models), len(MODEL_CATALOG))
        self.assertTrue(all(not model["installed"] for model in models))
        self.assertTrue(all(model["download_status"] == "idle" for model in models))

    def test_resolve_accepts_manually_installed_model(self):
        path = self._install_stub("qwen3_tts_base")
        self.assertEqual(self.manager.resolve("qwen3_tts_base"), str(path))

    def test_resolve_missing_model_does_not_download_by_default(self):
        with self.assertRaisesRegex(ModelDownloadError, "is not installed"):
            self.manager.resolve("qwen3_tts_custom_voice")

    def test_unknown_model_is_rejected(self):
        with self.assertRaisesRegex(ModelDownloadError, "Unknown or unapproved"):
            self.manager.path_for("arbitrary/repository")


if __name__ == "__main__":
    unittest.main()
