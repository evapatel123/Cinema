# Deploy LLM Cinema to a Hugging Face Space (under the hackathon org)

Everything below runs from the `claudemovies/` folder. You need to be logged into HF
(`hf auth login` — paste a token with **write** access).

## 1. Create the Space under the org

```bash
hf auth login
hf repo create build-small-hackathon/llm-cinema --repo-type space --space_sdk gradio
```

(or create it in the web UI: huggingface.co/new-space → owner = `build-small-hackathon`,
SDK = Gradio, name = `llm-cinema`.)

## 2. Upload the app (only what the Space needs)

```bash
hf upload build-small-hackathon/llm-cinema . . --repo-type space \
  --exclude "saved/*" "*.log" "*.jsonl" "*.bak" ".endpoint_key" \
            "drawn_cache.json" "__pycache__/*" "*.pyc"
```

This pushes `stage.py` (the app), the engine modules, `sprites.txt`, the `showcase/`
gallery films, `README.md`, and `requirements.txt`.

## 3. Set the Space secrets

Space → **Settings → Variables and secrets** → add (point these at your own
OpenAI-compatible endpoint; the key never lives in the repo):

| Name | Value |
| --- | --- |
| `CLAUDEMOVIES_LLM_URL` | `https://<your-endpoint>/v1` |
| `CLAUDEMOVIES_LLM_MODEL` | `cinema` |
| `CLAUDEMOVIES_LLM_KEY` | *(your bearer key)* |

## 4. Verify (the judge's-eye check)

Open the Space in a fresh browser:
- the **knight film auto-plays** within a couple seconds (no model needed),
- **Gallery** films replay instantly,
- **Make a film** → type a concept → Cinema writes + plays it live,
- **Adventure** → Begin → A/B/C choices appear,
- **Download** produces a GIF.

Warm both endpoints right before judging / recording the demo (open the Space, run one
*Make* and one *Adventure*) so the first judge click isn't a cold start.

## Keeping the endpoints awake during judging
Both Modal apps scale to zero after 15 min idle. They wake on the first request (~1–2 min
cold start for the teacher, ~2–4 min for Cinema loading MiniCPM). The Gallery covers that
gap (always instant). If you want them always-warm during judging, redeploy with a larger
`scaledown_window` — but that spends more credits.
