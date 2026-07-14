# Field Notes — Building LLM Cinema

*A small fine-tuned model that writes, draws, and directs original ASCII films — and plays
them inline. Built for the Build Small Hackathon.*

---

## The idea

Most "AI video" demos are wrappers around a giant hosted model. We wanted the opposite: a
**small** model doing something genuinely creative, where the model is *load-bearing* — remove
it and there's nothing left. So we built **Cinema**, a fine-tuned **MiniCPM3‑4B** that, from a
single sentence, invents an original ~90‑second film: it writes a beat-by-beat story, casts and
draws every character in ASCII, picks the terrain, camera, and a feeling per character, then
stages and plays it frame-by-frame right in the page. No video, no sound — just a small model's
imagination, streamed.

The whole thesis is **small by design**: a 4B model, fine-tuned, is enough to be delightful.

---

## How it works

- **Director (the model).** A concept → a strict-JSON film script: a 9-beat, three-act arc with
  per-shot `narration`, `cast`, `action`, `setting`, `camera`, and `mood`. The model is the
  author, the casting director, and the cinematographer.
- **Artist (the model again).** Any subject named in a shot is drawn as a small ASCII sprite —
  from a curated library of ~100, or drawn on demand by the model and cached.
- **Renderer (deterministic).** A Python engine turns the script into frames: textured terrain
  (water shimmers, lava glows, snow), characters that enter and idle, subtitles that type on,
  soft scene dips, a title card and end credits. Everything targets one canonical frame rate so
  the GIF, the web stage, and the terminal player all match.
- **Stage (the app).** The film streams frame-by-frame into a charcoal, monospace, "cinema"
  UI — left nav shelf, screen on the right — with a Gallery of pre-rendered films that replay
  instantly (no model needed), live "Make a film," ratings, and one-click GIF export.

---

## What we learned (the engineering, honestly)

A surprising amount of the work wasn't the model — it was making a *small model + a streaming UI*
behave. The most useful lessons:

**1. Small models mangle JSON in three different ways.** Across runs our director would
(a) backslash-escape every inner quote, (b) truncate at the token cap mid-film, and (c) emit a
field as an array. A single strict `json.loads` failed on all three, so every live film silently
fell back to a generic script. The fix was a tolerant parser: un-escape stray quotes, drop
trailing commas, and — crucially — a **salvage pass** that recovers individual shot objects past
a broken tail. *Lesson: never trust a small model to emit clean JSON; design the parser to
salvage, not validate.*

**2. Gradio's `cancels=` doesn't reliably stop a running generator.** Our opening film auto-played
as a streaming generator; when a user hit "Make," the default film kept streaming *over* their
loading screen. `cancels` didn't stop it. We replaced it with a **per-session generation token**:
every playback bumps a counter and bails the instant a newer one supersedes it. *Lesson: for
"only one stream at a time, newest wins," own the cancellation yourself with a token — don't rely
on the framework.*

**3. `height: 100vh` inside Hugging Face's auto-resizing iframe is an infinite loop.** The iframe
sizes to content; content sized to the viewport; they fed each other and the page grew past
18,000px. Any viewport-relative height does it. The fix was a **fixed pixel app height** — a
constant the loop can't amplify. *Lesson: in an embedded Space, never size to the viewport.*

**4. The biggest lever on a small model's writing is the in-context example.** Prompt
instructions help, but a single high-quality 9-shot example — the exact format, length, and prose
we wanted — moved output quality more than paragraphs of rules. *Lesson: show, don't tell, even to
the model.*

**5. Keep prose and pixels in sync, mechanically.** The model would narrate "a fireplace" that
never appeared, because only the `cast` is drawn. Rather than hope the model behaves, we scan each
narration against the full sprite vocabulary (≈100 sprites + ~130 aliases + common objects) and
**force any named drawable subject into the cast**. *Lesson: when two outputs must agree, don't
prompt for it — enforce it in code.*

**6. Streaming longevity matters.** A ~90s film is hundreds of frames. Building the whole frame
list up front, or blocking 60–90s on a cold model call with no yields, made the stream stall and
restart — replaying the intro forever. We made frames lazy (first frame instant) and run the model
call in a thread with a 1s heartbeat. *Lesson: a streaming UI must never go silent.*

---

## Design

We pushed hard past the default Gradio look: a flat **charcoal background with a faint blueprint
grid**, **JetBrains Mono** everywhere, a left "shelf" nav, and a glowing-bezel **screen** with a
`now_playing:` status bar and HUD corner brackets. Films stay contained in a fixed frame; the
nav never scrolls sideways.

---

## Safety

User prompts pass a content filter (profanity, slurs, hate) before anything is generated, in both
Make and the (now-removed) Adventure mode. Creations are **private to the maker's session** and
never stored or shown to anyone else.

---

## What's next

- **Off the grid:** quantize Cinema to **GGUF** and run it via **llama.cpp** inside the Space —
  no cloud, free CPU, ~the same quality (quantization costs speed, not craft).
- **Better prose:** the real step-change is the training data — a few hundred excellent 9-beat
  scripts would teach the model the *voice*, not just instruct it.
- **A custom frontend** via `gr.Server` for total design control.

---

## Credits

Model: fine-tuned **MiniCPM3‑4B** (OpenBMB base). App: Gradio + a custom ASCII render engine.
Built by **Conductor AI Labs** for the Build Small Hackathon.
