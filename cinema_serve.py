"""
Serve the fine-tuned Cinema model (MiniCPM3-4B) from the cinema-models volume as an
OpenAI-compatible endpoint (vLLM), so the LLM Cinema app runs on OUR small model.

    companion/.venv/bin/modal deploy claudemovies/cinema_serve.py

Then point the app at it:
    CLAUDEMOVIES_LLM_URL = https://<your-endpoint>/v1
    CLAUDEMOVIES_LLM_KEY = <your bearer key>
    CLAUDEMOVIES_LLM_MODEL = cinema

Scales to zero when idle. The bearer key comes from the companion-api-key secret.
"""

import os
import subprocess

import modal

MODEL_PATH = "/models/cinema"     # merged model saved by modal_finetune on the volume
SERVED_NAME = "cinema"
PORT = 8000

app = modal.App("cinema-serve")

vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.6.6.post1",
        "transformers==4.47.1",
        "huggingface_hub[hf_transfer]==0.26.5",
        "datamodel-code-generator",          # MiniCPM3 tokenizer dependency
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_FLASHINFER_SAMPLER": "0"})
)

hf_cache = modal.Volume.from_name("companion-hf-cache", create_if_missing=True)
models_vol = modal.Volume.from_name("cinema-models", create_if_missing=True)


@app.function(
    image=vllm_image,
    gpu="A10G",
    secrets=[modal.Secret.from_name("huggingface-secret"),
             modal.Secret.from_name("companion-api-key")],
    volumes={"/root/.cache/huggingface": hf_cache, "/models": models_vol},
    timeout=30 * 60,
    scaledown_window=15 * 60,
    # judging day: add min_containers=1 here (and redeploy) to skip cold starts
    # entirely — remember to remove it after, it bills GPU time around the clock
)
@modal.web_server(port=PORT, startup_timeout=15 * 60)
def serve():
    api_key = os.environ["COMPANION_API_KEY"]            # from the secret, never code
    subprocess.Popen([
        "vllm", "serve", MODEL_PATH,
        "--served-model-name", SERVED_NAME,
        "--trust-remote-code",                           # MiniCPM3 custom modeling/tokenizer
        "--host", "0.0.0.0", "--port", str(PORT),
        "--api-key", api_key,
        "--max-model-len", "4096",
        "--gpu-memory-utilization", "0.90",
    ])
