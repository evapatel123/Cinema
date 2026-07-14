"""
OpenAI-compatible chat client for the director model (e.g. a Modal vLLM endpoint).

A leaf module: it imports nothing from the package, so both `movies` (story
director) and `draw` (ASCII artist) can use it without an import cycle.

Config via env:  CLAUDEMOVIES_LLM_URL / _KEY / _MODEL  (the main director: Cinema).
The Adventure mode may use a second endpoint via CLAUDEMOVIES_ADV_* (a general model
handles branching better); it falls back to the main endpoint if ADV is unset.
"""

import json
import os
import urllib.request


def llm(system, user, max_tokens=600, temperature=0.8, prefix="CLAUDEMOVIES_LLM", timeout=90):
    """Return the model's reply, or "" if no endpoint is configured. `prefix` selects
    the env-var family (CLAUDEMOVIES_LLM_* by default, CLAUDEMOVIES_ADV_* for adventure).
    `timeout` is the per-request read timeout — raise it for a cold scale-to-zero endpoint."""
    if prefix == "CLAUDEMOVIES_ADV" and not os.environ.get("CLAUDEMOVIES_ADV_URL"):
        prefix = "CLAUDEMOVIES_LLM"                       # no separate adventure endpoint -> use the main one
    url = os.environ.get(prefix + "_URL", "")
    if not url:
        return ""
    base = url.rstrip("/") + ("" if url.rstrip("/").endswith("/v1") else "/v1")
    payload = json.dumps({"model": os.environ.get(prefix + "_MODEL", "Qwen/Qwen2.5-3B-Instruct"),
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": user}],
                          "max_tokens": max_tokens, "temperature": temperature}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=payload,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + os.environ.get(prefix + "_KEY", "")})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())["choices"][0]["message"]["content"]
