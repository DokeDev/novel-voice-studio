"""Portable local model registry with optional administrator downloads."""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Optional


MODEL_CATALOG = {
    "qwen3_tts_custom_voice": {
        "name": "Qwen3-TTS 1.7B CustomVoice",
        "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "relative_path": "qwen3-tts/1.7b-custom-voice",
        "purpose": "Built-in voices and instruction-controlled speech",
        "license": "Apache-2.0",
    },
    "qwen3_tts_base": {
        "name": "Qwen3-TTS 1.7B Base",
        "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "relative_path": "qwen3-tts/1.7b-base",
        "purpose": "Voice cloning and LoRA voices",
        "license": "Apache-2.0",
    },
    "qwen3_tts_voice_design": {
        "name": "Qwen3-TTS 1.7B VoiceDesign",
        "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        "relative_path": "qwen3-tts/1.7b-voice-design",
        "purpose": "Create reusable voices from text descriptions",
        "license": "Apache-2.0",
    },
}


class ModelDownloadError(RuntimeError):
    pass


class ModelManager:
    """Manage allow-listed model assets in a mounted directory."""

    def __init__(self, root_dir: Optional[str] = None, auto_download: bool = False):
        configured_root = root_dir or os.environ.get("ALEXANDRIA_MODELS_DIR", "models")
        self.root_dir = Path(configured_root).expanduser().resolve()
        self.auto_download = auto_download
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._downloads: dict[str, dict] = {}

    def _entry(self, model_key: str) -> dict:
        try:
            return MODEL_CATALOG[model_key]
        except KeyError as exc:
            raise ModelDownloadError(f"Unknown or unapproved model: {model_key}") from exc

    def path_for(self, model_key: str) -> Path:
        entry = self._entry(model_key)
        path = (self.root_dir / entry["relative_path"]).resolve()
        if self.root_dir not in path.parents:
            raise ModelDownloadError("Model path escapes the configured model directory")
        return path

    @staticmethod
    def is_valid_model_dir(path: Path) -> bool:
        if not path.is_dir() or not (path / "config.json").is_file():
            return False
        return any(path.rglob("*.safetensors")) or any(path.rglob("*.bin"))

    def list_models(self) -> list[dict]:
        result = []
        for key, entry in MODEL_CATALOG.items():
            path = self.path_for(key)
            download = self._downloads.get(key, {})
            result.append({
                "id": key,
                **entry,
                "path": str(path),
                "installed": self.is_valid_model_dir(path),
                "download_status": download.get("status", "idle"),
                "download_error": download.get("error"),
            })
        return result

    def resolve(self, model_key: str, allow_download: Optional[bool] = None) -> str:
        path = self.path_for(model_key)
        if self.is_valid_model_dir(path):
            return str(path)

        should_download = self.auto_download if allow_download is None else allow_download
        if not should_download:
            raise ModelDownloadError(
                f"Model '{model_key}' is not installed in {path}. "
                "Install it from model management or copy it into that directory."
            )

        self.download(model_key)
        return str(path)

    def download(self, model_key: str) -> str:
        entry = self._entry(model_key)
        target = self.path_for(model_key)
        if self.is_valid_model_dir(target):
            return str(target)
        if target.exists():
            raise ModelDownloadError(
                f"Incomplete model directory already exists: {target}. "
                "Complete the manual installation or move it aside before retrying."
            )

        partial = target.with_name(f".{target.name}.partial")
        if partial.exists():
            shutil.rmtree(partial)
        partial.parent.mkdir(parents=True, exist_ok=True)

        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=entry["repo_id"],
                revision=entry.get("revision"),
                local_dir=str(partial),
                token=os.environ.get("HF_TOKEN") or None,
            )
            if not self.is_valid_model_dir(partial):
                raise ModelDownloadError("Downloaded files failed model validation")
            os.replace(partial, target)
            return str(target)
        except Exception as exc:
            if partial.exists():
                shutil.rmtree(partial, ignore_errors=True)
            if isinstance(exc, ModelDownloadError):
                raise
            raise ModelDownloadError(str(exc)) from exc

    def start_download(self, model_key: str) -> dict:
        self._entry(model_key)
        with self._lock:
            current = self._downloads.get(model_key, {})
            if current.get("status") == "downloading":
                return current
            state = {"status": "downloading", "error": None}
            self._downloads[model_key] = state

        def run():
            try:
                path = self.download(model_key)
                final_state = {"status": "installed", "error": None, "path": path}
            except Exception as exc:
                final_state = {"status": "error", "error": str(exc)}
            with self._lock:
                self._downloads[model_key] = final_state

        threading.Thread(target=run, name=f"model-download-{model_key}", daemon=True).start()
        return state
