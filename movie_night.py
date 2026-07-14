"""
🎬 LLM Cinema — Movie Night.

The full harness. You boot it up, REEL (your host) asks what you're in the mood
for, pitches THREE original films (title + premise), and you:
  • pick one          [1-3]
  • ask for others    [m]ore
  • mix two of them    mix 1 3
  • rerun a favorite  [l]ibrary
Then it WRITES the film, ANIMATES it on the Claudecade engine, with SUBTITLES
(narration + dialogue) since there's no sound. Every film is saved to replay.

    python movie_night.py        # run it in your terminal (the movie needs a TTY)

Model:  CLAUDEMOVIES_LLM_URL / _KEY / _MODEL
"""

import glob
import json
import os
import time

import movies

HERE = os.path.dirname(os.path.abspath(__file__))
SAVED = os.path.join(HERE, "saved")

BANNER = r"""
   ___ _              _      __  __         _
  / __| |__ _ _  _ __| |___ |  \/  |_____ _(_)___ ___
 | (__| / _` | || / _` / -_)| |\/| / _ \ V / / -_|_-<
  \___|_\__,_|\_,_\__,_\___||_|  |_\___/\_/|_\___/__/   M O V I E   N I G H T
"""


def _think(msg, secs=0.0):
    print(msg, end="", flush=True)
    for _ in range(3):
        time.sleep(secs)
        print(".", end="", flush=True)
    print()


def show_pitches(films):
    print("\n  🎬  Tonight's premieres:\n")
    for i, f in enumerate(films, 1):
        print(f"   {i}.  \033[1m{f['title']}\033[0m")
        print(f"        {f['premise']}\n")


def library():
    files = sorted(glob.glob(os.path.join(SAVED, "*.json")))
    if not files:
        print("  (your library is empty — make one first)")
        return None
    print("\n  🎞️  Your library:\n")
    for i, p in enumerate(files, 1):
        spec = json.load(open(p))
        print(f"   {i}.  {spec.get('title','?')}  —  {spec.get('logline','')}")
    sel = input("\n  rerun which? [number, or ENTER to go back] > ").strip()
    if sel.isdigit() and 1 <= int(sel) <= len(files):
        return json.load(open(files[int(sel) - 1]))
    return None


def play_film(spec):
    movies.save_movie(spec)
    print(f"\n  🎬  Now showing:  \033[1m{spec['title']}\033[0m")
    if spec.get("logline"):
        print(f"      {spec['logline']}")
    input("\n  press ENTER to roll the film  (ESC quits, ENTER skips a shot) ")
    try:
        movies.play(spec)            # the Claudecade engine, with subtitles
    except Exception as e:
        print(f"  (couldn't open the terminal movie: {e})")
    print("\n  🎬  ~ THE END ~\n")


def main():
    print(BANNER)
    print("  Good evening. I'm REEL, your host. Let's find you something to watch.\n")
    mood = input("  What are you in the mood for tonight? > ").strip()

    films = None
    while True:
        if films is None:
            _think("  REEL is dreaming up tonight's lineup", 0.25)
            films = movies.pitch(mood)
            show_pitches(films)

        choice = input("  pick [1-3] · [m]ore · mix 1 3 · [l]ibrary · [q]uit > ").strip().lower()

        if choice in ("q", "quit", ""):
            print("\n  🎬  Goodnight. Roll credits.\n")
            return
        if choice in ("m", "more"):
            films = None
            continue
        if choice in ("l", "library"):
            spec = library()
            if spec:
                play_film(spec)
            continue

        concept, title = None, None
        if choice.startswith("mix"):
            idxs = [int(x) - 1 for x in choice.split()[1:] if x.isdigit()]
            picks = [films[i] for i in idxs if 0 <= i < len(films)]
            if picks:
                concept = "A single film that blends: " + " AND ".join(f["premise"] for f in picks)
        elif choice.isdigit() and 1 <= int(choice) <= len(films):
            f = films[int(choice) - 1]
            concept, title = f["premise"], f["title"]

        if not concept:
            print("  hmm, didn't catch that.")
            continue

        _think("\n  REEL is writing and directing your film", 0.4)
        spec = movies.direct(concept, title=title)
        play_film(spec)
        films = None                 # fresh lineup next round


if __name__ == "__main__":
    main()
