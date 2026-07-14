"""
Generate a curated set of showpiece films into showcase/ so the Space gallery has
gems that replay INSTANTLY (no model call) the moment a judge opens it.

    CLAUDEMOVIES_LLM_URL/_KEY/_MODEL set, then:  python showcase.py
"""

import json
import os
import re
import sys

import movies

SHOW = os.path.join(os.path.dirname(__file__), "showcase")

# fixed slug -> (clean display title, concept). Stable filenames + curated titles, so
# the gallery + title cards read well no matter what title the model invents.
# knight.json is the auto-play flagship.
FILMS = {
    "knight":       ("The Knight Afraid of the Dark", "a tiny knight who is afraid of the dark"),
    "rain-cat":     ("A Robot and a Stray Cat", "a lonely robot who finds a stray cat in the rain"),
    "bread-dragon": ("The Dragon Who Would Rather Bake", "a dragon who would rather bake bread than breathe fire"),
    "troll-dance":  ("The Troll Who Longed to Dance", "a grumpy troll who secretly longs to dance"),
    "paper-boat":   ("The Paper Boat", "a paper boat's brave voyage to the endless sea"),
    "ghost":        ("The Little Ghost Afraid of People", "a little ghost who is afraid of humans"),
    "snail-race":   ("The Snail Who Raced the Wind", "a snail who dreams of racing the wind"),
}


def main():
    os.makedirs(SHOW, exist_ok=True)
    for slug, (title, c) in FILMS.items():
        for _ in range(3):                       # retry until we get a full-length film
            spec = movies.direct(c)
            if movies.good_shot_count(len(spec.get("shots", []))):
                break
        n = len(spec.get("shots", []))
        if not movies.good_shot_count(n):
            print(f"  skip (shots={n}): {slug}", file=sys.stderr)
            continue
        spec["title"] = title                    # curated, clean title for the gallery + card
        json.dump(spec, open(os.path.join(SHOW, slug + ".json"), "w"), indent=2, ensure_ascii=False)
        print(f"  saved {slug}.json  ({n} shots, \"{title}\")")


if __name__ == "__main__":
    main()
