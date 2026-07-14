# Off-Grid Cinema: run the model LOCALLY with llama.cpp (GGUF)

This is the **no-cloud** path. Instead of the Modal/vLLM endpoint
(`cinema_serve.py`), you convert the fine-tuned Cinema model to **GGUF**, quantize
it to **Q4_K_M**, and serve it on **CPU** via `serve_llamacpp.py` (llama-cpp-python).
The LLM Cinema app talks to it through the same OpenAI-compatible contract it already
uses (`llm_client.py` -> `POST /v1/chat/completions`), so it is a drop-in.

Goal: earn the **llama.cpp** and **"off the grid"** badges — the whole director runs
on your machine, no GPU, no network.

---

## 0. Is MiniCPM3-4B GGUF-convertible? (Yes — with one caveat)

**Yes.** MiniCPM3 (`MiniCPM3ForCausalLM`, GGUF architecture id `minicpm3`) is a
first-class, supported architecture in llama.cpp. Proof points:

- OpenBMB publishes **official GGUFs**: `openbmb/MiniCPM3-4B-GGUF` ships
  `minicpm3-4b-fp16.gguf` and `minicpm3-4b-q4_k_m.gguf`, and the model card runs it
  with the one-liner `llama-server -hf openbmb/MiniCPM3-4B-GGUF:Q4_K_M`.
- `convert_hf_to_gguf.py` has a registered `MiniCPM3ForCausalLM` converter class
  (added to llama.cpp in late 2024, shortly after the model's 2024-09-05 release).

**Caveat — use a RECENT llama.cpp / llama-cpp-python.** At launch (Sept 2024) the
converter did **not** know MiniCPM3 and failed with
`Model MiniCPM3ForCausalLM is not supported` (see OpenBMB/MiniCPM issue #226). That
was fixed within weeks. So:

- Use a current `llama.cpp` checkout (for `convert_hf_to_gguf.py` + `llama-quantize`).
- Use `llama-cpp-python==0.3.2` or newer (pinned in `requirements-local.txt`) — the
  bundled llama.cpp must postdate the MiniCPM3 merge. Anything from the 0.2.x era is
  too old.

MiniCPM3 uses a custom attention variant; older runtimes that predate the merge will
also refuse to *load* the GGUF, so keeping both the converter and the runtime recent
matters.

### Fallback if MiniCPM3 ever misbehaves on your toolchain

The off-grid path does **not** depend on our fine-tune to demo the badges. If
conversion or loading fails on your platform, swap in any small llama.cpp-native
model and keep `serve_llamacpp.py` unchanged:

- **Qwen2.5-3B-Instruct GGUF** (e.g. `bartowski/Qwen2.5-3B-Instruct-GGUF`,
  `Q4_K_M`) — note `llm_client.py`'s default model is already
  `Qwen/Qwen2.5-3B-Instruct`, so prompts are tuned for that family.
- **Llama-3.2-3B-Instruct GGUF** — rock-solid llama.cpp support, ~2 GB at Q4_K_M.
- Or just pull our model's **official prebuilt GGUF** and skip conversion entirely:
  `huggingface-cli download openbmb/MiniCPM3-4B-GGUF minicpm3-4b-q4_k_m.gguf`
  (base MiniCPM3, not our fine-tune, but proves the local pipeline end to end).

Either way: `MODEL=<that>.gguf python serve_llamacpp.py` and you are off the grid.

---

## 1. Get the fp16 weights

Our merged fp16 weights live on the Modal volume `cinema-models` at `/models/cinema`
(see `cinema_serve.py`). Pull them down to a local folder, e.g. `./hf-cinema/`:

```bash
# from a machine with the Modal CLI configured
modal volume get cinema-models /cinema ./hf-cinema
```

You should end up with a standard HF directory: `config.json`,
`model-*.safetensors`, `tokenizer*`, etc. (`config.json` should say
`"architectures": ["MiniCPM3ForCausalLM"]`.)

---

## 2. Get a recent llama.cpp and convert HF -> GGUF (fp16)

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
pip install -r requirements.txt          # for the converter only

# Convert our fp16 HF weights to a single fp16 GGUF.
python convert_hf_to_gguf.py ../hf-cinema \
    --outfile ../models/cinema-f16.gguf \
    --outtype f16
```

If you see `Model MiniCPM3ForCausalLM is not supported`, your llama.cpp checkout is
too old — `git pull` to a current master and retry (see caveat in section 0).

---

## 3. Quantize to Q4_K_M

Q4_K_M is the sweet spot for a 4B on CPU: ~2.2 GB on disk, good quality.

```bash
# Build the quantize tool (one-time)
cmake -B build && cmake --build build --config Release -j

./build/bin/llama-quantize \
    ../models/cinema-f16.gguf \
    ../models/cinema-q4_k_m.gguf \
    Q4_K_M
```

You can delete `cinema-f16.gguf` afterward to save ~8 GB.

---

## 4. Serve it locally (CPU) and point the app at it

```bash
# in the claudemovies project dir
pip install -r requirements-local.txt

MODEL=./models/cinema-q4_k_m.gguf python serve_llamacpp.py
# -> Uvicorn running on http://0.0.0.0:8000
```

Sanity check the two routes the app uses:

```bash
curl http://localhost:8000/v1/models
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"cinema","messages":[{"role":"user","content":"hi"}],"max_tokens":32}'
```

Then run the LLM Cinema app against the local director:

```bash
export CLAUDEMOVIES_LLM_URL=http://localhost:8000/v1
export CLAUDEMOVIES_LLM_KEY=local        # any non-empty string; the local server ignores it
export CLAUDEMOVIES_LLM_MODEL=cinema
# ...then launch the app as usual
```

`llm_client.py` appends `/chat/completions` to the URL and reads
`choices[0].message.content`; `serve_llamacpp.py` returns exactly that shape, so no
app code changes are needed.

### serve_llamacpp.py env knobs

| Env          | Default        | Notes                                  |
|--------------|----------------|----------------------------------------|
| `MODEL`      | (required)     | path to the local `.gguf`              |
| `HOST`       | `0.0.0.0`      | bind host                              |
| `PORT`       | `8000`         | bind port                             |
| `N_CTX`      | `4096`         | context window (matches the vLLM serve)|
| `N_THREADS`  | all CPU cores  | generation threads                     |
| `SERVED_NAME`| `cinema`       | id reported by `/v1/models`            |

---

## 5. Running it inside a Hugging Face Space (cpu-basic) — honest caveats

You can run this whole thing in a **free `cpu-basic` Space** (2 vCPU, 16 GB RAM) to
earn the off-grid badge with zero paid GPU. It works, but be honest about the speed:

- **RAM:** Q4_K_M of a 4B is ~2.2 GB on disk and roughly **3-4 GB resident** with a
  4k context. That fits comfortably in 16 GB. fp16 (~8 GB) also fits but is slower —
  always serve the **quantized** GGUF on CPU.
- **Speed:** on 2 shared vCPUs expect roughly **2-6 tokens/sec**. A typical Cinema
  generation (a few hundred tokens) takes on the order of **30-90 seconds**. This is
  fine for a "generate a movie" button, painful for chat. Keep `max_tokens` modest.
- **Cold start:** loading the GGUF into RAM takes ~10-30 s on first request.
- Set `N_THREADS=2` (or leave default; `os.cpu_count()` on cpu-basic returns ~2).

Sketch of a Space setup (a separate Space that hosts the director, or the same Space
that runs the app — `serve_llamacpp.py` can run in the background):

1. `requirements.txt` for the Space = contents of `requirements-local.txt` (plus
   whatever the app needs).
2. On startup, fetch the GGUF once (don't commit a 2 GB file to git; use the Hub):
   ```python
   from huggingface_hub import hf_hub_download
   gguf = hf_hub_download("openbmb/MiniCPM3-4B-GGUF", "minicpm3-4b-q4_k_m.gguf")
   # or your own repo holding cinema-q4_k_m.gguf
   ```
3. Launch `serve_llamacpp.py` with `MODEL=<that path>` and set
   `CLAUDEMOVIES_LLM_URL=http://localhost:8000/v1` for the app process.

> Tip: upload your quantized `cinema-q4_k_m.gguf` to a (public) HF model repo and
> `hf_hub_download` it at boot — Spaces have ephemeral disk, so re-downloading or
> caching it in the persistent layer beats committing it.

---

## Summary

- **MiniCPM3-4B is GGUF-convertible and llama.cpp-runnable today** — it is an
  officially supported architecture (`minicpm3`) with official OpenBMB GGUFs. The
  only real risk is using a stale llama.cpp/llama-cpp-python from before the late-2024
  merge; pin recent versions.
- Convert fp16 -> GGUF (`convert_hf_to_gguf.py`), quantize to **Q4_K_M**, serve on
  CPU with `serve_llamacpp.py`, and set `CLAUDEMOVIES_LLM_URL` to it.
- Runs in a free HF **cpu-basic** Space (~3-4 GB RAM, ~2-6 tok/s) — slow but real,
  fully off the grid.
- If MiniCPM3 ever breaks on your toolchain, drop in a Qwen2.5-3B or Llama-3.2-3B
  GGUF with no changes to `serve_llamacpp.py`.
```
