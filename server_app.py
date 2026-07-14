"""
LLM Cinema — CUSTOM frontend on gr.Server (Gradio's FastAPI API engine).

This is the "off-brand" build: instead of Gradio components, we serve our OWN
HTML/CSS/JS cinema and stream frames over Server-Sent Events from FastAPI routes
on a gr.Server instance. The film engine (movies + render) is reused as-is.

Run:    python server_app.py
Deploy: HF Space (set app_file: server_app.py). Same CLAUDEMOVIES_LLM_* secrets.
"""

import html
import json
import os
import re
import threading
import time
import uuid

import gradio as gr
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

import movies
import render

W, H = render.W, render.H
HERE = os.path.dirname(__file__)
SHOW = os.path.join(HERE, "showcase")

# ── content filter (profanity / slurs / hate) ──
_BANNED = re.compile(r"\b(" + "|".join([
    "fuck", "fucks", "fucking", "fucker", "shit", "bitch", "cunt", "asshole", "bastard",
    "dick", "piss", "slut", "whore", "nigger", "nigga", "faggot", "fag", "kike", "spic",
    "chink", "gook", "wetback", "tranny", "retard", "coon", "dyke", "paki", "beaner",
    "heil hitler", "sieg heil", "white power", "kkk", "gas the jews",
]) + r")\w*", re.I)        # \w* catches suffix variants (shitty, fucking, dickhead); leading \b avoids embeds


def _blocked(t):
    return bool(_BANNED.search(t or ""))


_MAXLEN = 60
# common prompt-injection / jailbreak patterns — neutralised so nobody can steer the model
_INJECT = re.compile(
    r"(ignore\s+(all\s+|the\s+)?(previous|prior|above|earlier)"
    r"|disregard\s+(all|the|previous|prior)"
    r"|system\s+prompt|you\s+are\s+now|act\s+as\s+(a|an|if)"
    r"|jailbreak|developer\s+mode|override\s+(the|your)"
    r"|forget\s+(everything|all|the)|new\s+instructions)", re.I)


def _clean_concept(s):
    """Authoritative server-side sanitiser: strip control chars / markup, collapse whitespace,
    and HARD-cap to 60 chars so a single short film idea is all the model ever receives."""
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s or "")        # control chars, newlines, tabs
    s = "".join(ch for ch in s if ch.isprintable())
    s = re.sub(r"[<>{}`\\]", "", s)                      # markup / structural chars
    s = re.sub(r"\s+", " ", s).strip()
    return s[:_MAXLEN]


def _films(folder):
    out = {}
    order = ["knight.json", "paper-boat.json", "rain-cat.json", "troll-dance.json",
             "snail-race.json", "ghost.json", "bread-dragon.json"]
    paths = sorted(__import__("glob").glob(os.path.join(folder, "*.json")),
                   key=lambda p: (order.index(os.path.basename(p)) if os.path.basename(p) in order else 99,
                                  os.path.basename(p)))
    for p in paths:
        try:
            out[json.load(open(p)).get("title") or os.path.basename(p)[:-5]] = p
        except Exception:
            continue
    return out


def grid_to_html(grid, title=""):
    rows = []
    for r in range(H):
        cells, row, i = grid[r], "", 0
        while i < W:
            col, j, seg = cells[i][1], i, ""
            while j < W and cells[j][1] == col:
                seg += cells[j][0]
                j += 1
            hexc = "#%02x%02x%02x" % col if isinstance(col, tuple) else "#7df9a6"
            esc = html.escape(seg)
            row += f"<span style='color:{hexc}'>{esc}</span>" if seg.strip() else esc
            i = j
        rows.append(row)
    bar = (f"<div class='bar'><i></i><i></i><i></i><b>now_playing: {html.escape(title)}</b></div>")
    return f"{bar}<pre>{chr(10).join(rows)}</pre>"


def _tint(grid):
    """The frame's lit colour and 'energy' — a saturation/brightness-weighted average of the
    drawn cells, so the audience glow becomes a low-opacity MIRROR of the action on screen.
    Energy is keyed to how much is lit, so sparse frames (the title/credit cards) glow ~0."""
    tr = tg = tb = tw = 0.0
    lit = 0
    for row in grid:
        for cell in row:
            ch = cell[0]
            if ch == " " or ch == "":
                continue
            r, g, b = cell[1]
            lit += 1
            mx, mn = max(r, g, b), min(r, g, b)
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            sat = (mx - mn) / mx if mx else 0.0
            w = lum * (0.35 + sat)                       # vivid + bright cells lead the colour
            tr += r * w; tg += g * w; tb += b * w; tw += w
    cov = lit / float(W * H)
    energy = max(0.0, min(1.0, (cov - 0.10) * 6.0))      # cards are sparse -> ~0 -> no glow
    if tw <= 0:
        return [150, 180, 235], 0.0
    return [int(tr / tw), int(tg / tw), int(tb / tw)], round(energy, 3)


def _payload(grid, title=""):
    tint, energy = _tint(grid)
    return {"html": grid_to_html(grid, title), "tint": tint, "lvl": energy}


def _screen(msg, label="ready"):
    bar = f"<div class='bar'><i></i><i></i><i></i><b>{html.escape(label)}</b></div>"
    return f"{bar}<pre class='msg'>{html.escape(msg)}</pre>"


def _sse(frames):
    for fr in frames:
        payload = fr if isinstance(fr, dict) else {"html": fr}
        yield "data: " + json.dumps(payload) + "\n\n"
    yield "data: " + json.dumps({"done": True}) + "\n\n"


# ── the custom frontend: a real cinema-hall photo as the backdrop, the ASCII film
#    projected onto the screen, and all controls docked along the bottom ──
PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>LLM Cinema</title>
<meta name=description content="A small model writes, draws and directs original ~90-second ASCII films.">
<meta property="og:title" content="LLM Cinema">
<meta property="og:description" content="A small model writes, draws and directs original ASCII films. Presented by Conductor Creative Labs.">
<meta property="og:type" content="website">
<meta property="og:image" content="https://conductorailabs-llm-cinema.hf.space/static/share.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="LLM Cinema">
<meta name="twitter:description" content="A small model writes, draws and directs original ASCII films.">
<meta name="twitter:image" content="https://conductorailabs-llm-cinema.hf.space/static/share.png">
<link rel=preconnect href=https://fonts.googleapis.com>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel=stylesheet>
<style>
:root{--accent:#3ddc97;--accent2:#36c6e0;--ink:#e7ebf0}
*{box-sizing:border-box;margin:0}
html,body{height:100%;font-family:'JetBrains Mono',ui-monospace,monospace;background:#04060a;color:var(--ink);overflow:hidden}
/* the photo (with a transparent screen cut-out) sits ON TOP; the film screen is BEHIND
   it and shows through the hole — pixel-perfect. While a film plays we dim the PHOTO itself
   (its transparent hole stays clear so the screen stays bright) and pool soft light below. */
#bg{position:fixed;inset:0;width:100%;height:100%;object-fit:cover;z-index:1;
  filter:brightness(.62) saturate(.9);transition:filter 1.4s ease}
/* while a film plays the whole room goes really dark */
body.playing #bg{filter:brightness(.3) saturate(.78)}
/* the projection, BEHIND the photo, fills the cut-out hole */
#screen{position:fixed;left:22.3%;top:11.1%;width:57.7%;height:43.9%;z-index:0;background:#04060a;
  display:flex;align-items:center;justify-content:center;overflow:hidden}
#screen .bar{display:none}
/* REVEAL: a second copy of the photo at near-full brightness, shown ONLY through a soft,
   very blurry blob rising from UNDER the screen. The projector light "uncovers" the dark
   room (reveals the photo's own opacity) rather than painting white on top of it. */
#reveal{position:fixed;inset:0;z-index:2;pointer-events:none;opacity:0;
  background:url(static/cinema.png) center/cover no-repeat;
  filter:brightness(1.12) saturate(1.04) blur(8px);
  -webkit-mask-image:
     linear-gradient(to bottom, transparent 0 58%, #000 80%),
     radial-gradient(56% 48% at 51% 75%, #000 0%, rgba(0,0,0,.5) 44%, transparent 80%);
  -webkit-mask-composite:source-in;
  mask-image:
     linear-gradient(to bottom, transparent 0 58%, #000 80%),
     radial-gradient(56% 48% at 51% 75%, #000 0%, rgba(0,0,0,.5) 44%, transparent 80%);
  mask-composite:intersect;
  transition:opacity 1.4s ease, filter .22s linear}
/* the colour-mirror bloom over the reveal — JS sets its colour per frame (transparent until then) */
#spill{position:fixed;inset:0;z-index:3;pointer-events:none;opacity:0;mix-blend-mode:screen;
  background:transparent;filter:blur(40px);transition:opacity 1.4s ease, filter .22s linear;
  -webkit-mask-image:linear-gradient(to bottom, transparent 0 58%, #000 76%);
  mask-image:linear-gradient(to bottom, transparent 0 58%, #000 76%)}
body.playing #reveal{opacity:1}
body.playing #spill{opacity:1}
#brand{position:fixed;top:16px;left:20px;z-index:4;font-weight:700;letter-spacing:.06em;font-size:15px;
  text-shadow:0 1px 8px #000}#brand b{color:var(--accent)}
#screen pre{margin:0;white-space:pre;text-align:center;color:#cfd6df;line-height:1.12;
  font-size:clamp(11px,1.5vw,19px);text-shadow:none}
#screen pre.msg{color:var(--ink)}
/* opening-credits sequence, projected on the screen while the film renders */
#credwrap{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:20px;text-align:center;padding:0 6%;opacity:0;transition:opacity 1.1s ease;color:#eef2f6}
#credwrap.show{opacity:1}
.cr-s{font-size:clamp(10px,1.45vw,17px);letter-spacing:.42em;text-transform:uppercase;color:#cfd6df;line-height:1.9}
.cr-s b{color:#fff;font-weight:700}
.cr-big{font-size:clamp(30px,6.6vw,82px);font-weight:700;letter-spacing:.07em;line-height:.96;
  text-shadow:0 0 42px rgba(238,242,246,.22)}
/* the ANSI-shadow ASCII title — WHITE, sized per context (#screen pre would otherwise
   force its green film-frame style, so these need the #screen id for specificity) */
#screen pre.cr-title{margin:0;white-space:pre;line-height:1.0;color:#eef2f6;text-align:center;
  font-size:clamp(4px,0.78vw,9px);text-shadow:0 0 26px rgba(238,242,246,.2)}
#screen pre.wel-title{margin:0;white-space:pre;line-height:1.0;color:#eef2f6;text-align:center;
  font-size:clamp(4px,0.72vw,8px);text-shadow:0 0 16px rgba(238,242,246,.16)}
#screen pre.cr-art{font-size:clamp(7px,1.05vw,13px);line-height:1.05;color:#8b94a2;margin-top:4px;
  white-space:pre;text-shadow:none}
.cr-sub{font-size:clamp(9px,1.2vw,14px);letter-spacing:.5em;text-transform:uppercase;color:#9aa3b0;
  animation:lpulse 1.8s ease-in-out infinite}
/* the idle "now showing" welcome card on the theatre screen */
.scene-center{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:14px;text-align:center;padding:0 6%;color:#eef2f6}
.w-dir{font-size:clamp(8px,1.15vw,13px);color:#aab2bd;letter-spacing:.03em;line-height:1.7;max-width:84%;margin-top:2px}
.w-dir .wlink{color:#cfd6df;text-decoration:underline}.w-dir .wlink:hover{color:#fff}
/* controls docked along the bottom, over the audience */
#controls{position:fixed;left:0;right:0;bottom:0;z-index:4;padding:18px 22px 20px;
  background:linear-gradient(to top,rgba(4,6,10,.97),rgba(4,6,10,.78) 65%,transparent)}
#crow{display:flex;gap:10px;align-items:center;max-width:1120px;margin:0 auto 10px;width:100%}
#concept{flex:1;min-width:0;background:rgba(11,14,18,.92);border:1px solid #2b3540;border-radius:11px;
  color:var(--ink);padding:12px 15px;font:14px 'JetBrains Mono',monospace}
#concept:focus{outline:none;border-color:var(--accent)}
#controls button{border:none;border-radius:11px;padding:12px 18px;cursor:pointer;white-space:nowrap;
  font:700 13px 'JetBrains Mono',monospace;color:var(--ink);background:#222b36}
#controls button:hover{filter:brightness(1.18)}
#go{background:linear-gradient(92deg,var(--accent),var(--accent2));color:#04130d}
#stop{color:#ff8a84;background:#16191f;border:1px solid #3a2a2c}
#gallery{display:flex;gap:8px;overflow-x:auto;max-width:1120px;margin:0 auto;width:100%;
  padding-bottom:3px;scrollbar-width:thin}
#gallery .film{flex:0 0 auto;background:rgba(12,15,20,.8);border:1px solid #2b3540;color:#aeb6c2;
  border-radius:9px;padding:8px 13px;font-size:12px;cursor:pointer;white-space:nowrap}
#gallery .film:hover{color:#fff;border-color:var(--accent)}
#gallery::-webkit-scrollbar{height:6px}#gallery::-webkit-scrollbar-thumb{background:#2a3340;border-radius:3px}
/* off-grid download note — always visible under the controls */
#foot{max-width:1120px;margin:9px auto 0;text-align:center;font-size:11px;color:#8b94a2;letter-spacing:.02em}
#foot a{color:#aeb6c2;text-decoration:underline}#foot a:hover{color:#fff}
/* About button + modal */
#aboutbtn{position:fixed;top:14px;right:16px;z-index:6;background:rgba(11,14,18,.7);border:1px solid #2b3540;
  color:#cfd6df;border-radius:9px;padding:7px 14px;font:600 12px 'JetBrains Mono',monospace;cursor:pointer;
  letter-spacing:.06em;text-transform:uppercase;backdrop-filter:blur(4px)}
#aboutbtn:hover{color:#fff;border-color:var(--accent)}
#about{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;padding:20px;
  background:rgba(2,4,8,.8);backdrop-filter:blur(6px);opacity:0;pointer-events:none;transition:opacity .35s ease}
#about.show{opacity:1;pointer-events:auto}
#about .card{position:relative;max-width:560px;max-height:86vh;overflow:auto;background:#0b0e13;
  border:1px solid #232c38;border-radius:16px;padding:30px 32px;color:#dfe5ec;box-shadow:0 24px 80px rgba(0,0,0,.6)}
#about h1{font-size:22px;letter-spacing:.06em;margin-bottom:8px}#about h1 b{color:var(--accent)}
#about .lead{color:#aeb6c2;font-size:13px;line-height:1.65;margin-bottom:6px}
#about h2{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:#8b94a2;margin:18px 0 9px}
#about ul{list-style:none;display:flex;flex-direction:column;gap:9px}
#about li{font-size:12.5px;line-height:1.5;color:#cfd6df}#about li b{color:#fff}
#about code{background:#161b22;border-radius:4px;padding:1px 5px;font-size:11.5px}
#about .foot2{margin-top:20px;padding-top:16px;border-top:1px solid #1c242f;font-size:12.5px;color:#9aa3b0;line-height:1.8}
#about .foot2 b{color:#eef2f6}#about a{color:var(--accent2);text-decoration:none}#about a:hover{text-decoration:underline}
#about .x{position:absolute;top:14px;right:18px;color:#8b94a2;font-size:24px;line-height:1;cursor:pointer}
#about .x:hover{color:#fff}
/* ── mobile: stack the input over the buttons so nothing is cut off, and keep clear of the
   phone's home indicator with the safe-area inset ── */
#fs.mob{display:none}                     /* fullscreen toggle: mobile only */
@media (max-width:680px){
  /* on mobile, placeScreen() zooms the photo so the theatre screen fills the width and pins
     #screen to it (nothing cut off). The photo-reveal glow assumes desktop cover, so hide it. */
  #reveal{display:none}
  /* the theatre screen is short & wide on mobile — shrink intro content so it fits, not clips */
  .scene-center{gap:7px;padding:0 4%}
  #screen pre.wel-title,#screen pre.cr-title{font-size:clamp(3px,1.5vw,6px)}
  #screen pre.cr-art{display:none}                 /* drop the decorative reel on mobile */
  .cr-s{font-size:9px;letter-spacing:.22em;line-height:1.45}
  .cr-sub{font-size:8px;letter-spacing:.26em}
  .w-dir{font-size:8.5px;line-height:1.4;max-width:94%}
  #controls{padding:10px 10px calc(10px + env(safe-area-inset-bottom,0px))}
  #crow{flex-wrap:wrap;gap:7px;margin-bottom:8px}
  #concept{flex:1 1 100%;font-size:13px;padding:11px 13px;border-radius:9px}
  #controls button{flex:1 1 auto;padding:11px 8px;font-size:12px;border-radius:9px}
  #fs.mob{display:inline-block;flex:1 1 100%;background:#16191f;border:1px solid #2b3540;color:#cfd6df}
  #brand{font-size:12px;top:10px;left:12px}
  #gallery{gap:6px}
  #gallery .film{font-size:11px;padding:7px 10px}
  #foot{font-size:9.5px;margin-top:7px}
}
/* full-screen loader so the scene reveals all at once (no elements popping in) */
#loader{position:fixed;inset:0;z-index:99;background:#04060a;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:20px;text-align:center;transition:opacity 1.1s ease}
#loader.hide{opacity:0;pointer-events:none}
#loader .lsmall{color:#eef2f6;font-size:12px;letter-spacing:.55em;text-transform:uppercase;
  animation:lpulse 1.8s ease-in-out infinite}
#loader .lbig{font-weight:700;letter-spacing:.04em;color:#eef2f6;
  text-shadow:0 0 34px rgba(238,242,246,.22)}
/* the ANSI-shadow ASCII title (LLM CINEMA) — rendered as a monospace block */
pre#loadtitle{margin:0;white-space:pre;line-height:1.0;font-size:clamp(5px,1.0vw,11px);
  text-align:center}
#loader .lbar{width:min(280px,52vw);height:2px;background:#161b22;border-radius:2px;overflow:hidden}
#loader .lbar::after{content:"";display:block;height:100%;width:42%;
  background:linear-gradient(90deg,transparent,#eef2f6,transparent);animation:lslide 1.25s linear infinite}
@keyframes lpulse{0%,100%{opacity:.45}50%{opacity:1}}
@keyframes lslide{0%{transform:translateX(-120%)}100%{transform:translateX(330%)}}
</style></head><body>
<div id=loader>
  <div class=lsmall>presented by conductor creative labs</div>
  <pre id=loadtitle class=lbig>LLM CINEMA</pre>
  <div class=lbar></div>
</div>
<div id=screen></div>
<img id=bg src="static/cinema.png" alt="">
<div id=reveal></div>
<div id=spill></div>
<div id=brand>&#9654; LLM <b>CINEMA</b></div>
<button id=aboutbtn>about</button>
<div id=about><div class=card><div class=x id=aboutx>&times;</div>
  <h1>LLM <b>CINEMA</b></h1>
  <div class=lead>Cinema is a fine-tuned <b>MiniCPM3-4B</b> &mdash; a four-billion-parameter model that
    <b>writes, draws, and directs</b> original ASCII short films. It invents the story, draws every
    character, picks the terrain, camera and mood, then stages and plays it frame by frame. No video,
    no footage &mdash; pure imagination, one frame at a time.</div>
  <h2>How it earns its badges</h2>
  <ul>
    <li>&#127912; <b>Off-Brand</b> &mdash; a fully custom <code>gr.Server</code> front end (this whole cinema), well past the default Gradio look.</li>
    <li>&#128028; <b>Tiny Titan</b> &mdash; runs on a genuinely tiny <b>4B</b> model, under the &le;4B bar.</li>
    <li>&#128268; <b>Off the Grid</b> &mdash; can <b>optionally</b> run as a fully local build with <b>no cloud APIs</b>.</li>
    <li>&#129433; <b>Llama Champion</b> &mdash; the model runs through the <b>llama.cpp</b> runtime.</li>
    <li>&#128211; <b>Field Notes</b> &mdash; the build is written up in the repo.</li>
  </ul>
  <h2>Small &amp; local</h2>
  <div class=lead>Just 4B parameters &mdash; small enough to run on your laptop. Download the off-the-grid
    build and run it locally on llama.cpp, no cloud needed.
    <a href="https://huggingface.co/spaces/build-small-hackathon/llm-cinema/blob/main/LOCAL_LLAMACPP.md" target=_blank rel=noopener>Get the local build &#8599;</a></div>
  <div class=foot2>Presented by <b>Conductor Creative Labs</b><br>
    <a href="https://conductorailabs.com" target=_blank rel=noopener>conductorailabs.com</a></div>
</div></div>
<div id=controls>
  <div id=crow>
    <input id=concept maxlength=60 autocomplete=off spellcheck=false
      placeholder="Describe your film — e.g. a tiny knight afraid of the dark">
    <button id=go>&#9654; Make &amp; play</button>
    <button id=surprise>Surprise</button>
    <button id=replay>&#8635; Replay</button>
    <button id=stop>Stop</button>
    <button id=fs class=mob>&#9974; Fullscreen</button>
  </div>
  <div id=gallery></div>
  <div id=foot>Generates live in the cloud here &middot; <a href="https://huggingface.co/spaces/build-small-hackathon/llm-cinema/blob/main/LOCAL_LLAMACPP.md" target=_blank rel=noopener>&#128268; download the off-the-grid build &mdash; runs locally on llama.cpp &#8599;</a></div>
</div>
<script>
const screen=document.getElementById('screen');
// ── ANSI-shadow ASCII font for the LLM CINEMA title (loader + opening credits) ──
let GLYPH=null;
function asciiWord(t){if(!GLYPH)return t;t=t.toUpperCase();
  let rows=[];for(let r=0;r<6;r++){let line="";
    for(const c of t){line+= c===' ' ? '    ' : (GLYPH[c]?GLYPH[c][r]:'    ');}rows.push(line);}
  return rows.join('\n');}
function asciiTitle(){return asciiWord('LLM')+'\n'+asciiWord('CINEMA');}   // stacked, fits narrow screens
function paintLoaderTitle(){const el=document.getElementById('loadtitle');if(el&&GLYPH)el.textContent=asciiTitle();}
fetch('static/ansifont.json').then(r=>r.json()).then(g=>{GLYPH=g;paintLoaderTitle();
  if(!es&&!playTimer&&!phase)welcome();}).catch(()=>{});   // re-render welcome with the ASCII title
const SURPRISES=["a tiny knight who is afraid of the dark","a lonely robot who finds a stray cat",
"a dragon who would rather bake than fight","a snail who dreams of racing the wind",
"a little ghost afraid of humans","a candle racing the dawn"];
let es=null;
// ── loader: reveal the whole scene at once, once the bg image + gallery are ready ──
const loader=document.getElementById('loader');
let bgReady=false,galReady=false,minDone=false;
function reveal(){if(bgReady&&galReady&&minDone){loader.classList.add('hide');
  setTimeout(()=>{loader.style.display='none';},1200);}}
(function(){const b=document.getElementById('bg');
  if(b.complete&&b.naturalWidth>0)bgReady=true; else b.addEventListener('load',()=>{bgReady=true;reveal();});
  setTimeout(()=>{minDone=true;reveal();},1600);                 // min on-screen time for the copy
  setTimeout(()=>{bgReady=galReady=minDone=true;reveal();},7000);})(); // safety: never hang
const revealEl=document.getElementById('reveal'), spillEl=document.getElementById('spill');
// fit a full film frame (80x18 grid) to exactly fill the screen box without cropping the
// subtitle — measured from real glyph metrics, so it tracks the cut-out at any size.
let _fs=null;
function fit(force){const p=screen.querySelector('pre'); if(!p||p.classList.contains('msg'))return;
  if(_fs&&!force){p.style.fontSize=_fs+'px';return;}
  p.style.fontSize='10px';
  const cw=p.scrollWidth/10, ch=p.scrollHeight/10;
  if(!cw||!ch)return;
  _fs=(Math.min(screen.clientWidth/cw, screen.clientHeight/ch)*0.99).toFixed(2);
  p.style.fontSize=_fs+'px';}
// map the film screen EXACTLY onto the photo's cut-out (x596..2102, y172..807 of 2638x1478).
// DESKTOP: the photo is object-fit:cover; mirror that transform. MOBILE (portrait): a landscape
// photo can't cover without hiding the screen, so we ZOOM the photo so the cut-out fills the
// width and pin #screen to it — the theatre screen stays the focus and nothing is cut off.
const SX=596,SY=172,SW=1507,SH=636,IW=2638,IH=1478;
function placeScreen(){const bg=document.getElementById('bg'),vw=window.innerWidth,vh=window.innerHeight;
  if(vw<=680){                                   // mobile: zoom to the screen
    const s=(vw*0.96)/SW, lx=vw*0.02, ty=vh*0.16;
    bg.style.position='fixed';bg.style.objectFit='fill';bg.style.right='auto';bg.style.bottom='auto';
    bg.style.width=(IW*s)+'px';bg.style.height=(IH*s)+'px';
    bg.style.left=(lx-SX*s)+'px';bg.style.top=(ty-SY*s)+'px';
    screen.style.left=lx+'px';screen.style.top=ty+'px';
    screen.style.width=(SW*s)+'px';screen.style.height=(SH*s)+'px';
  }else{                                          // desktop: match object-fit:cover
    bg.style.position='';bg.style.objectFit='';bg.style.right='';bg.style.bottom='';
    bg.style.width='';bg.style.height='';bg.style.left='';bg.style.top='';
    const s=Math.max(vw/IW,vh/IH), ox=(vw-IW*s)/2, oy=(vh-IH*s)/2;
    screen.style.left=(ox+SX*s)+'px';screen.style.top=(oy+SY*s)+'px';
    screen.style.width=(SW*s)+'px';screen.style.height=(SH*s)+'px';
  }}
placeScreen();
window.addEventListener('resize',()=>{placeScreen();_fs=null;if(screen.querySelector('pre'))fit(true);});
function show(h){screen.innerHTML=h;fit();}
function playing(on){document.body.classList.toggle('playing',on);
  if(!on){revealEl.style.opacity='';revealEl.style.filter='';spillEl.style.background='';}}
function welcomeHTML(){const title=GLYPH?("<pre class='wel-title'>"+asciiTitle()+"</pre>")
    :"<div class='cr-big'>LLM CINEMA</div>";
  return "<div class='scene-center'>"+title
    +"<div class='cr-s'>presented by conductor creative labs</div>"
    +"<div class='w-dir'>Type an idea below and press &ldquo;Make &amp; play&rdquo; &mdash; a small model will "
    +"write, draw and direct your film. Or pick one from the gallery. "
    +"You can also <a class='wlink' href='https://huggingface.co/spaces/build-small-hackathon/llm-cinema/blob/main/LOCAL_LLAMACPP.md' target='_blank' rel='noopener'>run it off the grid, locally on llama.cpp</a>.</div></div>";}
function welcome(){playing(false);screen.innerHTML=welcomeHTML();}   // set directly (no fit() on the title pre)
// one film frame -> screen + the colour-mirror glow (used live AND on replay)
function renderFilmFrame(d){show(d.html);playing(true);
  if(d.tint){const r=d.tint[0],g=d.tint[1],b=d.tint[2],e=(d.lvl||0);
    const a=(0.15*e).toFixed(3), a2=(0.05*e).toFixed(3);
    spillEl.style.background='radial-gradient(76% 56% at 51% 70%, rgba('+r+','+g+','+b+','+a+') 0%, '
      +'rgba('+r+','+g+','+b+','+a2+') 46%, transparent 78%)';
    revealEl.style.opacity=Math.min(0.7,e*1.4).toFixed(3);
    revealEl.style.filter='brightness('+(1.06+0.12*e).toFixed(3)+') saturate(1.05) blur(8px)';}}
// ── intro: while the model writes, hold the TITLE + a status; when it's done, fade to a
//    short "presented by" bumper, then play the film (buffered so nothing is skipped) ──
const BUMPER=[
  "<div class='cr-s'>Conductor&nbsp;Creative&nbsp;Labs<br><b>presents</b></div>",
  "<div class='cr-s'>in conjunction with<br><b>Hugging&nbsp;Face&nbsp;Spaces &amp; Gradio</b></div>"];
function showCard(inner){screen.innerHTML="<div id=credwrap>"+inner+"</div>";
  const w=document.getElementById('credwrap');requestAnimationFrame(()=>{if(w)w.classList.add('show');});}
function fadeCard(){const w=document.getElementById('credwrap');if(w)w.classList.remove('show');}
function startWriting(){phase='writing';playing(true);
  revealEl.style.opacity='0';spillEl.style.background='';      // dim the house only — no glow yet
  const t=GLYPH?("<pre class='cr-title'>"+asciiTitle()+"</pre>"):"<div class='cr-big'>LLM CINEMA</div>";
  showCard(t+"<div class='cr-sub'>now writing and directing, please wait</div>");}
function playBumper(done){let i=0;
  (function step(){
    if(i>=BUMPER.length){fadeCard();creditsTimer=setTimeout(done,900);return;}
    showCard(BUMPER[i]);
    creditsTimer=setTimeout(()=>{fadeCard();creditsTimer=setTimeout(()=>{i++;step();},700);},2200);})();}
// ── streaming + a buffer so any film can be replayed exactly ──
let phase=null,buf=[],playTimer=null,creditsTimer=null,streamDone=false;
function startBufferedPlay(){phase='playing';let i=0;
  playTimer=setInterval(()=>{
    if(i<buf.length){renderFilmFrame(buf[i++]);}
    else if(streamDone){clearInterval(playTimer);playTimer=null;playing(false);}},150);}
function stopStream(){if(es){es.close();es=null;}
  if(playTimer){clearInterval(playTimer);playTimer=null;}
  if(creditsTimer){clearTimeout(creditsTimer);creditsTimer=null;}}
function stop(){stopStream();phase=null;welcome();}
function stream(url,withCredits){stopStream();phase=null;buf=[];streamDone=false;
  if(withCredits)startWriting();
  es=new EventSource(url);
  es.onmessage=e=>{const d=JSON.parse(e.data);
    if(d.done){streamDone=true;if(es){es.close();es=null;}
      if(!withCredits){playing(false);} return;}        // gallery stops here; make drains its buffer
    if(d.phase)return;                                  // heartbeat while writing -> hold the title
    if(!d.html)return;
    const film=d.html.indexOf('<span')>=0;
    if(!film){stopStream();phase=null;show(d.html);playing(false);return;}  // terminal message
    buf.push(d);
    if(withCredits){
      if(phase==='writing'){phase='bumper';playBumper(startBufferedPlay);}  // first frame -> bumper
      return;}                                          // bumper/playing: buffered player renders
    renderFilmFrame(d);};                               // gallery: render live
  es.onerror=()=>{if(es){es.close();es=null;}if(phase==null)playing(false);};}
function replay(){if(!buf.length)return;stopStream();phase='playing';
  const frames=buf.slice();let i=0;playing(true);
  playTimer=setInterval(()=>{if(i>=frames.length){clearInterval(playTimer);playTimer=null;playing(false);return;}
    renderFilmFrame(frames[i++]);},150);}
const concept=document.getElementById('concept');
function make(){const c=concept.value.trim().slice(0,60);
  if(!c){concept.focus();return;}
  stream('api/make?concept='+encodeURIComponent(c),true);}
document.getElementById('go').onclick=make;
concept.addEventListener('keydown',e=>{if(e.key==='Enter')make();});
document.getElementById('surprise').onclick=()=>{const c=SURPRISES[Math.floor(Math.random()*SURPRISES.length)];
  concept.value=c;stream('api/make?concept='+encodeURIComponent(c),true);};
document.getElementById('replay').onclick=replay;
document.getElementById('stop').onclick=stop;
// About modal
const aboutEl=document.getElementById('about');
document.getElementById('aboutbtn').onclick=()=>aboutEl.classList.add('show');
document.getElementById('aboutx').onclick=()=>aboutEl.classList.remove('show');
aboutEl.onclick=e=>{if(e.target===aboutEl)aboutEl.classList.remove('show');};
document.addEventListener('keydown',e=>{if(e.key==='Escape')aboutEl.classList.remove('show');});
// fullscreen (mobile): go fullscreen and try to lock landscape for a proper cinema view
document.getElementById('fs').onclick=()=>{const d=document, el=d.documentElement;
  if(d.fullscreenElement||d.webkitFullscreenElement){(d.exitFullscreen||d.webkitExitFullscreen||function(){}).call(d);return;}
  const req=el.requestFullscreen||el.webkitRequestFullscreen;
  if(req){const p=req.call(el); const lock=()=>{try{window.screen.orientation&&window.screen.orientation.lock&&
      window.screen.orientation.lock('landscape').catch(()=>{});}catch(e){}};
    if(p&&p.then)p.then(lock).catch(()=>{}); else lock();}};
fetch('api/gallery').then(r=>r.json()).then(films=>{const g=document.getElementById('gallery');
  films.forEach(n=>{const b=document.createElement('button');b.className='film';b.textContent=n;
    b.onclick=()=>stream('api/play?name='+encodeURIComponent(n),false);g.appendChild(b);});
  galReady=true;reveal();}).catch(()=>{galReady=true;reveal();});
welcome();
</script></body></html>"""


server = gr.Server(title="LLM Cinema")


@server.get("/")
def index():
    return HTMLResponse(PAGE)


@server.get("/static/cinema.png")
def bg_image():
    return FileResponse(os.path.join(HERE, "static", "cinema.png"))


@server.get("/static/ansifont.json")
def ansifont():
    return FileResponse(os.path.join(HERE, "static", "ansifont.json"), media_type="application/json")


@server.get("/static/share.png")
def share_image():
    return FileResponse(os.path.join(HERE, "static", "share.png"), media_type="image/png")


@server.get("/api/gallery")
def gallery():
    return JSONResponse(list(_films(SHOW).keys()))


@server.get("/api/play")
def play(name: str):
    path = _films(SHOW).get(name)
    if not path:
        return JSONResponse({"error": "not found"}, status_code=404)
    spec = json.load(open(path))

    def frames():
        for grid in render.iter_movie_frames(spec):
            yield _payload(grid, spec.get("title", ""))
            time.sleep(movies.FRAME_MS / 1000)
    return StreamingResponse(_sse(frames()), media_type="text/event-stream")


@server.get("/api/make")
def make(concept: str):
    concept = _clean_concept(concept)               # sanitise + hard 60-char cap (authoritative)

    def frames():
        if not concept:
            yield _screen("Type a short film idea to begin.", "ready")
            return
        if _blocked(concept) or _INJECT.search(concept):
            yield _screen("Let's keep it friendly — try a kind, fun film idea.", "blocked")
            return
        result = {}

        def work():
            try:
                result["spec"] = movies.direct(concept)
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"
        th = threading.Thread(target=work, daemon=True)
        th.start()
        t0 = time.time()
        while th.is_alive():
            # heartbeats keep the SSE alive while the client plays the opening credits
            yield {"phase": "writing", "t": int(time.time() - t0)}
            th.join(timeout=0.7)
        if result.get("error") or not (result.get("spec") or {}).get("shots"):
            yield _screen("Could not reach the model. Please try again.", "error")
            return
        spec = result["spec"]
        for grid in render.iter_movie_frames(spec):
            yield _payload(grid, spec.get("title", ""))
            time.sleep(movies.FRAME_MS / 1000)
    return StreamingResponse(_sse(frames()), media_type="text/event-stream")


if __name__ == "__main__":
    # HF Spaces runs this file as a script and injects GRADIO_SERVER_NAME/PORT.
    server.launch(server_name=os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0"),
                  server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")))
