"""
LLM Cinema — the inline STAGE (Gradio app, the hackathon submission).

The "Cinema" model writes, draws, and directs ORIGINAL ASCII films that play
INLINE on a little charcoal terminal-stage — no separate window, no sound, just
the model's imagination streaming frame by frame.

  • a showpiece film auto-plays the moment the page loads (no model call needed)
  • Make a film from any concept   • a Gallery of films that replay instantly
  • download your film as a GIF to share

Run:    python stage.py
Deploy: Hugging Face Space (Gradio). Set CLAUDEMOVIES_LLM_URL/_KEY/_MODEL secrets.
"""

import glob
import html
import json
import os
import random
import re
import threading
import time
import uuid

import gradio as gr

import movies
import render


def warm_endpoints():
    """Wake the scale-to-zero model endpoints in the background, so the first
    real 'Make a film' doesn't eat the whole cold start. Safe to call often."""
    def ping(prefix):
        try:
            movies.llm("Warmup.", "ok", max_tokens=1, prefix=prefix)
        except Exception:
            pass
    for prefix in ("CLAUDEMOVIES_LLM", "CLAUDEMOVIES_ADV"):
        threading.Thread(target=ping, args=(prefix,), daemon=True).start()

W, H = render.W, render.H
HERE = os.path.dirname(__file__)
SHOW = os.path.join(HERE, "showcase")
SAVED = os.path.join(HERE, "saved")

SURPRISES = [
    "a tiny knight who is afraid of the dark", "a lonely robot who finds a stray cat",
    "a dragon who would rather bake than fight", "two fireflies falling in love over a pond",
    "a grumpy troll who secretly wants to dance", "a snail who dreams of racing the wind",
    "a little ghost afraid of humans", "a paper boat's voyage to the endless sea",
    "a mouse who builds a ladder to the moon", "a candle racing the dawn",
]


# ── render a frame-grid to coloured HTML for the inline stage ──────────────────
def grid_to_html(grid, title=""):
    rows = []
    for r in range(H):
        cells, row, i = grid[r], "", 0
        while i < W:
            col, j, seg = cells[i][1], i, ""
            while j < W and cells[j][1] == col:
                seg += cells[j][0]
                j += 1
            hexc = "#%02x%02x%02x" % col if isinstance(col, tuple) else "#7CFC9A"
            esc = html.escape(seg)
            row += f"<span style='color:{hexc}'>{esc}</span>" if seg.strip() else esc
            i = j
        rows.append(row)
    return (f"<div class='stage'><div class='bar'><i></i><i></i><i></i>"
            f"<b>{html.escape(title)}</b></div><pre>{chr(10).join(rows)}</pre></div>")


def _idle(msg):
    return ("<div class='stage'><div class='bar'><i></i><i></i><i></i><b>LLM Cinema</b></div>"
            f"<pre>  {html.escape(msg)}</pre></div>")


_TITLE_ART = r"""
 _    _    __  __    ___ ___ _  _ ___ __  __   _
| |  | |  |  \/  |  / __|_ _| \| | __|  \/  | /_\
| |__| |__| |\/| | | (__ | || .` | _|| |\/| |/ _ \
|____|____|_|  |_|  \___|___|_|\_|___|_|  |_/_/ \_\
"""


def _welcome():
    """The first screen: a cinematic ASCII title card + a prompt to make a film."""
    e = html.escape
    art = [ln for ln in _TITLE_ART.strip("\n").split("\n")]
    w = max(len(ln) for ln in art)
    art_block = "\n".join(ln.ljust(w) for ln in art)   # equal-width lines stay aligned when centred
    strip = ("▖▖▘▘" * (w // 4 + 1))[:w]                # a film-strip edge
    body = (
        f"<span class='strip'>{e(strip)}</span>\n\n"
        f"<span class='ttl'>{e(art_block)}</span>\n\n\n"
        f"<span class='sub'>a small model writes · draws · directs\n"
        f"original ASCII films from a single idea</span>\n\n\n"
        f"<span class='cta'>{e('▸  type an idea on the left, then press “Make & play”')}</span>\n"
        f"<span class='sub'>or pick one from the gallery below</span>\n\n"
        f"<span class='strip'>{e(strip)}</span>"
    )
    return ("<div class='stage'><div class='bar'><i></i><i></i><i></i>"
            "<span class='barlabel'>ready · awaiting your idea</span></div>"
            f"<pre class='welcome'>{body}</pre></div>")


# ── content filter: refuse profanity, slurs and hate before anything is generated ──
_BANNED = re.compile(r"\b(" + "|".join([
    # profanity
    "fuck", "fucks", "fucking", "fucker", "shit", "bullshit", "bitch", "cunt",
    "asshole", "bastard", "dick", "piss", "slut", "whore", "wank", "prick",
    # racial / ethnic / antisemitic / homophobic / ableist slurs
    "nigger", "nigga", "faggot", "fag", "kike", "spic", "chink", "gook",
    "wetback", "tranny", "retard", "retarded", "coon", "dyke", "paki", "beaner",
    # hate ideology
    "heil hitler", "sieg heil", "white power", "kkk", "gas the jews", "lynch",
]) + r")\b", re.I)


def _blocked(*texts) -> bool:
    """True if any provided text contains banned profanity / slurs / hate terms."""
    return any(_BANNED.search(t or "") for t in texts)


# Per-session "now playing" generation token. Gradio's cancels= does NOT reliably stop
# a running generator (the default film kept streaming over a user's loading screen), so
# every player bumps this token when it starts and bails the moment a newer one supersedes
# it. Keyed by a per-session id (gr.State) so viewers don't interrupt each other.
GEN: dict[str, int] = {}


def _newsid():
    """A fresh per-session id (assigned to a gr.State on page load)."""
    return uuid.uuid4().hex


def _begin(sid):
    """Mark a new playback as the current one for this session; return its token."""
    GEN[sid] = GEN.get(sid, 0) + 1
    return GEN[sid]


def _stream(spec, sid, mine, cards=True):
    """Play a spec inline; yields (html, spec). Stops early if a newer playback in this
    session has superseded `mine`. The lazy frame generator means the first frame is
    instant and the worker yields every frame (so Gradio never restarts the stream)."""
    for grid in render.iter_movie_frames(spec, cards=cards):
        if GEN.get(sid) != mine:                     # a newer film/action took the screen
            return
        yield grid_to_html(grid, spec.get("title", "")), spec
        time.sleep(movies.FRAME_MS / 1000)


FLAGSHIP = "knight.json"   # the film judges see first on load
GALLERY_ORDER = ["knight.json", "paper-boat.json", "rain-cat.json", "troll-dance.json",
                 "snail-race.json", "ghost.json", "bread-dragon.json"]


def _films(folder):
    """title -> json path for every saved film in a folder (best films first)."""
    def rank(p):
        name = os.path.basename(p)
        return (GALLERY_ORDER.index(name) if name in GALLERY_ORDER else 99, name)
    out = {}
    for p in sorted(glob.glob(os.path.join(folder, "*.json")), key=rank):
        try:
            title = json.load(open(p)).get("title") or os.path.basename(p)[:-5]
        except Exception:
            continue
        out[title] = p
    return out


def _featured():
    """A spec to auto-play on load: the flagship film, else any showcase/saved gem."""
    flag = os.path.join(SHOW, FLAGSHIP)
    if os.path.exists(flag):
        return json.load(open(flag))
    for folder in (SHOW, SAVED):
        films = _films(folder)
        if films:
            return json.load(open(next(iter(films.values()))))
    return None


CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap');

:root, .dark{
  --bg:#0e1116; --panel:#0a0c10; --grid:rgba(140,170,200,.05);
  --line:#1c2129; --muted:#79828f; --ink:#e7ebf0;
  --accent:#3ddc97; --accent2:#36c6e0;
}
/* FIXED app height (in px, never vh/%) — on Hugging Face the app sits in an
   auto-resizing iframe; any viewport-relative height feeds back into infinite
   growth. A constant height is the only stable answer. The two panes scroll
   internally; Gradio's own wrappers just size to this fixed app. */
html, body{margin:0}
gradio-app{display:block}
.gradio-container{max-width:100%!important;width:100%!important;overflow:hidden!important;
  margin:0!important;padding:0!important;
  font-family:'JetBrains Mono',ui-monospace,'SFMono-Regular',monospace!important;color:var(--ink)}
body, gradio-app, .gradio-container{background:var(--bg)!important}
.gradio-container .contain{padding:0!important;margin:0!important;max-width:100%!important}
footer{display:none!important}
.gradio-container *{border-color:var(--line)!important}   /* kill stray accent borders */

/* ── two-pane app on charcoal + faint grid ── */
#app{height:760px!important;overflow:hidden!important;
  flex-wrap:nowrap!important;gap:0!important;align-items:stretch!important;
  background-color:var(--bg)!important;
  background-image:linear-gradient(var(--grid) 1px, transparent 1px),
                   linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size:32px 32px}
#shelf{flex:0 0 300px!important;width:300px!important;min-width:300px!important;max-width:300px!important;
  height:760px!important;overflow-x:hidden!important;overflow-y:auto!important;
  flex-direction:column!important;flex-wrap:nowrap!important;align-content:stretch!important;
  background:rgba(8,10,14,.85);border-right:1px solid var(--line);
  padding:16px 16px!important;gap:0!important;box-sizing:border-box!important}
#shelf::-webkit-scrollbar{width:7px}
#shelf::-webkit-scrollbar-thumb{background:#222833;border-radius:4px}
/* let every Gradio wrapper in the shelf shrink to the column (no horizontal overflow) */
#shelf, #shelf *{box-sizing:border-box!important}
#shelf > *,#shelf .block,#shelf .form,#shelf .gr-form,#shelf .wrap,#shelf .gr-group{
  min-width:0!important;max-width:100%!important;margin:0!important}
#shelf .gr-group,#shelf .form,#shelf .block{background:none!important;border:none!important;
  box-shadow:none!important}
/* the textbox wrapper collapses to one line while the auto-grown textarea is taller,
   so it overlaps the next control — force the wrappers to contain their content */
#shelf .block,#shelf .form,#shelf .input-container,#shelf label.container{
  height:auto!important;min-height:0!important;overflow:visible!important}
#cinema{flex:1 1 auto!important;min-width:0!important;height:760px!important;overflow-y:auto;
  display:flex!important;flex-direction:column;align-items:center;justify-content:center;padding:36px!important}

/* shelf brand + section headers (mono, technical) — compact so it all fits, no scroll */
#brand{font-weight:700;font-size:15px;letter-spacing:.06em;color:var(--ink)}
#brand::before{content:"▸ ";color:var(--accent)}
#brandsub{color:var(--muted);font-size:10px;margin:3px 0 0;line-height:1.45}
.shelf-h{color:var(--accent);font-size:9.5px;font-weight:700;text-transform:uppercase;
  letter-spacing:.22em;margin:11px 0 4px;border-top:1px solid var(--line);padding-top:9px}
.shelf-h::before{content:"// "}
/* text inputs: one clean box (no nested wrapper box). Let Gradio size the textarea
   from its `lines` count — don't override padding/line-height/height or it overflows
   its wrapper and overlaps the next control. */
#shelf textarea{font-size:13.5px!important;
  background:#0b0e12!important;border:1px solid #2b3540!important;border-radius:9px!important;
  color:var(--ink)!important;font-family:'JetBrains Mono',monospace!important}
#shelf textarea:focus{border-color:var(--accent)!important;outline:none!important}
#shelf textarea::placeholder{color:#6d7682!important}
/* force the textbox wrappers tall enough to contain the 3-line field so the button
   beneath always clears it (Gradio's wrapper otherwise collapses to one line).
   Use #shelf #id so it beats the #shelf .block{min-height:0} rule above. */
#shelf .form:has(#concept){min-height:84px!important;margin-top:2px!important}
#shelf #concept{min-height:84px!important}
#shelf #concept textarea{height:72px!important}
#shelf button{border-radius:6px!important;font-family:'JetBrains Mono',monospace!important;
  letter-spacing:.03em;min-height:0!important;padding:7px 10px!important;font-size:12px!important;
  margin-top:4px!important}
#shelf .gr-dropdown,#shelf [data-testid='dropdown']{font-size:12px!important}
#shelf fieldset,#shelf .gr-radio{border:none!important;background:none!important;gap:1px!important}
#shelf label,#shelf span{font-family:'JetBrains Mono',monospace!important;font-size:12px!important}

/* now playing — wraps onto a new line, never truncated */
.np{color:var(--ink);font-size:12.5px;line-height:1.35;white-space:normal;
  overflow-wrap:anywhere;padding:2px 0 1px}

/* gallery list at the bottom — one button per film, text wraps (no truncation) */
#shelf button.film{justify-content:flex-start!important;text-align:left!important;
  white-space:normal!important;overflow-wrap:anywhere;line-height:1.25!important;
  font-size:11.5px!important;padding:6px 9px!important;min-height:0!important;
  margin:0 0 3px 0!important;
  color:var(--muted)!important;background:#0c0e12!important;border:1px solid var(--line)!important}
#shelf button.film:hover{color:var(--ink)!important;border-color:var(--accent)!important}
.gradio-container button.primary,.gradio-container .primary{
  background:linear-gradient(92deg,var(--accent),var(--accent2))!important;
  border:none!important;color:#04130d!important;font-weight:700!important;letter-spacing:.04em}

#makebtn{font-size:13.5px!important;padding:11px!important;margin-top:8px!important}
#makerow{display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important;
  gap:6px!important;margin-top:5px!important}
#makerow > *{flex:1 1 0!important;min-width:0!important}
#makerow button{padding:6px!important;font-size:12px!important;width:100%!important}
#stopbtn{color:#ff8a84!important;background:#13171c!important;border:1px solid #3a2a2c!important}
#stopbtn:hover{border-color:#ff5f57!important;color:#ff5f57!important}

/* ── the screen: a clean modern monitor with a status bar + HUD corners ── */
.stage{width:100%;max-width:1040px;margin:0 auto;position:relative;
  font-family:'JetBrains Mono',ui-monospace,monospace}
.stage .bar{display:flex;align-items:center;gap:7px;
  background:#0a0c10;border:1px solid var(--line);border-bottom:none;border-radius:9px 9px 0 0;
  padding:9px 14px}
.stage .bar i{width:8px;height:8px;border-radius:50%;display:inline-block;background:#2b313b}
.stage .bar i:nth-child(1){background:#ff5f57}
.stage .bar b{color:var(--muted);font-size:12px;letter-spacing:.05em;margin-left:8px}
.stage .bar b::before{content:"now_playing: ";color:var(--accent)}
.stage .bar .barlabel{color:var(--muted);font-size:12px;letter-spacing:.05em;margin-left:8px}
/* cinematic welcome card */
.welcome{line-height:1.3!important;font-size:16px!important}
.welcome .ttl{color:#eaf1f5;font-weight:500}
.welcome .strip{color:#27333d;letter-spacing:2px}
.welcome .sub{color:var(--muted);font-size:13px}
.welcome .cta{color:var(--accent);font-weight:700}
.stage pre{position:relative;z-index:1;margin:0;
  background:#0a0d11;
  color:#7df9a6;font-size:18px;line-height:1.14;padding:28px 12px;
  border:1px solid var(--line);border-top:none;border-radius:0 0 9px 9px;white-space:pre;
  text-align:center;overflow:hidden;min-height:430px;box-sizing:border-box}
/* HUD corner brackets */
.stage::before,.stage::after{content:"";position:absolute;width:20px;height:20px;
  pointer-events:none;z-index:2;border:2px solid var(--accent);opacity:.55}
.stage::before{top:-7px;left:-7px;border-right:none;border-bottom:none}
.stage::after{bottom:-7px;right:-7px;border-left:none;border-top:none}
.endcard{max-width:1040px;margin:10px auto 0;color:var(--muted);text-align:center;
  font-family:'JetBrains Mono',monospace;letter-spacing:3px;font-size:13px}

/* rating stars, in the shelf */
#rating{display:flex!important;align-items:center;gap:4px!important;flex-wrap:nowrap!important;margin:2px 0!important}
#rating>*{flex:0 0 auto!important;min-width:0!important;width:auto!important}
#rating button.star{background:none!important;border:none!important;box-shadow:none!important;
  color:#3a414c!important;font-size:22px!important;line-height:1;padding:0 1px!important;
  min-width:0!important;width:auto!important;cursor:pointer;transition:color .12s,transform .12s}
#rating button.star.lit{color:#febc2e!important}      /* cumulative fill (set in JS) */
#rating button.star:hover{transform:scale(1.18)}
#ratemsg{min-height:18px}
#ratemsg .rated{color:#febc2e;font-size:13px}
"""


THEME = gr.themes.Base(
    primary_hue="emerald", neutral_hue="slate",
    font=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
).set(body_background_fill="#0e1116", body_background_fill_dark="#0e1116")


FORCE_DARK = """
() => {
  document.documentElement.classList.add('dark');
  document.body.classList.add('dark');
  document.querySelector('gradio-app')?.classList.add('dark');

  // Star rating: hovering star N fills 1..N; clicking locks that many filled.
  // Colours are set as inline !important styles so they beat Gradio's own button CSS.
  const GOLD = '#febc2e', DIM = '#4b5159';
  const wire = () => {
    const box = document.querySelector('#rating');
    if (!box) { setTimeout(wire, 300); return; }
    if (box.dataset.wired) return; box.dataset.wired = '1';
    const stars = () => Array.from(box.querySelectorAll('button.star'));
    let locked = -1;
    const paint = (upto) => stars().forEach((s, i) =>
        s.style.setProperty('color', i <= upto ? GOLD : DIM, 'important'));
    paint(-1);
    box.addEventListener('mouseover', e => {
      const b = e.target.closest('button.star'); if (b) paint(stars().indexOf(b));
    });
    box.addEventListener('mouseleave', () => paint(locked));
    box.addEventListener('click', e => {
      const b = e.target.closest('button.star'); if (b) { locked = stars().indexOf(b); paint(locked); }
    });
  };
  wire();
}
"""


def build():
    with gr.Blocks(title="LLM Cinema") as demo:    # theme + css + js go to launch() in Gradio 6
        last_spec = gr.State(None)
        sid = gr.State()            # unique per browser session; keys the playback token
        gallery = _films(SHOW)

        with gr.Row(elem_id="app"):
            # ── LEFT: the shelf / nav ──
            with gr.Column(elem_id="shelf", scale=0):
                gr.HTML("<div id='brand'>LLM CINEMA</div>"
                        "<div id='brandsub'>a tiny fine-tuned model writes, draws &amp; "
                        "directs original ASCII films</div>")

                gr.HTML("<div class='shelf-h'>Your film</div>")
                concept = gr.Textbox(show_label=False, lines=3, max_lines=3, elem_id="concept",
                                     placeholder="Describe your film — e.g. a tiny knight afraid of the dark")
                go = gr.Button("▸  Make & play", variant="primary", elem_id="makebtn")
                with gr.Row(elem_id="makerow"):
                    surprise = gr.Button("Surprise", size="sm")
                    stop = gr.Button("Stop", size="sm", elem_id="stopbtn")

                gr.HTML("<div class='shelf-h'>Now playing</div>")
                now_playing = gr.HTML("<div class='np'>—</div>")

                gr.HTML("<div class='shelf-h'>Rate &amp; save</div>")
                with gr.Row(elem_id="rating"):
                    star_btns = [gr.Button("★", elem_classes="star") for _ in range(5)]
                rate_msg = gr.HTML("", elem_id="ratemsg")
                dl = gr.Button("Download GIF", size="sm")
                dlfile = gr.File(label="your film", visible=False)

                gr.HTML("<div class='shelf-h'>Gallery</div>")
                film_btns = [(t, gr.Button(t, elem_classes="film", size="sm")) for t in gallery]

            # ── RIGHT: the cinema ──
            with gr.Column(elem_id="cinema"):
                stage = gr.HTML(_welcome())

        # on load: assign a per-session id + force dark/star-hover (client js), then quietly
        # warm the model endpoints. No auto-played preview — the viewer is invited to make one.
        load_ev = demo.load(_newsid, None, sid, js=FORCE_DARK)
        load_ev.then(lambda: warm_endpoints(), None, None)

        def _create(concept, sid):
            """Write a film, streaming progress to the stage and surfacing any error.
            Yields (stage_html, spec) tuples; on success ends by playing the film."""
            mine = _begin(sid)              # take the screen — supersedes the opening film
            concept = (concept or "").strip()
            if not concept:
                yield _idle("Type a concept first, then press Make & play."), None
                return
            if _blocked(concept):
                yield _idle("Let's keep it friendly — that idea can't be filmed.\n\n"
                            "Try something kind, funny or imaginative."), None
                return
            # Run the model call in a thread and emit a heartbeat ~once a second while
            # it works. This both shows live progress AND keeps the stream alive — a
            # silent 60-90s cold-start block would make Gradio drop and restart the
            # generator, which is what made it loop the intro forever.
            result = {}
            def work():
                try:
                    result["spec"] = movies.direct(concept)
                except Exception as e:                   # network / endpoint failure
                    result["error"] = f"{type(e).__name__}: {e}"
            th = threading.Thread(target=work, daemon=True)
            th.start()
            t0, dots = time.time(), 0
            while th.is_alive():
                if GEN.get(sid) != mine:                 # the viewer started something else
                    return
                dots = dots % 3 + 1
                yield _idle(f"Concept:\n  {concept}\n\nCinema is writing your film"
                            + "." * dots + "\n\n"
                            + f"({int(time.time() - t0)}s — the model may be waking up; "
                              "the first request can take a minute)"), None
                th.join(timeout=0.7)
            if GEN.get(sid) != mine:
                return
            if result.get("error"):
                yield _idle("Could not reach the Cinema model.\n\n"
                            f"{result['error']}\n\nPlease try again in a moment."), None
                return
            spec = result.get("spec")
            if not spec or not spec.get("shots"):
                yield _idle("The model returned nothing usable. Please try again."), None
                return
            # NOTE: we intentionally do NOT persist user films — each creation is private to
            # the maker's own session (per-session playback token) and never shown to others.
            yield _idle(f"\"{spec.get('title', concept)}\"\n\n"
                        f"{len(spec['shots'])} shots written. Drawing and rolling…"), None
            yield from _stream(spec, sid, mine)

        def make_and_play(c, sid):
            yield from _create(c, sid)

        def surprise_me(sid):
            yield from _create(random.choice(SURPRISES), sid)

        def stop_play(sid):
            _begin(sid)                       # supersede any running film/generation
            # re-assert the welcome a few times so a trailing/buffered film frame from the
            # stream we just cancelled can't land on top of it
            for _ in range(5):
                yield _welcome(), None
                time.sleep(0.25)

        go.click(make_and_play, [concept, sid], [stage, last_spec])
        surprise.click(surprise_me, sid, [stage, last_spec])
        stop.click(stop_play, sid, [stage, last_spec])

        def rate(n):
            def f(spec):
                try:
                    with open(os.path.join(HERE, "ratings.jsonl"), "a") as fp:
                        fp.write(json.dumps({"stars": n,
                                             "title": (spec or {}).get("title", "")}) + "\n")
                except Exception:
                    pass
                stars = "★" * n + "☆" * (5 - n)
                return (f"<span class='rated'><b>{stars}</b>"
                        f"&nbsp;&nbsp;Thanks!</span>")
            return f

        for i, b in enumerate(star_btns, 1):
            b.click(rate(i), last_spec, rate_msg)

        def to_gif(spec):
            if not spec:
                return gr.update(visible=False)
            gif, _, _ = render.render_spec(spec)
            return gr.update(value=gif, visible=True)

        dl.click(to_gif, last_spec, dlfile)

        def make_play(title):
            def f(sid):
                path = gallery.get(title)
                if not path:
                    return
                yield from _stream(json.load(open(path)), sid, _begin(sid))
            return f

        for title, btn in film_btns:
            btn.click(make_play(title), sid, [stage, last_spec])

        # keep the shelf "Now playing" in sync with whatever film is on screen (wraps, no truncation)
        def _np(spec):
            title = (spec or {}).get("title") or "—"
            return f"<div class='np'>{html.escape(title)}</div>"

        last_spec.change(_np, last_spec, now_playing)

    # explicit queue: streaming relies on it, and a higher concurrency lets several
    # viewers (judges) watch at once instead of waiting in line
    demo.queue(default_concurrency_limit=12)
    return demo


demo = build()
warm_endpoints()      # start waking the model the moment the Space boots

if __name__ == "__main__":
    demo.launch(theme=THEME, css=CSS)
