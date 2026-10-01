import os
import tempfile
import unittest
from unittest.mock import patch

from utils import canonicalize_speaker_label, get_data_root, resolve_data_path, stable_seed


class RuntimeUtilsTests(unittest.TestCase):
    def test_data_root_prefers_environment_override(self):
        with tempfile.TemporaryDirectory() as configured:
            with patch.dict(os.environ, {"ALEXANDRIA_DATA_DIR": configured}):
                self.assertEqual(get_data_root("/fallback"), os.path.abspath(configured))

    def test_data_root_uses_default_without_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_data_root("relative-data"), os.path.abspath("relative-data"))

    def test_narrator_variants_are_canonicalized(self):
        for label in ("NARRATOR", "Narrator", "NARR.ATOR", "narration", "NARRATIVE"):
            self.assertEqual(canonicalize_speaker_label(label), "NARRATOR")

    def test_character_names_are_preserved(self):
        self.assertEqual(canonicalize_speaker_label(" 顾言 "), "顾言")

    def test_stable_seed_is_reproducible_and_role_specific(self):
        self.assertEqual(stable_seed("顾言"), stable_seed("顾言"))
        self.assertNotEqual(stable_seed("顾言"), stable_seed("程野"))
        self.assertGreaterEqual(stable_seed("顾言"), 0)

    def test_relative_asset_paths_use_runtime_data_root(self):
        with tempfile.TemporaryDirectory() as root:
            expected = os.path.join(root, "designed_voices", "voice.wav")
            self.assertEqual(
                resolve_data_path("designed_voices/voice.wav", root),
                expected,
            )

    def test_absolute_asset_paths_are_preserved(self):
        path = "/workspace/alexandria/designed_voices/voice.wav"
        self.assertEqual(resolve_data_path(path, "/other/root"), path)

    def test_relative_asset_path_can_fall_back_to_legacy_root(self):
        with tempfile.TemporaryDirectory() as data_root, tempfile.TemporaryDirectory() as legacy_root:
            legacy_dir = os.path.join(legacy_root, "designed_voices")
            os.makedirs(legacy_dir)
            legacy_path = os.path.join(legacy_dir, "voice.wav")
            with open(legacy_path, "wb") as f:
                f.write(b"test")
            self.assertEqual(
                resolve_data_path(
                    "designed_voices/voice.wav",
                    data_root,
                    fallback_root=legacy_root,
                ),
                legacy_path,
            )


if __name__ == "__main__":
    unittest.main()
