"""
Build the SFT dataset for our own ASCII-movie director model.

Each row teaches: CONCEPT -> an ORIGINAL movie script (strict JSON), in the exact
test-time format (Karpathy's SFT rule). Mix of hand-written GOLD examples and
distilled examples from the current model (cherry-picked for valid structure).

    python train_data.py --n 40          # generate -> movie_sft.jsonl
"""

import argparse
import json
import os

import movies

# the short instruction the fine-tuned model will be prompted with at run time
SFT_SYS = ("You are a master ASCII-movie director. From a concept, write an ORIGINAL ~2-minute film "
           "as strict JSON only: {\"title\":str,\"logline\":str,\"shots\":[{\"narration\":\"60-90 "
           "chars present tense\",\"cast\":[1-3 common nouns, each drawn in ASCII],\"action\":\""
           + "|".join(movies.ACTIONS) + "\",\"setting\":\"" + "|".join(movies.SETTINGS)
           + "\",\"dialogue\":\"optional <=60 chars\"}]}. Write " + str(movies.N_SHOTS) + " shots (a full 3-act arc).")

# varied concepts across tone/genre so the model learns range (craft, not content)
CONCEPTS = [
    "a tiny knight who is afraid of the dark", "a lonely robot who finds a stray cat",
    "a rabbit who wants to touch the moon", "a monster who just wants a friend",
    "two birds racing the sunrise", "a flower that grows in a haunted castle",
    "a cat burglar mouse and a sleepy guard dog", "a ship lost in a sea of stars",
    "a tree that remembers every child who climbed it", "a robot learning to laugh",
    "a knight and a dragon who'd rather have tea", "the last firefly looking for summer",
    "a house that misses the family that left", "a moonbeam trying to wake the sun",
    "a cat who thinks it is a king", "a small boat and a very big storm",
    "a shy ghost throwing a birthday party", "a snail in a race it cannot win",
    "a robot gardener and the first flower", "a wolf who howls off-key",
    "a girl who collects forgotten lullabies", "two rivals stuck in one elevator",
    "a clock that runs backward on purpose", "a lighthouse keeper and a lost whale",
    "a dragon afraid of its own fire", "a puppet who cuts its own strings",
    "a knight delivering a single flower across a war", "a cat and a beam of light, eternal rivals",
    "a robot reading a bedtime story to nobody", "a bird teaching a fish to fly",
    "the moon babysitting the stars", "a monster under the bed who is also scared",
    "a tiny boat sailing a bathtub ocean", "a scarecrow who wants to travel",
    "two old friends, one last game", "a candle racing the dawn",
    "a fox who steals colors from the sunset", "a robot and a kite",
    "a mouse mailing a letter to the moon", "a garden that only blooms when sung to",
]

# a couple of hand-written GOLD scripts (the quality bar the model imitates)
GOLD = [
    ("a lonely robot who finds a stray cat",
     {"title": "The Tin Heart", "logline": "A discarded robot learns to feel from a stray cat.",
      "shots": [
          {"narration": "A rusted robot jolts awake alone in a junkyard at dusk.", "cast": ["robot"], "action": "rise", "dialogue": ""},
          {"narration": "A wary cat slinks from the shadows, tail flicking.", "cast": ["robot", "cat"], "action": "enter", "dialogue": "...friend?"},
          {"narration": "They share a silent night beneath a watching moon.", "cast": ["robot", "cat", "moon"], "action": "gather", "dialogue": ""},
          {"narration": "Dawn comes; the cat turns to leave.", "cast": ["robot", "cat"], "action": "exit", "dialogue": "stay."},
          {"narration": "The robot follows, its tin chest glowing for the first time.", "cast": ["robot", "cat"], "action": "gather", "dialogue": ""}]}),
]


def row(concept, spec):
    return {"messages": [{"role": "system", "content": SFT_SYS},
                         {"role": "user", "content": f"CONCEPT: {concept}"},
                         {"role": "assistant", "content": json.dumps(spec, ensure_ascii=False)}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()
    out, kept, bad = [], 0, 0

    for concept, spec in GOLD:
        out.append(row(concept, spec))
        kept += 1

    for concept in CONCEPTS[:args.n]:
        spec = movies.direct(concept)
        # keep only well-formed, full-length scripts
        if isinstance(spec.get("shots"), list) and movies.good_shot_count(len(spec["shots"])) \
                and all(s.get("narration") for s in spec["shots"]):
            out.append(row(concept, spec))
            kept += 1
            print(f"  ✓ {concept[:40]:42} {len(spec['shots'])} shots")
        else:
            bad += 1
            print(f"  ✗ {concept[:40]} (malformed)")

    path = os.path.join(os.path.dirname(__file__), "movie_sft.jsonl")
    with open(path, "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {kept} rows ({bad} dropped) -> {path}")


if __name__ == "__main__":
    main()
