"""
Generate ASCII-drawing SFT rows from the hand-authored sprite library.

Teaches the model to DRAW: (label/description -> small ASCII sprite), in one
consistent style. Combined with movie_sft.jsonl (story craft), the model learns
to do it all: write the story AND draw its characters AND stage the movie.

    python ascii_data.py        # -> ascii_sft.jsonl
"""

import json
import os

import ascii_sprites as A

DRAW_SYS = ("You are an ASCII artist. Draw a small black-and-white ASCII sprite (max 7 rows, max 14 "
            "columns, pure ASCII, front-facing, sitting on a ground line) of the requested subject. "
            "Keep one consistent simple style. Output ONLY the ASCII art, no commentary.")


def row(label, lines):
    return {"messages": [{"role": "system", "content": DRAW_SYS},
                         {"role": "user", "content": f"Draw: {label}"},
                         {"role": "assistant", "content": "\n".join(lines)}]}


def main():
    # canonical sprites only — aliases just duplicate the same art under synonyms and
    # are resolved at runtime by a string lookup, not the model. Training on them
    # over-weights the draw task vs movie-writing, so we leave them out.
    out = [row(name, lines) for name, lines in A.SPRITES.items()]
    path = os.path.join(os.path.dirname(__file__), "ascii_sft.jsonl")
    with open(path, "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out)} ASCII-drawing rows ({len(A.SPRITES)} canonical sprites) -> {path}")


if __name__ == "__main__":
    main()
