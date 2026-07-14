"""
Off-grid director: serve the fine-tuned Cinema model LOCALLY via llama.cpp (GGUF).

No cloud, no GPU. This is a tiny OpenAI-compatible server (FastAPI + llama-cpp-python)
that loads a local GGUF and exposes exactly the two routes llm_client.py touches:

    POST /v1/chat/completions   -> {"choices": [{"message": {"content": ...}}]}
    GET  /v1/models             -> {"data": [{"id": ...}]}

It is a drop-in for CLAUDEMOVIES_LLM_URL. Point the app at it:

    export CLAUDEMOVIES_LLM_URL=http://localhost:8000/v1
    export CLAUDEMOVIES_LLM_KEY=local            # any non-empty string; not checked
    export CLAUDEMOVIES_LLM_MODEL=cinema

Run it (after converting/quantizing per LOCAL_LLAMACPP.md):

    pip install -r requirements-local.txt
    MODEL=./models/cinema-q4_k_m.gguf python serve_llamacpp.py

Config via env:
    MODEL          path to the local .gguf            (required)
    HOST           bind host                          (default 0.0.0.0)
    PORT           bind port                          (default 8000)
    N_CTX          context window                     (default 4096)
    N_THREADS      CPU threads (default: all cores)
    SERVED_NAME    id reported by /v1/models          (default cinema)

This file intentionally has NO cloud dependencies. Everything runs on CPU.
"""

import os
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from llama_cpp import Llama

MODEL_PATH = os.environ.get("MODEL", "")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
N_CTX = int(os.environ.get("N_CTX", "4096"))
N_THREADS = int(os.environ["N_THREADS"]) if os.environ.get("N_THREADS") else (os.cpu_count() or 4)
SERVED_NAME = os.environ.get("SERVED_NAME", "cinema")

if not MODEL_PATH:
    raise SystemExit(
        "Set MODEL to a local .gguf path, e.g.\n"
        "    MODEL=./models/cinema-q4_k_m.gguf python serve_llamacpp.py\n"
        "See LOCAL_LLAMACPP.md to produce the GGUF from the fp16 weights."
    )
if not os.path.exists(MODEL_PATH):
    raise SystemExit(f"MODEL not found: {MODEL_PATH}")

# Load once at startup. chat_format=None lets llama.cpp use the GGUF's built-in
# chat template (MiniCPM3 ships one); we pass messages straight through.
print(f"[serve_llamacpp] loading {MODEL_PATH}  (n_ctx={N_CTX}, threads={N_THREADS})")
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=N_CTX,
    n_threads=N_THREADS,
    n_gpu_layers=0,          # CPU only -> off the grid
    verbose=False,
)

app = FastAPI(title="claudemovies local llama.cpp director")


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{"id": SERVED_NAME, "object": "model", "owned_by": "local-llamacpp"}],
    }


# Some clients probe /health; harmless to provide.
@app.get("/health")
def health():
    return {"status": "ok", "model": SERVED_NAME}


@app.post("/v1/chat/completions")
async def chat_completions(request: dict):
    """Mirror the OpenAI chat-completions shape that llm_client.llm() parses:
    it reads choices[0].message.content. We honor model/messages/max_tokens/temperature."""
    messages = request.get("messages", [])
    max_tokens = int(request.get("max_tokens", 600))
    temperature = float(request.get("temperature", 0.8))

    try:
        out = llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = out["choices"][0]["message"]["content"]
        usage = out.get("usage", {})
    except Exception as exc:  # surface errors as a 500 the client can see
        return JSONResponse(status_code=500, content={"error": {"message": str(exc)}})

    return {
        "id": "chatcmpl-" + uuid.uuid4().hex,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.get("model", SERVED_NAME),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": out["choices"][0].get("finish_reason", "stop"),
            }
        ],
        "usage": usage,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
