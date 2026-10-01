import os
import json
import re
import time
import tempfile


def get_data_root(default_root):
    """Return the persistent runtime data directory when one is configured."""
    configured = os.environ.get("ALEXANDRIA_DATA_DIR")
    root = configured if configured else default_root
    return os.path.abspath(os.path.expanduser(root))


def canonicalize_speaker_label(value):
    """Normalize common narrator label variants without changing character names."""
    label = str(value or "").strip()
    letters_only = re.sub(r"[^A-Z]", "", label.upper())
    if letters_only in {"NARRATOR", "NARRATION", "NARRATIVE"}:
        return "NARRATOR"
    return label


def atomic_json_write(data, target_path, max_retries=5):
    """Atomically write JSON data using a temp file and os.replace.

    Includes retry logic with exponential backoff for Windows file locking
    (Access is denied / file in use errors).
    """
    directory = os.path.dirname(target_path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        for attempt in range(max_retries):
            try:
                os.replace(tmp_path, target_path)
                return
            except OSError as e:
                if attempt < max_retries - 1 and (
                    e.errno == 5
                    or "Access is denied" in str(e)
                    or "being used by another process" in str(e)
                ):
                    delay = 0.05 * (2 ** attempt)
                    time.sleep(delay)
                    continue
                raise
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
