import os
import tempfile
import unittest
from unittest.mock import patch

from utils import canonicalize_speaker_label, get_data_root


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


if __name__ == "__main__":
    unittest.main()
