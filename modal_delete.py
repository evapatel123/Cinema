"""Audit + delete HF repos pushed via the stored huggingface-secret (no token paste).

    companion/.venv/bin/modal run claudemovies/modal_delete.py
"""
import modal

app = modal.App("hf-cleanup")
img = modal.Image.debian_slim().pip_install("huggingface_hub")


@app.function(image=img, secrets=[modal.Secret.from_name("huggingface-secret")])
def cleanup(repos):
    import os
    from huggingface_hub import HfApi, whoami
    tok = os.environ["HF_TOKEN"]
    api = HfApi()
    user = whoami(token=tok)["name"]
    deleted = []
    for r in repos:
        full = r if "/" in r else f"{user}/{r}"
        try:
            api.delete_repo(repo_id=full, token=tok)
            deleted.append(full)
        except Exception:
            pass
    models = [m.id for m in api.list_models(author=user)]
    spaces = [s.id for s in api.list_spaces(author=user)]
    datasets = [d.id for d in api.list_datasets(author=user)]
    return {"account": user, "deleted_now": deleted,
            "remaining_models": models, "spaces": spaces, "datasets": datasets}


@app.local_entrypoint()
def main():
    print(cleanup.remote(["companion-minicpm", "cinema"]))
