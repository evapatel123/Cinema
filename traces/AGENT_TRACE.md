# Agent Trace — how LLM Cinema was built

**Open Trace badge.** LLM Cinema was built by a human directing an **AI coding agent** across many
sessions. This is the scrubbed, public record of that collaboration — what the agent changed and
why — so others can see how an AI agent and a human built a small-model project end to end.

This trace is intentionally **secret-free**: no API keys, tokens, endpoint URLs, emails, or other
personal data appear here or anywhere in the repo (those live only in Space secrets). For the
distilled lessons (what worked, what didn't), see [`FIELD_NOTES.md`](../FIELD_NOTES.md).

## What the agent did, in order

The agent worked the way a careful engineer would: read the code, made a focused change, then
**verified it live** (headless-browser screenshots of the deployed Space, frame-by-frame render
scans, content-filter probes) before moving on. Highlights of the loop:

- Built the off-brand custom `gr.Server` frontend (cinema-hall backdrop, ASCII projected through a
  transparent screen cut-out, reactive under-screen lighting, opening credits, replay, mobile layout).
- Hardened the director: 9-beat structure, always-draw-both-subjects, slower pacing, indoor/outdoor
  scene variety, cold-start retry, profanity + prompt-injection filtering.
- Investigated whether the 4B could draw the cast (it was fine-tuned to) — found its live ASCII too
  rough, so kept the hand-authored sprite library and added a guard that rejects non-art model output.
- Security pass: removed all personal endpoint URLs from public files, added `.gitignore` for secrets.

## Commit-level trace (most recent first)

- `0f3bde6` Scene variety: add an indoor floor + keyword inference + director option (not always outdoors)
- `4137b3c` QA fixes: block profanity variants (shitty/fucking/dickhead); stop auto-casting props as characters (window/table); writing screen drops 'presents'
- `619fba1` Fix on-screen garbage: reject non-art model draws (->placeholder); alias shadow->monster, lizard->frog etc.; clean showcase casts to drawable subjects
- `f3ac16b` Quality pass: revert to library art, calmer prose (temp 0.7 + clarity rule), regenerate all 7 showcase films (on-concept, complete, both subjects); keep library after 4B drawings proved poor
- `cff7f51` Fix website URL: conductorailabs.com (About modal + end card)
- `f5340ba` Keep cloud Modal for live + surface off-grid: page footer link, welcome link, and an About modal
- `832314a` Cold-start resilience: longer timeout + retry so a real script comes back, not the generic fallback
- `95b88fd` Stop clipping/covering the screen edges
- `2a4c31c` Generation quality: draw all concept subjects + slower pacing + duo-aware prompt
- `73450e8` Subtitles: lift the scene off the floor (blank row gap); intro: show LLM CINEMA title on the writing screen
- `d15bcb2` Intro reorder (title+writing status -> presented-by bumper -> film) + correct mobile screen mapping
- `b45c9bd` README: make off-grid (local llama.cpp) the primary run path; hosted endpoint is optional fallback
- `0c6a40d` Restore Off-the-Grid + Llama Champion badges (off-grid run is real, via llama.cpp)
- `c4e8fb0` README: Thousand Token Wood track + accurate tags/badges (only claim what's evidenced)
- `bcfb412` Harden: gitignore secrets/logs; genericize last endpoint example in cinema_serve docstring
- `31a3b51` Security/cleanup: remove personal Modal URLs from README+DEPLOY; submission section + tags
- `a64e0bc` Draw fire: campfire sprite + fire aliases + warm colour + centre-stage props
- `9a57626` Branded social share image + OG/Twitter tags; mobile-optimized controls + fullscreen
- `1cb85a9` New cinema backdrop (hf_bg3) + bigger welcome LLM CINEMA title
- `3c271db` Welcome title smaller+white; white title/end cards w/ Conductor Creative Labs; drop green text-glow
- `f6caf5e` Input security: 60-char cap + sanitiser + prompt-injection guard
- `f5978e7` Style the idle theatre screen: ASCII LLM CINEMA title + presented-by + directions
- `d1e2cba` ANSI-shadow ASCII title font for LLM CINEMA + 'presented by conductor creative labs'
- `b6bfa75` Darken the idle background (was too bright before a film plays)
- `5d40964` Opening credits while rendering + Replay button
- `53b758e` Glow: colour-mirror the on-screen action (ambilight) + raise subtitle
- `eac7201` Intro loader: all white (drop the green accent)
- `884998f` Cinema: fill the cut-out (80-wide grid + JS contain-fit) + realistic under-screen light
- `3f3a50b` Screen behind the bg cutout (pixel-perfect) + restrained lighting (ambient + reactive streaks)
- `8914340` Loader (NOW ENTERING) + screen glow + subtitle pagination + regenerated complete-sentence showcase films
- `d08eec9` Deploy custom gr.Server frontend: app_file=server_app.py, gradio 6.16, env-aware launch
- `5962c6c` Custom gr.Server frontend: cinema-hall backdrop + bottom controls + badge assets
- `40e6735` Add Field Notes (build report) for the hackathon
- `1e9d1cb` Airtight prose↔visuals: force every narrated drawable subject into the cast
- `7356330` Fix subtitle cutoff + keep narrated objects on screen
- `7450b1a` Remove the Adventure section (redundant)
- `e33d07f` Stories: tighter ~90s length + coherent 3-act structure + stronger prose
- `89c934c` Clean up Create/Adventure inputs: large, single-box, no overlap
- `c38c81c` Stop reliably cancels: re-assert welcome to beat trailing frames
- `c58abb9` Cleaner Create area: larger prompt box + Stop/cancel control
- `519ab9d` Cinematic intro: stylized ASCII LLM CINEMA title card
- `35cede2` Welcome prompt instead of autoplay; remove glow; private creations; content filter
- `b43586f` Shelf: Now Playing (wraps, no truncation) + Gallery at bottom showing all films
- `64eb064` Shelf nav: no scroll either axis, everything fits
- `c89259a` Contain page with a fixed app height (stop HF iframe feedback loop)
- `b80495e` Fix infinite page height (contain to viewport)
- `b35fc23` Restyle: modern charcoal + grid + monospace terminal look
- `02b76ab` Redesign: full-frame app — left nav shelf, cinema on the right
- `98aa54b` Fix: loading screen now shows; default film no longer plays over user actions
- `84ae783` Center the app and widen it (was pinned to the left edge)
- `7b31f84` Cinema redesign: film projects on a curtained movie screen, prompt below
- `e1d1f5e` Center the knight's head over its body
- `a763e9e` Star rating: cumulative hover fill (hovering star N lights 1..N)
- `e93ee78` Add a star rating under the player (copy sits inline beside the stars)
- `5952a83` Fix intro-looping playback, remove UI emojis, add site to end credits
- `ce548f2` Redesign stage (modern dark cinema UI) + stop auto-play clobbering user films
- `6fdf408` Fix live Make&play (robust JSON salvage) + center & stabilize the stage
- `5e37282` Spaces-ready: subtitle wrap, gallery order, adventure GIF state, endpoint warmup
- `a7482ca` Polish: coherent gallery films (judge-picked) + end credits + crash fix
- `3d08781` Showcase: curated clean titles for the gallery + title cards
- `fb89b67` Contest-ready: serve Cinema (MiniCPM) live + dual-endpoint + deploy assets
- `8e2cf0e` Cinema Space: feature the knight film on load (flagship first impression)
- `ab1c2d8` LLM Cinema: judge-ready Gradio app + showcase gallery + deploy artifacts
- `7cfe667` Cinema iterate: robust grader + movie-dominant data (drift fixed; 0.75->0.88)
- `2bc64a1` Cinema fine-tune: fix in-job test token budget (420 -> 1000); valid_script_rate 0.75
- `5c5d7b7` Cinema training data: regenerate movie_sft on the 13-beat + setting/camera/mood schema
- `6de0709` LLM Cinema: choose-your-own-adventure (interactive branching films)
- `9f677d6` LLM Cinema: saved character library + side-only entrances
- `b3b2bc2` LLM Cinema: camera moves, character moods, title/end cards + scene fades
- `55d00ff` Rebrand: ClaudeMovies -> LLM Cinema; model named 'Cinema'
- `483e277` Fix latent risk: companion fine-tune now pushes to a PRIVATE HF repo
- `3071618` Cleanup (types): shared schema module + fix FLOOR type defect; mypy 5->0 errors
- `fcb5c25` Cleanup (comments): scrub award/hackathon larp and edit-narration
- `29f262b` Cleanup (defensive): narrow broad excepts, surface silent failures
- `0597d50` Cleanup (DRY): consolidate duplicated staging helpers into movies.py
- `5f1d376` Cleanup: break movies<->draw cycle via leaf llm_client module
- `f31b098` Cleanup: remove dead CAST sprite dict, unify shot-count contract to 13-beat
- `60c9d29` Checkpoint: locked scenes, 2-min pacing, sprite library, floors, colors, scenery, z-order spacing
- `a09bca9` Fix security findings: SSRF guard, key-in-secret, path traversal, relay auth
- `5b96db7` ClaudeMovies: inline terminal 'stage' player (Gradio, streams frames in-page) + in-job model test in fine-tune
- `36d15d0` ClaudeMovies: scale-up data generator + private fine-tune (private HF repo, combined craft+ascii corpus)
- `3ea9a5b` ClaudeMovies: craft KB (3-act/endings/dialogue) + ASCII drawing dataset + draw-any-character pipeline; director cross-references craft, renderers draw any cast
- `3919bcf` ClaudeMovies: slower playback + held readable subtitles + charcoal bg; finetune saves private (no auto-publish)
- `3d8e0f1` ClaudeMovies: Movie Night harness (REEL host, pitch/pick/mix/library, subtitles)
- `16498a4` ClaudeMovies: video renderer (GIF/filmstrip) + SFT data gen + Modal MiniCPM fine-tune setup
- `18b93fb` ClaudeMovies: LLM directs ORIGINAL ASCII movies on the Claudecade engine (super-engineered director)
- `4cce2c5` ASCIIBook: TF-IDF retrieval + softer refusal for grounded Q&A
- `0bdffbc` ASCIIBook: ASCII storyteller with reusable sprite library + AgentPhone prototypes
- `9027d69` Archive companion + modal work before pivot
- `534f31e` Add full system architecture doc
- `29cee72` Companion: dignified memory companion for elders (Gradio + Modal agent)

---

*Each commit was made by the agent and verified before the next. The full reasoning lived in the
coding-agent session; this is the public, sanitized change record shared for the Open Trace badge.*
