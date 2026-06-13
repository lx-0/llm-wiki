#!/usr/bin/env python3
"""Premium infographic for the vault information model — DDoDS/Pachaar style.
Corrected per code-verification: daily/ is co-emitted with raw/ (not derived
from it); knowledge/ is an interlinked consistent wiki, not a generic read-model.
Render: uv run python render_excalidraw.py docs/vault-concept.excalidraw --theme light
"""
import sys
sys.path.insert(0, "/Users/alex/.claude/plugins/cache/yesterday-public-plugins/excalidraw-diagram/1ed96bc84eaf/skills/excalidraw-diagram/references")
from infographic_builder import Scene, PREMIUM as P, FONT

OUT="/Users/alex/Sync/home/alex/Code/WebDev/projects/lx-0/llm-wiki/docs/vault-concept.excalidraw"
s=Scene(1560, 1410)

# ── Title + mascot + hook ───────────────────────────────────────────
s.highlighter(466, 60, 742, 44, P.LAV)
s.text(472, 48, "Where does a thought go?", fs=46, color=P.INK, fam=FONT.DISPLAY, w=820)
s.text(470, 116, "every capture lands in one of three KINDS of place — by its nature, not its topic",
       fs=19, color=P.GRAY, fam=FONT.SANS)
# mascot (confused) + thought
s.place("Shrug", 95, 60, h=120, lib="stick-figures")
s.rect(150, 60, 250, 64, "#FFFFFF", P.INK, rounded=True, sw=2)
s.text(168, 74, "voice? photo?\na task or just a thought?", fs=14, color=P.INK, fam=FONT.HAND)
s.line(150, 110, [[0,0],[-28,18]], color=P.INK, sw=2)  # little tail toward mascot

LX=70; PW=1420
def band(y, h, fill, stroke, tab, sub):
    s.rect(LX, y, PW, h, fill, stroke, rounded=True, sw=2)
    s.rect(LX+18, y-20, 250, 40, fill, stroke, rounded=True, sw=2)
    s.text(LX+18, y-13, tab, fs=18, color=stroke, align="center", w=250, fam=FONT.HAND)
    s.text(LX+290, y-23, sub, fs=14, color=P.GRAY, fam=FONT.SANS)

# ── Band ① CAPTURE ──────────────────────────────────────────────────
by=240; bh=190
band(by, bh, P.BLUE, P.BLUE_S, "①  CAPTURE", "write it down — once as source, once as a dated rollup")
s.pill(LX+40, by+62, 190, 78, "capture event", P.LAV, P.LAV_S, fs=18, sub="voice · photo · email")
s.arrow(LX+240, by+85, dx=120, dy=-8, color=P.BLUE_S, numbered=1)
s.arrow(LX+240, by+108, dx=120, dy=22, color=P.BLUE_S, numbered=1)
s.pill(LX+372, by+34, 300, 70, "raw/", P.BLUE, P.BLUE_S, fs=20, sub="immutable source log · write-once")
s.pill(LX+372, by+112, 300, 70, "daily/<date>/", P.BUTTER, P.BUTTER_S, fs=18, sub="co-emitted rollup — points back to raw")
s.text(LX+710, by+78, "one event, written twice.\nthe rollup is NOT derived from raw —\nboth are siblings of the same capture.",
       fs=15, color=P.INK, fam=FONT.HAND)

# ── Band ② DISTILLATION ─────────────────────────────────────────────
by=490; bh=210
band(by, bh, P.MINT, P.MINT_S, "②  DISTILLATION", "compiled into a real wiki + a daily digest — derived, regenerable")
s.arrow(LX+40, by+95, dx=150, dy=0, color=P.MINT_S, numbered=2)
s.text(LX+40, by+58, "raw/ + daily/", fs=14, color=P.GRAY, fam=FONT.MONO)
s.place("Graph (nodes + edges)", LX+210, by+44, h=92, drop_text=True)
s.pill(LX+330, by+52, 330, 84, "knowledge/", P.MINT, P.MINT_S, fs=22, sub="interlinked · deduped · reconciled · MOCs")
s.text(LX+690, by+44, "A real WIKI — one person's Wikipedia.", fs=17, color=P.MINT_S, fam=FONT.HAND)
s.text(LX+690, by+74, "consistent, cross-linked, deduplicated, kept\ncoherent by the reconcile loop. NOT work docs.\nNOT episodic. NOT a scratch pad.",
       fs=14, color=P.INK, fam=FONT.SANS)
s.pill(LX+330, by+150, 330, 44, "daily/<date>.md  digest", P.BUTTER, P.BUTTER_S, fs=15)
s.text(LX+690, by+158, "≤500-word daily summary, distilled from the captures", fs=13, color=P.GRAY, fam=FONT.SANS)

# ── Band ③ OPERATIONAL ──────────────────────────────────────────────
by=750; bh=210
band(by, bh, P.CORAL, P.CORAL_S, "③  OPERATIONAL", "the one mutable-state layer — your working desk")
s.pill(LX+40, by+78, 180, 64, "intake", P.LAV, P.LAV_S, fs=17, sub="voice · photo")
# the dividing-line decision
s.text(LX+232, by+44, "carries an", fs=13, color=P.GRAY, fam=FONT.SANS)
s.text(LX+232, by+62, "open loop?", fs=18, color=P.CORAL_S, fam=FONT.HAND)
s.arrow(LX+232, by+110, dx=110, dy=-30, color=P.CORAL_S)
s.arrow(LX+232, by+110, dx=110, dy=8, color=P.MINT_S)
s.arrow(LX+232, by+110, dx=110, dy=44, color=P.NEUTRAL_S)
s.pill(LX+352, by+50, 360, 46, "task · idea  →  workspace/", P.CORAL, P.CORAL_S, fs=16)
s.pill(LX+352, by+104, 360, 40, "note  →  knowledge/", P.MINT, P.MINT_S, fs=15)
s.pill(LX+352, by+150, 360, 36, "none  →  dropped", P.NEUTRAL, P.NEUTRAL_S, fs=14)
s.text(LX+740, by+70, "workspace/ holds open loops with a status\n(pending → done / dismissed). Your agent may\nread AND write here — the only content layer\nit works inside. Kept clear & distillable.",
       fs=14, color=P.INK, fam=FONT.SANS)

# ── Classification matrix (the table) ───────────────────────────────
ty=1010
s.text(LX, ty, "THE SAME FIVE, CLASSIFIED", fs=18, color=P.INK, fam=FONT.HAND)
s.text(LX+340, ty+3, "two axes: cognitive nature  ×  lifecycle / authority", fs=13, color=P.GRAY, fam=FONT.SANS)
cols=[("LAYER",150),("TIER",170),("NATURE",230),("MUTABILITY",240),("OWNER",230)]
cx=[LX]
for _,w in cols: cx.append(cx[-1]+w)
tw=cx[-1]-LX
hy=ty+34; rh=58
s.rect(LX,hy,tw,32,P.NEUTRAL,P.NEUTRAL_S,rounded=False,sw=1)
for i,(c,w) in enumerate(cols):
    s.text(cx[i]+12,hy+8,c,fs=12,color=P.INK,fam=FONT.SANS)
rows=[
 ("raw/","capture","source evidence","immutable","collector",P.BLUE_S),
 ("daily/","capture + distill","episodic","append-only","collector · hook",P.BUTTER_S),
 ("knowledge/","distillation","semantic","derived · regenerable","LLM (compile)",P.MINT_S),
 ("workspace/","operational","intentional · open loop","MUTABLE · pending→done","operator + agent",P.CORAL_S),
]
for r,(layer,tier,nat,mut,own,acc) in enumerate(rows):
    ry=hy+32+r*rh
    s.rect(LX,ry,tw,rh,"#FFFFFF" if r%2==0 else "#FBF7EE","#E0D9C8",rounded=False,sw=1)
    s.rect(LX,ry,7,rh,acc,acc,rounded=False,sw=0)
    s.text(cx[0]+16,ry+rh/2-10,layer,fs=15,color=acc,fam=FONT.HAND)
    s.text(cx[1]+12,ry+rh/2-9,tier,fs=12.5,color=P.INK,fam=FONT.SANS)
    s.text(cx[2]+12,ry+rh/2-9,nat,fs=12.5,color=P.INK,fam=FONT.SANS)
    s.text(cx[3]+12,ry+rh/2-9,mut,fs=12.5,color=P.INK,fam=FONT.SANS)
    s.text(cx[4]+12,ry+rh/2-9,own,fs=12.5,color=P.INK,fam=FONT.SANS)
s.rect(LX,hy,tw,32+len(rows)*rh,"transparent",P.INK,rounded=False,sw=1.5)
# happy mascot at the resolution
s.place("Happy", LX+tw+30, hy+40, h=120, lib="stick-figures")

# ── Thesis ──────────────────────────────────────────────────────────
s.thesis("Classify information by whether it carries an open loop — not by its topic.", y=1352)
s.save(OUT)
print("saved", OUT)
