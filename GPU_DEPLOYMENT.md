# GPU Deployment

This build keeps model weights and sample assets out of the repository and Docker image. The same image can be moved between GPU providers; persistent data is supplied through bind mounts.

For a RunPod-specific setup using a single Network Volume, see [RUNPOD_DEPLOYMENT.md](RUNPOD_DEPLOYMENT.md). Set `ALEXANDRIA_DATA_DIR` to the persistent volume directory so uploads, scripts, voices, LoRA adapters, and generated audio survive Pod replacement.

## Host layout

`docker-compose.yml` uses these host directories:

```text
data/
  models/       Qwen3-TTS model weights
  cache/        Hugging Face download cache
  config/       Web UI configuration
  final/        Final MP3 and M4B files
  uploads/      Uploaded books
  output/       Generated voice lines
  scripts/      Saved annotated scripts
  clone_voices/ Uploaded voice references
  lora_models/  Trained LoRA adapters
```

The approved model destinations shown in the **Models** tab are:

```text
/alexandria/models/qwen3-tts/1.7b-custom-voice
/alexandria/models/qwen3-tts/1.7b-base
/alexandria/models/qwen3-tts/1.7b-voice-design
```

Each installed directory must contain `config.json` and at least one `.safetensors` or `.bin` weight file.

## Start on a GPU host

1. Install Docker, Docker Compose, the NVIDIA driver, and NVIDIA Container Toolkit.
2. Copy this repository to the host. Do not add model weights to the repository.
3. Run `docker compose up --build -d`.
4. Open port `4200` through a private network or an authenticated reverse proxy.
5. Open **Models** and either start an administrator download or copy weights into `data/models` and press **Scan**.
6. Keep automatic model download disabled for controlled deployments. Enable it only when the container is allowed to access Hugging Face.

Set `HF_TOKEN` in the container environment only when a selected repository requires authentication. Do not place tokens in Git.

## Object storage

Set these variables on the GPU host before starting Compose:

| Variable | Purpose |
|---|---|
| `ALEXANDRIA_S3_BUCKET` | Required destination bucket |
| `ALEXANDRIA_S3_ENDPOINT` | S3-compatible endpoint; omit for AWS S3 |
| `ALEXANDRIA_S3_REGION` | Provider region when required |
| `ALEXANDRIA_S3_ACCESS_KEY_ID` | Access key or provider key ID |
| `ALEXANDRIA_S3_SECRET_ACCESS_KEY` | Secret key |
| `ALEXANDRIA_S3_PUBLIC_BASE_URL` | Optional CDN/public base URL returned to the order platform |
| `ALEXANDRIA_S3_PREFIX` | Object prefix, default `audiobooks` |

The **Result** tab publishes the selected MP3 or M4B plus a `manifest.json`. Credentials are read only from the server environment and are never returned to the browser. When no public base URL is configured, the result contains object keys for the order platform to sign or resolve itself.

## Capacity baseline

- GPU: NVIDIA with 16 GB VRAM recommended; 24 GB gives more comfortable batching.
- System RAM: 32 GB recommended.
- Persistent disk: start with 60 GB and expand for the content library.
- Container disk: 20 GB is generally sufficient because model weights and outputs use mounted storage.

The admin UI currently has no built-in authentication. Do not expose port `4200` directly to the public internet.
