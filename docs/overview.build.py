#!/usr/bin/env python3
"""Premium README hero for llm-wiki — restyle of docs/overview.png.
Card-grid layout, DDoDS/Pachaar premium style. Counts verified against code
(13 substrate sources = 12 collectors + sessions hook; 8 knowledge categories;
4 agents). Includes the workspace/+intents capability (operator opt-in to show
pre-ship). Render: render_excalidraw.py docs/overview.excalidraw --theme light"""
import sys
sys.path.insert(0, "/Users/alex/.claude/plugins/cache/yesterday-public-plugins/excalidraw-diagram/1ed96bc84eaf/skills/excalidraw-diagram/references")
from infographic_builder import Scene, PREMIUM as P, FONT

OUT="/Users/alex/Sync/home/alex/Code/WebDev/projects/lx-0/llm-wiki/docs/overview.excalidraw"
s=Scene(1660, 1020)
LX=70

# ── Title ───────────────────────────────────────────────────────────
s.highlighter(LX+2, 56, 322, 50, P.LAV)
s.text(LX+8, 44, "llm-wiki", fs=54, color=P.INK, fam=FONT.DISPLAY, w=420)
s.text(LX+10, 116, "self-cartography engine", fs=22, color=P.LAV_S, fam=FONT.HAND)
s.text(LX+10, 152, "an LLM-compiled Obsidian wiki that you and your agents read from — and write back into — daily",
       fs=16, color=P.GRAY, fam=FONT.SANS)
s.place("Happy", 1470, 40, h=140, lib="stick-figures")
s.text(1300, 150, "you read what the\nagent wrote.", fs=14, color=P.GRAY, fam=FONT.HAND)

# ── Stat strip ──────────────────────────────────────────────────────
def stat(x, num, label, fill, stroke):
    s.rect(x, 205, 360, 96, fill, stroke, rounded=True, sw=2)
    s.text(x, 222, num, fs=44, color=stroke, align="center", w=360, fam=FONT.DISPLAY)
    s.text(x, 274, label, fs=14, color=P.INK, align="center", w=360, fam=FONT.SANS)
gap=22; sw_=360
stat(LX,            "13", "substrate sources",   P.BLUE,   P.BLUE_S)
stat(LX+(sw_+gap),  "4",  "agents wired in",     P.LAV,    P.LAV_S)
stat(LX+2*(sw_+gap),"8",  "knowledge categories",P.MINT,   P.MINT_S)
stat(LX+3*(sw_+gap),"MIT","open source · prototype",P.BUTTER,P.BUTTER_S)

# ── Feature card grid (3×3) ─────────────────────────────────────────
cards=[
 ("Two-path ingest", P.BLUE, P.BLUE_S, "Claude sessions + 12 collectors land in\nraw/ + daily/ — one event, written as\nsource AND dated rollup."),
 ("Compile → query", P.MINT, P.MINT_S, "Claude SDK distills raw/+daily/ into an\ninterlinked wiki. Local $0 query over it."),
 ("Multi-agent hooks", P.LAV, P.LAV_S, "session-end → flush + piggybacks:\ncompile · curiosity · dream-cycle ·\nsuggestions · reconcile."),
 ("Curiosity loop", P.BUTTER, P.BUTTER_S, "local Ollama finds knowledge gaps after\ncompile → queued deep-scan requests.\nNo cloud."),
 ("Self-healing wiki", P.MINT, P.MINT_S, "dedup · concept-reconcile · materialized\nbacklinks · broken-link + contradiction\nscan."),
 ("workspace/ + intents", P.CORAL, P.CORAL_S, "voice/photo captures classified into\ntasks & ideas → agent-actioned,\noperator-gated."),
 ("Operator self-reports", P.LAV, P.LAV_S, "psychometric instruments scored on your\nown substrate; weekly cross-instrument\nmeta-report."),
 ("Hard facts", P.CORAL, P.CORAL_S, "operator-authored facts override every\nsource; propagated vault-wide on the\nnext compile."),
 ("Graph + dashboard", P.BLUE, P.BLUE_S, "Obsidian dashboard, multi-channel graph,\ndomain MOCs — your portrait, navigable\nby you + agents."),
]
cw=502; ch=168; cgap=24; cx0=LX; cy0=345
for i,(title,fill,stroke,body) in enumerate(cards):
    r,c=divmod(i,3)
    x=cx0+c*(cw+cgap); y=cy0+r*(ch+cgap)
    s.rect(x,y,cw,ch,"#FFFFFF",P.NEUTRAL_S,rounded=True,sw=1.5)          # card frame
    s.rect(x+16,y-14,min(len(title)*15+40,330),34,fill,stroke,rounded=True,sw=2)  # title pill
    s.text(x+16,y-8,title,fs=16,color=P.INK,align="center",w=min(len(title)*15+40,330),fam=FONT.HAND)
    s.text(x+22,y+44,body,fs=14.5,color=P.INK,fam=FONT.SANS,w=cw-44)

# ── Thesis ──────────────────────────────────────────────────────────
s.thesis("You read what the agent wrote. The agent reads what you wrote. Both refine the same surface.", y=960)
s.save(OUT)
print("saved", OUT)
