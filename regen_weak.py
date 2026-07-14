"""Regenerate the weaker gallery films via the teacher + a coherence judge (best of N)."""
import json
import re

import movies
import showcase

JUDGE = ("You rate how COHERENT and satisfying a short film's story is — does it follow a "
         "clear arc, stay on the concept, and not repeat itself? Reply ONLY an integer 1-10.")


def is_fallback(spec):
    """The deterministic template (teacher call failed) — off-concept, reject it."""
    return any("our story quietly begins" in s.get("narration", "") for s in spec["shots"])


def coherence(concept, spec):
    beats = "\n".join(f"{i+1}. {s['narration']}" for i, s in enumerate(spec["shots"]))
    r = movies.llm(JUDGE, f"CONCEPT: {concept}\n\nBEATS:\n{beats}\n\nScore (1-10):",
                   max_tokens=6, temperature=0)
    m = re.search(r"\d+", r or "")
    return int(m.group()) if m else 0


def main():
    movies.direct("a quick warmup so the endpoint is hot")          # avoid cold-start timeouts
    for slug in ["fireflies", "ghost", "snail-race"]:
        title, concept = showcase.FILMS[slug]
        best, bs = None, -1
        for _ in range(4):
            spec = movies.direct(concept)
            if is_fallback(spec) or not movies.good_shot_count(len(spec.get("shots", []))):
                continue                                            # reject template / wrong length
            s = coherence(concept, spec)
            if s > bs:
                best, bs = spec, s
        if best and bs >= 6:                                        # only keep genuinely coherent films
            best["title"] = title
            json.dump(best, open(f"showcase/{slug}.json", "w"), indent=2, ensure_ascii=False)
            print(f"  {slug:12} coherence {bs}/10  ({len(best['shots'])} shots)  KEPT")
        else:
            print(f"  {slug:12} best {bs}/10 — keeping the existing film")


if __name__ == "__main__":
    main()
