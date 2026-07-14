"""
Scale the craft training set: brainstorm many diverse concepts, direct each into
an original movie (craft-KB guided), grade it, and keep the well-formed ones.

Writes movie_sft.jsonl (gold + generated). Combine with ascii_sft.jsonl at fine-tune.

    python generate_ton.py --target 120
Needs CLAUDEMOVIES_LLM_URL / _KEY / _MODEL.
"""

import argparse
import json
import os
import sys

import movies
import train_data

MOODS = ["heartfelt", "funny", "strange", "spooky", "adventurous", "cozy", "epic",
         "sad but hopeful", "whimsical", "mysterious", "silly", "dark and tender",
         "wholesome", "surreal", "action-packed", "quiet", "fantastical", "triumphant",
         "bittersweet", "playful"]


def valid(spec):
    s = spec.get("shots")
    return (isinstance(s, list) and movies.good_shot_count(len(s))
            and all(x.get("narration") for x in s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=120)
    a = ap.parse_args()

    concepts, seen = [], set()
    for c in train_data.CONCEPTS:
        if c not in seen:
            seen.add(c); concepts.append(c)
    fails = 0
    for m in MOODS:                                   # brainstorm more via the host
        try:
            for f in movies.pitch(m):
                p = f.get("premise", "").strip()
                if p and p not in seen:
                    seen.add(p); concepts.append(p)
        except Exception as e:                        # model layer raises varied types; skip but count
            fails += 1
            print(f"  pitch failed ({m}): {e}", file=sys.stderr)

    rows = [train_data.row(c, spec) for c, spec in train_data.GOLD]
    kept = 0
    for c in concepts:
        if kept >= a.target:
            break
        try:
            spec = movies.direct(c)
        except Exception as e:
            fails += 1
            print(f"  direct failed ({c[:40]}): {e}", file=sys.stderr)
            continue
        if valid(spec):
            rows.append(train_data.row(c, spec))
            kept += 1
            if kept % 10 == 0:
                print(f"  {kept}/{a.target} kept")
    if fails:
        print(f"  ({fails} model calls failed — check the endpoint if this is high)", file=sys.stderr)

    path = os.path.join(os.path.dirname(__file__), "movie_sft.jsonl")
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} craft rows ({kept} generated + {len(train_data.GOLD)} gold) -> movie_sft.jsonl")


if __name__ == "__main__":
    main()
