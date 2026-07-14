"""
LoRA fine-tune the "Cinema" model on Modal, then save it (private by default).

Cinema learns to BOTH write 13-beat ASCII films and draw the cast, from
movie_sft.jsonl (story craft) + ascii_sft.jsonl (sprite drawing).

    # generate the training data first:
    python claudemovies/train_data.py      # -> movie_sft.jsonl
    python claudemovies/ascii_data.py      # -> ascii_sft.jsonl
    # train (saves to the cinema-models Modal volume):
    modal run claudemovies/modal_finetune.py
    # train AND push to a PRIVATE HF repo:
    modal run claudemovies/modal_finetune.py --publish

Base defaults to MiniCPM; override with FT_BASE. Repo name via --repo-id (default "cinema").
"""

import json
import os

import modal

# MiniCPM base; override with FT_BASE=Qwen/Qwen2.5-1.5B-Instruct if the toolchain fights it.
BASE = os.environ.get("FT_BASE", "openbmb/MiniCPM3-4B")

# concepts the in-job test grades the fine-tuned model on
TESTS = ["a tiny knight afraid of the dark", "a lonely robot who finds a cat",
         "a rabbit who wants the moon", "a monster who just wants a friend",
         "two birds racing the sunrise", "a ship lost in a sea of stars",
         "a dragon who would rather bake", "a candle racing the dawn"]


def _first_json(s):
    """First COMPLETE {...} object (balanced braces) — ignores any trailing garbage
    the model may emit after the JSON (repeat loops, ANSI, extra prose)."""
    i = s.find("{")
    while i != -1:
        depth = 0
        for j in range(i, len(s)):
            depth += (s[j] == "{") - (s[j] == "}")
            if depth == 0:
                try:
                    return json.loads(s[i:j + 1])
                except Exception:
                    break
        i = s.find("{", i + 1)
    return None


def _grade(model, tok, sysmsg):
    """Generate a film for each TEST concept and structurally grade it. Low-temp +
    repetition penalty avoids loops; balanced-brace extraction is robust to trailing
    garbage; 1800 tokens fits the longest films."""
    passed, samples = 0, []
    for c in TESTS:
        msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": f"CONCEPT: {c}"}]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda")
        g = model.generate(ids, max_new_tokens=1800, do_sample=False,   # greedy = deterministic, consistent length
                           repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
        txt = tok.decode(g[0][ids.shape[1]:], skip_special_tokens=True)
        spec = _first_json(txt)
        sh = spec.get("shots", []) if isinstance(spec, dict) else []
        ok, reason = False, "ok"
        if not isinstance(spec, dict) or "shots" not in spec:   reason = "no-json"
        elif not isinstance(sh, list):                          reason = "no-shots-list"
        elif not (8 <= len(sh) <= 18):                          reason = f"shots={len(sh)}"
        elif not all(s.get("narration") for s in sh):           reason = "empty-narration"
        else:                                                   ok = True
        passed += int(ok)
        samples.append({"concept": c, "valid": ok, "reason": reason,
                        "tail": "" if ok else txt[-140:].replace(chr(10), " ")})
    return {"valid_script_rate": round(passed / len(TESTS), 2), "n": len(TESTS), "samples": samples}

app = modal.App("cinema-finetune")

train_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.5.1",
        "transformers==4.46.3",
        "trl==0.12.2",
        "peft==0.13.2",
        "datasets==3.1.0",
        "accelerate==1.1.1",
        "huggingface_hub==0.26.5",
        "sentencepiece",
        "datamodel-code-generator",  # MiniCPM3 tokenizer dep
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "0"})
)

hf_cache = modal.Volume.from_name("companion-hf-cache", create_if_missing=True)
models_vol = modal.Volume.from_name("cinema-models", create_if_missing=True)


@app.function(
    image=train_image,
    gpu="L40S",
    secrets=[modal.Secret.from_name("huggingface-secret")],
    volumes={"/root/.cache/huggingface": hf_cache, "/models": models_vol},
    timeout=2 * 60 * 60,
)
def train(data: list, repo_id: str, publish: bool = False):
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    print(f"base={BASE}  examples={len(data)}  -> repo={repo_id}")
    tok = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE, torch_dtype=torch.bfloat16, trust_remote_code=True, device_map="cuda")

    ds = Dataset.from_list(data)
    peft_cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05,
                          target_modules="all-linear", task_type="CAUSAL_LM")
    args = SFTConfig(
        output_dir="/root/out",
        num_train_epochs=4,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=2e-4,
        warmup_ratio=0.05,
        bf16=True,
        logging_steps=10,
        save_strategy="no",
        max_seq_length=1024,
        packing=False,
    )
    trainer = SFTTrainer(model=model, args=args, train_dataset=ds,
                         peft_config=peft_cfg, processing_class=tok)
    trainer.train()

    merged = trainer.model.merge_and_unload()

    metrics = _grade(merged, tok, data[0]["messages"][0]["content"])   # in-job structural test
    print("TEST:", metrics)

    if publish:                                    # private HF repo (never public)
        from huggingface_hub import create_repo
        tokn = os.environ["HF_TOKEN"]
        create_repo(repo_id, token=tokn, private=True, exist_ok=True)
        merged.push_to_hub(repo_id, token=tokn, private=True)
        tok.push_to_hub(repo_id, token=tokn, private=True)
        loc = f"PRIVATE repo https://huggingface.co/{repo_id}"
    else:
        out = f"/models/{repo_id}"
        merged.save_pretrained(out)
        tok.save_pretrained(out)
        models_vol.commit()
        loc = f"Modal volume cinema-models:/{repo_id}"
    return {"saved": loc, "test": metrics}


@app.function(
    image=train_image,
    gpu="L40S",
    secrets=[modal.Secret.from_name("huggingface-secret")],
    volumes={"/root/.cache/huggingface": hf_cache, "/models": models_vol},
    timeout=30 * 60,
)
def test_saved(repo_id: str, sysmsg: str):
    """Re-grade an already-saved model from the volume (no retraining)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    path = f"/models/{repo_id}"
    tok = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        path, torch_dtype=torch.bfloat16, trust_remote_code=True, device_map="cuda")
    metrics = _grade(model, tok, sysmsg)
    print("RETEST:", metrics)
    return metrics


def _sysmsg():
    here = os.path.dirname(os.path.abspath(__file__))
    return json.loads(open(os.path.join(here, "movie_sft.jsonl")).readline())["messages"][0]["content"]


@app.local_entrypoint()
def main(repo_id: str = "cinema", publish: bool = False, ascii_cap: int = 30):
    here = os.path.dirname(os.path.abspath(__file__))

    def load(fn):
        p = os.path.join(here, fn)
        return [json.loads(line) for line in open(p)] if os.path.exists(p) else []

    movie = load("movie_sft.jsonl")
    draw = load("ascii_sft.jsonl")[:ascii_cap]   # keep draw exposure SMALL so the model
    data = movie + draw                          # stays movie-dominant and can't drift to "Draw:"
    print(f"training on {len(data)} rows ({len(movie)} movie + {len(draw)} draw); private={not publish}")
    print(train.remote(data, repo_id, publish))


@app.local_entrypoint()
def retest(repo_id: str = "cinema"):
    """Grade the saved model without retraining: modal run modal_finetune.py::retest"""
    print(test_saved.remote(repo_id, _sysmsg()))
