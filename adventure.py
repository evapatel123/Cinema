"""
Choose-your-own-adventure — an interactive, branching LLM Cinema film.

    python adventure.py "a knight at a haunted crossroads"

Each chunk plays (its GIF opens), then you pick a / b / c — or type your own
direction — and Cinema continues the story until it reaches an ending.
"""

import argparse
import subprocess
import sys

import movies
import render


def _grow_history(history: str, shots: list, choice: str) -> str:
    h = history + "\n".join(s["narration"] for s in shots) + "\n"
    if choice:
        h += f"(viewer chose: {choice})\n"
    return h[-1600:]                       # keep recent context within the prompt budget


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("concept")
    ap.add_argument("--no-open", action="store_true", help="don't open each chunk's GIF")
    a = ap.parse_args()

    concept, history, choice, n = a.concept, "", "", 0
    title = concept[:30]
    print(f"\n🌿 {concept}\n")
    while True:
        chunk = movies.direct_branch(concept, history, choice)
        n += 1
        title = chunk.get("title", title)
        spec = {"title": f"{title} — pt {n}", "logline": concept, "shots": chunk["shots"]}
        for s in chunk["shots"]:
            print("   ", s["narration"])
        gif, _, _ = render.render_spec(spec)
        if not a.no_open:
            subprocess.run(["open", gif], check=False)
        history = _grow_history(history, chunk["shots"], choice)

        if chunk["ending"]:
            print("\n🎬  THE END\n")
            break

        print("\n  What happens next?")
        for c in chunk["choices"]:
            print(f"    {c['key']})  {c['label']}")
        print("    (or type your own)")
        raw = input("\n  > ").strip()
        choice = next((c["label"] for c in chunk["choices"] if raw.lower() == c["key"]), raw)
        if choice.lower() in ("quit", "q", "exit"):
            print("  (left the adventure)")
            break


if __name__ == "__main__":
    main()
