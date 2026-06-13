#!/usr/bin/env python3
"""Generator for docs/vault-concept.excalidraw — the fundamental vault model.
Light-authored (white bg, pastel fills, mono font 3) → rendered with --theme dark
to match docs/architecture.png + docs/overview.png house style."""
import json, itertools

_seed = itertools.count(700001)
def s(): return next(_seed)

E = []
def base(**kw):
    d = dict(angle=0, strokeWidth=2, strokeStyle="solid", fillStyle="solid",
             roughness=0, opacity=100, groupIds=[], frameId=None, roundness=None,
             seed=s(), version=1, versionNonce=s(), isDeleted=False,
             boundElements=[], updated=1, link=None, locked=False)
    d.update(kw); return d

def rect(id, x, y, w, h, fill="transparent", stroke="#0A0A0A", sw=2, radius=True):
    x,y,w,h=float(x),float(y),float(w),float(h)
    E.append(base(id=id, type="rectangle", x=x, y=y, width=w, height=h,
                  strokeColor=stroke, backgroundColor=fill, strokeWidth=sw,
                  roundness=({"type":3} if radius else None)))

def text(id, x, y, t, fs=14, color="#0A0A0A", w=None, align="left", font=3):
    x,y=float(x),float(y)
    lines = t.split("\n")
    if w is None: w = int(max(len(l) for l in lines) * fs * 0.6) + 6
    h = int(len(lines) * fs * 1.25) + 4
    E.append(base(id=id, type="text", x=x, y=y, width=w, height=h,
                  strokeColor=color, backgroundColor="transparent", strokeWidth=1,
                  text=t, originalText=t, fontSize=fs, fontFamily=font,
                  textAlign=align, verticalAlign="top", lineHeight=1.25,
                  containerId=None))
    return w, h

def line(id, pts, stroke="#737373", sw=1, style="solid"):
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    x0,y0=pts[0]
    E.append(base(id=id, type="line", x=x0, y=y0,
                  width=max(xs)-min(xs), height=max(ys)-min(ys),
                  strokeColor=stroke, backgroundColor="transparent", strokeWidth=sw,
                  strokeStyle=style, points=[[p[0]-x0,p[1]-y0] for p in pts]))

def arrow(id, x1,y1,x2,y2, stroke="#FC4E14", sw=2, style="solid"):
    E.append(base(id=id, type="arrow", x=x1, y=y1, width=x2-x1, height=y2-y1,
                  strokeColor=stroke, backgroundColor="transparent", strokeWidth=sw,
                  strokeStyle=style, points=[[0,0],[x2-x1,y2-y1]],
                  startBinding=None, endBinding=None,
                  startArrowhead=None, endArrowhead="arrow"))

# palette (light-authored; inverts well under --theme dark, matches architecture.excalidraw)
ORANGE="#FC4E14"; SLATE="#737373"; INK="#0A0A0A"
BLUE_F="#EFF6FF"; BLUE_S="#2563EB"
GOLD_F="#FFECB9"; GOLD_S="#92610F"
MINT_F="#E6F4EC"; MINT_S="#1B7340"
CORAL_F="#FFD8CB"; CORAL_S="#C43D2E"
PURP_S="#7C3AED"; PURP_F="#F3EEFF"
CARD="#FFFFFF"

W=1520
# ── Title ───────────────────────────────────────────────────────────
text("title","0",40,"ANATOMY OF A KNOWLEDGE BASE",34,INK,w=W,align="center",font=5)
text("subtitle","0",92,"five layers of one vault — classified by the NATURE of the information, not its topic",16,SLATE,w=W,align="center")
line("rule_top",[(110,128),(W-110,128)],SLATE,1)

# ── Section A: the lifecycle spine (CQRS) ───────────────────────────
text("secA","110",150,"① HOW INFORMATION MOVES  ·  capture → write-model → read-model  +  a separate operational store",15,ORANGE,font=3)

# capture node (left)
rect("cap_box",110,200,210,150,PURP_F,PURP_S,2)
text("cap_t",128,214,"CAPTURE",15,PURP_S)
text("cap_b",128,242,"voice · photo\nemail · meetings\nsessions",12.5,INK)
text("cap_n",128,318,"raw intake events",11,SLATE)

# write model band
rect("wm_box",420,180,300,250,"transparent",SLATE,1);
text("wm_lbl",432,190,"WRITE MODEL  (append-only fact stream)",11.5,SLATE)
rect("raw_box",440,220,260,80,BLUE_F,BLUE_S,2)
text("raw_t",456,232,"raw/",15,BLUE_S)
text("raw_b",456,258,"immutable source log · write-once",11.5,INK)
rect("daily_box",440,320,260,80,GOLD_F,GOLD_S,2)
text("daily_t",456,332,"daily/",15,GOLD_S)
text("daily_b",456,358,"episodic time-series log · append-only",11.5,INK)

# read model
rect("kn_box",800,180,290,110,MINT_F,MINT_S,2)
text("kn_t",818,194,"knowledge/",16,MINT_S)
text("kn_b",818,222,"semantic READ-MODEL\nmaterialized view · derived,\nregenerable",11.5,INK)

# operational store
rect("ws_box",800,330,290,110,CORAL_F,CORAL_S,3)
text("ws_t",818,344,"workspace/",16,CORAL_S)
text("ws_b",818,372,"OPERATIONAL store · the ONLY\nmutable-state layer · open loops",11.5,INK)

# arrows
arrow("a_cap_wm",320,275,438,270,PURP_S,2)
arrow("a_wm_kn",702,250,798,235,MINT_S,2)
text("compile_lbl",712,210,"compile\n(materialize)",10.5,MINT_S)
arrow("a_wm_ws",660,405,800,390,CORAL_S,2,"dotted")
text("router_lbl",1100,360,"← router sends\n  open-loops here",11,CORAL_S)
text("desc_lbl",1100,210,"← descriptive:\n  what is / was /\n  is known",11,MINT_S)

line("rule_a",[(110,470),(W-110,470)],SLATE,1)

# ── Section B: the classification matrix (THE TABLE) ────────────────
text("secB","110",492,"② THE CLASSIFICATION  ·  two orthogonal axes — cognitive nature × lifecycle/authority",15,ORANGE)

tbl_x=110; tbl_y=530;
cols=[("LAYER",150),("COGNITIVE NATURE",230),("DATA-STRUCTURE ANALOGUE",330),("MUTABILITY",210),("OWNER",220)]
col_x=[tbl_x];
for _,w in cols: col_x.append(col_x[-1]+w)
tbl_w=col_x[-1]-tbl_x
rowh=64; header_h=34

# header
rect("th",tbl_x,tbl_y,tbl_w,header_h,"#E5E5E5","#0A0A0A",1,radius=False)
for i,(c,w) in enumerate(cols):
    text(f"th_{i}",col_x[i]+12,tbl_y+10,c,12,INK)

rows=[
 ("raw/","— (source evidence)","append-only event log","immutable","collector",BLUE_S),
 ("daily/","episodic","time-series / partitioned log","append-only","collector · hook",GOLD_S),
 ("knowledge/","semantic","materialized view (read-model)","derived · regenerable","LLM (compile)",MINT_S),
 ("workspace/","operational / intentional","transactional store + state-machine","MUTABLE · pending→done","operator + their agent",CORAL_S),
]
for r,(layer,nat,ds,mut,own,accent) in enumerate(rows):
    ry=tbl_y+header_h+r*rowh
    fill=CARD if r%2==0 else "#F7F7F7"
    rect(f"tr_{r}",tbl_x,ry,tbl_w,rowh,fill,"#D0D0D0",1,radius=False)
    rect(f"tab_{r}",tbl_x,ry,6,rowh,accent,accent,0,radius=False)  # accent tab
    text(f"c0_{r}",col_x[0]+14,ry+rowh//2-12,layer,14.5,accent)
    text(f"c1_{r}",col_x[1]+12,ry+rowh//2-9,nat,12,INK)
    text(f"c2_{r}",col_x[2]+12,ry+rowh//2-9,ds,12,INK)
    text(f"c3_{r}",col_x[3]+12,ry+rowh//2-9,mut,12,INK)
    text(f"c4_{r}",col_x[4]+12,ry+rowh//2-9,own,12,INK)
# table border
rect("tbl_border",tbl_x,tbl_y,tbl_w,header_h+len(rows)*rowh,"transparent","#0A0A0A",1.5,radius=False)

# callout under table
co_y=tbl_y+header_h+len(rows)*rowh+22
rect("callout",tbl_x,co_y,tbl_w,56,GOLD_F,GOLD_S,2)
text("callout_t",tbl_x+18,co_y+10,"THE DIVIDING LINE  —  does it carry an open loop / a state?  →  workspace/ (operational).   Otherwise it's descriptive (raw · daily · knowledge).",13,INK)
text("callout_b",tbl_x+18,co_y+33,"You classify by lifecycle, not by topic.",11.5,SLATE)

line("rule_b",[(110,co_y+92),(W-110,co_y+92)],SLATE,1)

# ── Section C: the kind router ──────────────────────────────────────
rc_y=co_y+114
text("secC","110",rc_y,"③ THE INTAKE ROUTER  ·  one classifier splits each capture by whether it carries an open loop",15,ORANGE)
# four outcomes, all BELOW the header
outs=[("task","actionable → workspace/",CORAL_F,CORAL_S),
      ("idea","incubate → workspace/",CORAL_F,CORAL_S),
      ("note","reference → knowledge/",MINT_F,MINT_S),
      ("none","noise → dropped","#ECECEC",SLATE)]
ox=420; first_oy=rc_y+44; step=44; oboxh=34
out_center=first_oy+((len(outs)-1)*step+oboxh)/2
# capture node vertically centered on the outcome stack
rect("rt_cap",110,out_center-35,170,70,PURP_F,PURP_S,2)
text("rt_cap_t",126,out_center-21,"capture event\n(voice · photo)",12.5,PURP_S)
for i,(k,d,f,st) in enumerate(outs):
    oy=first_oy+i*step
    rect(f"out_{i}",ox,oy,360,oboxh,f,st,2)
    text(f"out_k_{i}",ox+14,oy+8,k,13,st)
    text(f"out_d_{i}",ox+90,oy+9,d,12,INK)
    arrow(f"out_a_{i}",282,out_center,ox-4,oy+oboxh/2,st,1.5)

text("kind_note","820",first_oy+6,"kind + status frontmatter.\nTriage promotes note → knowledge/,\nkeeps task/idea as open loops\nuntil done / dismissed.",12,SLATE)

# ── Bottom thesis ───────────────────────────────────────────────────
th_y=first_oy+(len(outs)-1)*step+oboxh+48
rect("thesis_bg",110,th_y,W-220,60,"#1A1A1A","#1A1A1A",0)
text("thesis","130",th_y+13,"Classify information by whether it carries an open loop — not by its topic.  Four layers describe reality; one holds what's still in motion.",15,"#FFFFFF",w=W-260,align="center")

doc=dict(type="excalidraw",version=2,source="vault-concept",
         elements=E, appState=dict(viewBackgroundColor="#FFFFFF",gridSize=None), files={})
json.dump(doc, open("/Users/alex/Sync/home/alex/Code/WebDev/projects/lx-0/llm-wiki/docs/vault-concept.excalidraw","w"), indent=1)
print("wrote", len(E), "elements")
