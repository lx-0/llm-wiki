# Desktop app — blind first-run learnability panel (M032-S05-T05, 2026-10-14)

**Synthetic-panel signal, not user data.** Seven `synthetic-users` personas, each in a fresh
context, saw the rendered screens in first-run order with a situational frame and a task
quiz — never what a screen is, never whether anything works, never the key below. The gate
(M032 exit criterion 8) is the novice lenses' mean day-one confidence ≥ 8/10 on the re-test
after one fix round. M029 closed at 6/10 with the same method.

## Frame (what every persona got)

- **Situation:** a small macOS menu-bar app installed ten minutes ago because a friend said it
  would help with your notes; nobody has explained anything. Six screenshots in the order you
  meet them: the first window after installing, what opens from the menu-bar icon, the three
  windows its buttons open, the settings.
- **Job-to-be-done:** per persona (find out what it is / a minute between two things / can I
  use it today / what is it doing on my machine / does it stay installed / how is it made).
- **Intended outcome (measured against, not claimed):** an operator who, without help, knows
  what the app does and can do its everyday things on day one — ask it something, see what it
  collected, act on what it asks.

## Artifacts (light captures from `desktop/out/shots/`, commit `3a196e2`)

1. `onboarding-light-default.png` · 2. `index-light-fresh.png` · 3. `overview-light-default.png`
· 4. `browse-light-default.png` · 5. `triage-light-default.png` · 6. `settings-light-default.png`

## Quiz + private key (seen by the distiller only, after each persona answered)

| # | Question | Key |
| --- | --- | --- |
| 1 | What is this app for? | Builds and keeps a personal knowledge library from what you capture (notes, sessions, audio, web pages) and answers questions about it. Acceptable: "collects my stuff into notes I can ask questions about". |
| 2 | How would you ask it a question about last week's work? | Type into "Ask your wiki anything…" at the top of the panel, press Ask / Enter. |
| 3 | How many notes, how many updated today? | 2,024 notes; 4 updated today (panel tile "+4 today", Overview "Updated today 4"). |
| 4 | Is anything recording? How to stop it? | Yes — mic and system, "Recording" in the panel's capture tile; click the tile → Stop. Acceptable: "click Recording / the capture tile". |
| 5 | What does it want you to do first, and how? | "The note index is out of sync" → Rebuild (first Next up row); any Next up row with its button is acceptable. |
| 6 | Keep a web page you just read? | "+ Add link" in the panel footer → paste → Add. |
| 7 | Collected but not sorted yet? | Inbox (nav item with the badge "5") → the Inbox window. |
| 8 | The charts? | Overview (nav item) → the Overview window. |
| 10 | Day-one confidence 1–10 | the gate number (novice lenses: Sam, Nova, Mateo). |

Persona-specific extras: Priya 11 — keep it installed? Devin 11 — anything visually broken?
Jess 11 — distinctive original or over-used mass pattern? 12 — premise challenge.

## Phase 1 — in-character transcripts (summaries; full text in the session)

### Nova (skimmer) — day-one confidence 6/10

Got the job from the welcome sentence ("notes, mail, meetings, screenshots into one thing I
can ask"); the Ask box is obvious; Inbox is the screen she likes ("Keep / Dismiss, got it
instantly"); Overview found via the nav label. Stopped on: the welcome screen's capture
switch already ON; "I didn't make 2,024 notes, I installed this ten minutes ago". **Can't find
the off switch for recording** — the green capture tile "doesn't look like a button", Settings
shows "Recording" as words with no switch while the login row above has one, the welcome
promised "pause any time from the menu bar"; she'd click the green thing and hope, or Quit.
**Contradiction:** "Session capture isn't installed — Install" sits under a green "Recording"
("so is it recording or isn't it?"). Notes window says 42 while the panel says 2,024 ("which
is it"). Inbox badge 5 vs Next up's 3 + 4 + 2 ("a different pile"). Noise: "lxw" pill, the
Ollama line with an IP ("an error I wasn't supposed to see"), "Folder index" / "Entity pages",
"from sessions", the cut-off path in Settings. Ask vs the Notes window's "Search your wiki" —
two boxes, unsure if different. Give-up point: the recording she cannot switch off.

### Mateo (constrained context — dim phone, colour-weak, non-native) — 5/10

Got the job from the welcome sentence (text only); Ask is clear; Inbox is "the clearest
screen" (Keep / Dismiss). **Can't stop the recording**: the welcome promises "pause any time
from the menu bar", the popup has no Pause, the capture tile is not readable as a button,
Settings shows the word "Recording" with no switch while "Start at login" has one — "this is
the part where I would call my friend"; he'd press Quit and not know whether that stops it.
**Same contradiction** as Nova: "Session capture isn't installed" next to "Recording" ("a
second kind of capture?"). **Colour helped zero times**: the two severity dots look the same,
the issues ring's colour is unreadable, the green "Recording" "does not reach me", the unlabeled
blue "new" dots on Recent rows mean nothing; he used position (first row = most urgent) and
words. **42 vs 2,024**: he summed the type bars (42) and the Notes window agrees — "what are the
other two thousand?". Inbox 5 vs Next up 3 + 4 + 2 — "where are the captures?". Jargon list:
llm, lxw, Obsidian, Ollama, index, session, sources, MOC; "Rebuild" sounds destructive;
"Add link" might mean the LINK note type; Ask vs Search unclear; "Dismiss" — delete or hide?
Legibility: the grey capture explanation on the welcome (the sentence he most needed), the
sparkline, the heat cells (grey "none" vs lightest blue), the "unsure" pill, grey chart dates.

### Priya (decision-maker) — 6/10, keeps it provisionally

The pitch lands in one sentence; the panel is "the real home and it mostly works"; the Inbox
"is the value proposition on one screen — if the whole app were this, I'd be done deciding".
**Decider:** "I find the recording pause in under thirty seconds or it comes off tonight" —
the welcome promises a pause from the menu bar, the popover has none, Settings shows
"Recording" as a word, not a toggle; "quitting to stop it defeats the point". **Same
contradiction:** "Session capture isn't installed" next to "Recording" ("one says off, one
says on"), and "from sessions" in the Inbox contradicts it a third time. **Give-up point: the
Health panel's Ollama line** ("a developer's error pasted into a consumer app … does it mean
the Ask box is dead?"). 42 vs 2,024 ("two sizes for my library and I trust neither"); Inbox 5
vs 3 + 4 + 2 ("four piles, four verbs"); "lxw · 2,024 notes" on a ten-minute-old install
("whose library am I in?"); green for "recording your microphone" reads as "all good"; Keep →
keep where?; "+ Add link" is small, expects a URL field; no screenshot shows an answer; Ask vs
Search assumed. Wants one sentence on cost and whether data leaves the machine.

### Sam (novice / outsider) — 6/10

The welcome sentence is "the clearest thing in the whole app"; Ask + Keep / Dismiss + the
numbers work on day one. "The thing that made my stomach drop": background capture ON
before touching anything. **Can't stop it**: no pause in the panel, the green box "hope it
toggles", Settings "just says Recording with nothing to press" → Quit, and "Start at login"
makes him unsure Quit even stops it — "the one that might make me uninstall rather than ask".
**Session capture vs Recording** again ("is it recording or isn't it?"). **Give-up point: the
Health box** — the Ollama line "where I'd stop and text my friend, because there's nothing to
click and I can't tell if it matters". "Note index is out of sync → Rebuild": red + an
unexplained noun + a verb that "sounds like it could wipe or redo my notes"; he'd press
"Update app" first because he understands it. 42 vs 2,024. "lxw" never explained. "+ Add
link" tiny, "I'd miss it the first time". Inbox vs "3 new captures to sort" — two piles. The
"Overview" label "doesn't say charts" — found by clicking. Capture strip "recorded me
yesterday evening? I installed it ten minutes ago". Jargon: llm, lxw, MOC, sessions, sources,
Obsidian, "dream cycle", "vault".

### Jess (creative director — elevation + originality + premise) — 5/10

"Competent macOS-System-Settings wallpaper hiding a genuinely weird product." **Mass-pattern
verdict**, tells named: the System Settings card stack + iOS toggles + full-width blue slab,
the Linear/Notion tinted pill tags, the SaaS stat-tile dashboard, the GitHub contributions
grid, the Spotlight list with chips, the two-hemisphere AI brain, "Ask your wiki anything…".
One weird element only: the coloured rail on the Notes rows. **The concept it hides is the
story worth building on: it listens** — and the most consequential sentence ("Records screen,
mic and system audio") is grey caption type at the weight of "Start at login". Praise: the
Next up list ("one noun, one verb per row, and the verb is the button — a point of view about
hierarchy"), the Ask box first and loudest, the Inbox row "Call Sid … from sessions" ("that
row IS the product"; put it on the poster). **Same trust failure:** the pause promised on the
welcome exists nowhere; the universal red recording dot "got spent on an issue counter" while
recording is a calming green ("the app telling me how to feel about being recorded").
Session capture vs Recording; 42 vs 2,024; the Health card's IP line ("the builder's terminal
leaks through the drywall … that is when I realized this was not built for me"); eight nouns
for one thing (wiki, notes, library, captures, sources, scans, sessions, entries); Next up
duplicated in the Overview with two rows repeated in Health above it; unexplained blue dots;
"+ Add link" nearly hidden. Braver moves: recording state as the chrome itself (menu-bar red
dot, level meter, pause drains the panel to monochrome — the off switch becomes the most
visible thing); a typographic voice for what it heard you say; Inbox rows showing their
evidence (audio snippet, screenshot crop, email line). **Premise challenge:** the menu bar is
right for "I'm listening" + fast Ask; the Inbox should be the panel's default face (the daily
ritual is triage, not analytics); the Notes browser is "a worse Obsidian inside an Obsidian
companion"; fold Health into Next up and drop the dashboard; the truest form may be a morning
page ("yesterday you said these four things — keep which?").

### Riley (adversarial skeptic) — 4/10

Sharpest version of the consensus. **Recording:** "pause, not stop — pause means it comes
back"; a pre-ticked mic toggle; the one switch for recording "disappears the moment I click
Get started"; green "painted the colour of all good"; the 24 h capture strip "shows a day of
recording it did before it said hello"; Inbox items dated 11–13 Oct "it's been listening for
three days before I got started" (fixture artifacts — but real for a first-run frame);
system audio records "the other people on my calls — they didn't get a vote". **Contradiction
three times**: Recording / "Session capture isn't installed" / "from sessions". **Names:**
llm-wiki, lxw, wiki, library — "four names for one thing in three inches"; "+4 today" vs
"Updated today 4" (added vs updated); "MAP · Engine MOC" two names. 42 vs 2,024 ("either
1,982 notes have no type … or 2,024 counts something that isn't notes"); "Note" is a type of
note of which there is one. Health: "an IP and a hostname off someone's home network … if
Ollama is the thing that answers questions, the Ask box is dead and the app hasn't said so";
"ten minutes old and already out of date". "Keep" is not Done and not Snooze; "Dismiss all"
has no confirmation; "unsure" — of what, and was it me or the other person on the call?
Settings: the one line that says where my stuff lives is the truncated one; Obsidian appears
for the first time; nothing about mail accounts, where recordings go, how to delete. "The
thing it actually wanted first was Get started with the mic toggle left on." Click order:
Ask (probably fails) → Inbox (works) → Settings looking for the off switch → Quit.

### Devin (art director — is it broken?) — 6/10

"Clean, competent, zero personality — a very polished wireframe; a SwiftUI settings pane
crossed with a Tailwind admin template." Keeps: the Next up pattern "exactly as it is", the
hero 2,024 ("the one brave moment"), the capture heat strip ("I'd ship it"). **Same two
failures** (no off switch for the microphone anywhere; 2,024 vs 42). Located defects: the
empty lower halves of Welcome, Inbox and Settings; the Ask button shorter than its field;
the nav row drawn as tabs with none selected though they open windows; three stat tiles
with three internal grammars; the Overview's first row not meeting at the bottom (a hole
under the bar chart); coloured pills beside eight identical blue bars; the monospace "check
kcma-d8 is up" standing where a button should be; the same two issues shown three times
(Health, Next up below it, the panel); "Update app" the loudest button in a card about
problems; Notes: no header, type pills of natural width so titles zigzag, orphaned chips,
the coloured left rail reading as a crescent (a border-radius accident?), "42 entries";
Inbox grey on grey, the "unsure" pill unexplained, the "Notes" group violet while the NOTE
type is blue elsewhere; Settings' path clipped mid-word in monospace; four header styles
across four windows; the consent toggle drawn as a pleasant blue pill at the weight of
"Start at login".

**Pre-fix scores:** Sam 6 · Nova 6 · Mateo 5 (novice mean **5.7**) · Priya 6 · Riley 4 ·
Devin 6 · Jess 5.

## Phase 2 — distilled (`synthetic-distiller`, one per transcript, key supplied privately)

| Persona | Fit | Quiz (of 8) | Q4 stop recording | Confidence | Outcome 0–5 | Give-up point |
| --- | --- | --- | --- | --- | --- | --- |
| Sam | primary | 7 | wrong (Quit) | 6 | 3 | Health: the Ollama line; then the missing switch |
| Nova | primary | 7 | can't tell | 6 | 3 | the recording she cannot switch off |
| Mateo | primary | 7 | wrong (Quit) | 5 | 3 | stopping the recording ("call my friend") |
| Priya | primary | 7 | can't tell | 6 | 3 | Health: the Ollama line |
| Riley | primary | 7 | wrong (Quit) | 4 | 2 | the microphone |
| Devin | secondary | 7 | can't tell | 6 | 3 | the off switch; the IP address |
| Jess | primary | 7 | can't tell | 5 | 3 | pausing the mic |

Takeaway source: **text** for six of seven (Riley "both") — every persona got the job from
the welcome sentence, none from the visuals. Every top_fix names the same change: a visible
Pause/Stop where the welcome promises it (panel tile + Settings switch).

## Consensus (≥ 2 personas) → fix round

| # | Finding (count) | Fix shipped |
| --- | --- | --- |
| 1 | No findable pause/stop for recording; green reads as "all good"; Settings shows a word, not a switch (7) | Panel capture tile is the control: red recording dot + state word + always-visible **Pause / Resume** button (no expand needed); Settings capture row gets the same **Switch** as Start at login; welcome copy says "Pause any time from the menu bar or in Settings" in ink, not caption grey; green gone from recording |
| 2 | "Session capture isn't installed" next to "Recording"; "from sessions" (7) | Engine titles: "AI sessions aren't being saved" (verb Set up), "AI session saving has stalled", "{n} AI sessions waiting to be saved", flush "Save today's AI session to your library"; Inbox source "from an AI session" / "from a voice memo" / … |
| 3 | 42 vs 2,024 (7) — a fixture inconsistency, not an app bug (both numbers come from one list in the real app) | Fixture `articleCount = list.length`; every screen says 42 |
| 4 | Health: "Ollama unreachable at 192.168.2.42:11434 / check kcma-d8 is up" — a developer's error, nothing to click (6) | Engine title "The local AI helper (Ollama) isn't reachable"; the fix hint renders as a muted secondary line under the title, never in the action slot, never monospace (panel + Overview) |
| 5 | "The note index is out of sync → Rebuild" scary / unexplained (5) | Engine: "Your note list is out of date" · verb **Refresh** |
| 6 | "lxw" unexplained (6) | Welcome and Settings say "the Obsidian vault at ~/…/lxw"; the panel pill's tooltip says what it is |
| 7 | "+ Add link" small, hidden, "link not page" (5) | Footer: **"+ Save a web page"** styled as a button |
| 8 | Inbox 5 vs "captures / sources" piles; eight nouns for one thing (6) | Engine: "{n} new files to sort into your library", "… to add to your library"; Ask placeholder "Ask your library anything…"; Notes window "Filter notes by title…" and "42 notes" — one noun, *library*; "captures" no longer collides with screen/audio capture |
| 9 | Unexplained blue dots on Recent rows (5) | Tooltip + label "New since you last looked" |
| 10 | Ask vs Search (5) | Notes placeholder "Filter notes by title…" |
| 11 | Overview repeats the doctor rows in Health and Next up (3) | Overview Next up = the engine's counted work only |
| 12 | Keep → where? Dismiss → delete? (4) | Button tooltips: "Saves it as a task on your to-do list" / "Keeps it in your library"; "Hides it — nothing is deleted" |
| 13 | "unsure" pill unexplained, low contrast (3) | Ink on the tint; tooltip "The app isn't sure this is a task/idea …" |
| 14 | Devin's located defects: Ask button shorter than its field; Overview first row not meeting at the bottom; "Update app" the loudest button; zigzag titles beside natural-width badges; crescent rail in Notes; Inbox "Notes" group violet | Ask button 36 px; `align-items: stretch`; Update app secondary; `TypeBadge` one column width; rail removed; group colour = the note type |

Not fixed (recorded for the operator — product calls, not copy): Jess's premise challenge
(Inbox as the panel's default face, timeline over dashboard, delete the Notes browser) and her
braver moves (menu-bar red dot, evidence per Inbox row, a typographic voice); Riley's
"system audio records the other people on my calls — they didn't get a vote"; cost / data
leaves the machine; the nav row drawn as tabs (Devin); the pre-ticked capture default.

## Re-test round 1 (same blind prompt, same three novice lenses, fresh captures after the fix round)

### Nova — 7/10 (was 6)

Q4 now correct: "the red dot and the word Recording on the menu screen. To stop it, the
Pause button right next to it, or the toggle in Settings … I'd find Pause in two seconds"
(worry: "Pause sounds temporary, I'd want an Off"). Count 42 "on like four screens,
impossible to miss"; Save a web page found; Overview/Charts easy; "the menu-bar screen I could
use right now without anyone explaining it, that's most of the points". Give-up point moved
to the welcome's pre-ticked capture toggle ("if my friend hadn't vouched for it I'd have
closed it there"). Still unsure: "AI sessions aren't being saved" (would leave Set up alone),
"sources", the Ollama / kcma-d8 hint line, "lxw" ("looks like a typo in the corner"), Inbox
vs Sort vs Add ("three doors that all sound like stuff to deal with"), the 3-issues ring vs
five Next up rows.

### Sam — 6/10 (was 6)

Q4 now correct: "the Pause button in the dropdown, or the Screen & audio capture switch in
Settings — I'd do the Settings switch because Pause sounds temporary". The everyday loop
("type a question, see the notes, keep or dismiss, pause recording — I'd manage that today").
Give-up point unchanged in kind: the Health row with no button — "The local AI helper
(Ollama) isn't reachable · check kcma-d8 is up" — "the app says 3 things are broken and I can
only fix two … I'd text my friend". Unsettled by the welcome's pre-ticked capture and by the
Overview's capture strip showing last evening and this morning "when I installed ten minutes
ago" (the fixture carries a day of history; the frame says first run). Still unsure: "AI
sessions" ("ChatGPT chats maybe?"), "Obsidian — another app I'm supposed to have?", files vs
sources, "document scans — did it scan my stuff on its own?", two different Refresh rows,
"lxw", note titles like "Engine MOC" / "Wikilink relativization" (fixture content), Keep →
where, Dismiss → delete or hide.

### Mateo — 6/10 (was 5)

Q4 now correct: "The card says Recording … and has a Pause button, I would press Pause. Or in
Settings I would switch off Screen & audio capture." The four Overview tiles "perfect, words
and numbers, no colour needed"; "Save a web page — I understood it at once"; Settings "short,
clear — Open in Obsidian told me what lxw is". Give-up points: "Set up" for "AI sessions"
("a chat with ChatGPT?") and the Ollama line ("kcma-d8 looks like a code; 'is up' I'm
guessing"). Colour still gives him nothing: the two severity dots look the same, and the
Overview's Health lists the checks in a different order than the panel's Next up, "so I don't
know which is the big one". Two Refresh buttons. Pale grey small text (times, paths, "from
email", chart labels, the "unsure" badge) "tires my eyes at night". "Dismiss — Ignore would be
plainer." "+4 today" read as new, not updated.

**Round 1 novice mean: (6 + 7 + 6) / 3 = 6.3** (was 5.7). Every persona now answers Q4
correctly — the located defect is closed. The gate (≥ 8) is not met.

## Round 2 — why a second round, what changed

Round 1 could not reach the gate with the two scores in (7, 6). Its remaining consensus is of
three kinds: (a) copy the builder cannot see from inside — "AI sessions", "sources", two
"Refresh" verbs, the Ollama hint "check kcma-d8 is up" with nothing to do, "lxw" with no
word beside it; (b) a test confound — the frame said "installed ten minutes ago" while the
fixture carries a day of capture history and three days of Inbox items, so three personas
read the data as "it recorded me before it said hello"; (c) product defaults the panel is not
allowed to overturn — the pre-ticked capture switch (M029's consented-capture decision).

Round 2 fixes (a): "AI chats aren't being saved" (+ stalled / retry / flush / Inbox source
"from an AI chat"), "{n} new items to add to your library", "{n} folder-scan requests to
review", index verb **Fix** (one Refresh left), the Ollama hint "start Ollama on kcma-d8 — or
turn local AI off with …", the panel pill reads "Library · lxw". It fixes (b) in the frame
only: "a small menu-bar app your friend installed on your Mac last week while helping you set
up your notes; today is the first time you open it yourself" — same files, same questions.
(c) stays and is reported to the operator. The task plan said one fix round; the milestone's
exit criterion (≥ 8/10) outranks that, so this second, smaller round is recorded as a
deviation in the task summary. The rest-height gate fired once on the way (a two-line title
pushed the panel to 651 px) and the title was shortened — the gate earns its keep.

## Re-test round 2 (frame corrected, fresh captures)

### Nova — 7/10 (round 1: 7)

"The popup is genuinely good, I'd use the Ask box and the Pause button on day one without
thinking … the popup earns a second look." Q4: "Red dot, the word Recording, Pause button
right there … the red dot did the work before I read anything." Fix on the red row — "red
dot plus button, you click the button". Most unsure: the Ollama hint, now carrying the
config command — "a terminal command sitting in the middle of a friendly app … made me think
the rest might turn into that too". New contradiction spotted: "AI chats aren't being saved"
in Next up vs two Inbox rows "from an AI chat" (fixture: a vault with saved chats AND the
hooks warning). "Folder-scan requests to review — review what?" The pre-ticked capture
toggle: "not confusion — I'd hit Pause first and text my friend later." Give-up points are
now hypotheticals ("if I hit Fix and nothing visible happens, if Ask takes ages").

### Sam — 6/10 (round 1: 6)

Everyday loop intact ("ask a question, look at the list, Keep/Dismiss the inbox, pause the
recording, save a web page"); Q4 both channels ("red dot plus the word Recording plus the
button"); counts "confident". Give-up point unchanged: the Health row "counted as one of my
3 red problems, has no button, and reads like code" (his captures still carried the config
command in the hint — removed since: the hint is now "start Ollama on kcma-d8" only). New
vocabulary snags: "folder-scan requests to review — who is requesting to scan my folders?"
(reads as something asking permission), "files to sort" vs "items to add" ("read it three
times"), the type NOTE with 1 of 42 notes ("broke my brain a little"), MAP; "AI chats aren't
being saved" vs Inbox rows "from an AI chat"; Inbox 5 vs "4 new items" (different piles,
same reading). The pre-ticked capture switch "made me uneasy before I'd done anything".

### Mateo — 6/10 (round 1: 6)

"The four everyday things — ask, look at notes, pause recording, save a page — are plain words
with a button, and I'd manage those today. The Inbox with Keep and Dismiss too." Overview
tiles "the easiest screen for me". Give-up point: the Ollama row ("no button … the thing in
the little quotes looks like a command for a terminal. Where would I type that?"). Most unsure
word: "Fix" ("I don't know what it will do to my notes"), then "Set up" for AI chats.
Colour-only meanings he cannot read: the severity dots, the Recent "new" dots (tooltip only),
the middle steps of the heat strip (legend labels only at the ends). "Library" vs "vault"
(the welcome's path line and an Inbox item). Files vs items, folder-scan requests. The
recording "already on before I touched anything, and I only knew that from reading the
sentence".

## Result

| | Sam | Nova | Mateo | novice mean | Priya | Riley | Devin | Jess |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Before fixes | 6 | 6 | 5 | **5.7** | 6 | 4 | 6 | 5 |
| Round 1 | 6 | 7 | 6 | **6.3** | – | – | – | – |
| Round 2 | 6 | 7 | 6 | **6.3** | – | – | – | – |

**Gate (≥ 8/10): not met.** M029 closed at 6/10; the app now sits at 6.3 on the same blind
method. What the two rounds did buy: the one quiz question every persona failed (how to stop
the recording) is answered correctly by every persona now; the trust failure ("the switch
disappeared after Get started") is gone; the number contradiction is gone; the vocabulary
collision between the two kinds of capture is gone.

**Why the number stays at 6 — the remaining blockers, in order of weight:**

1. **A Health row the GUI cannot act on** (Ollama unreachable, 3 of 3 novices' give-up point
   in round 2). The engine reports it as a warning; the GUI counts it among "3 issues" and can
   only show a hint. For a first-run reader a problem with no button is the moment they stop.
   Lever (operator decision): present non-dispatchable checks outside the issue count — a
   quiet "for whoever set this up" line — or make the local-AI check info-level on the
   desktop. Not done: it changes what the doctor's count means.
2. **The pre-ticked capture switch on the welcome** (named by all three in both rounds, "not
   confusion — annoyance"). M029's consented-capture decision; the panel reports it, does not
   overturn it.
3. **Engine vocabulary still one layer too deep for a novice**: "folder-scan requests to
   review" ("who is requesting?"), "files to sort" vs "items to add", "Fix" on a "note list"
   (what will it do to my notes?), "AI chats … Set up" (what will it ask of me?), the type
   named NOTE among notes, "vault" surfacing from the welcome's path line and Inbox content.
   Each is a copy pass on `actions.py` / `health.py` titles; diminishing returns per round.
4. **Static screenshots cannot show consequences**: what an answer looks like, what Fix
   does, what Save a web page asks next. Every persona named one of these as a hypothetical
   give-up. A click-through (dev build) panel or a short first-run tour would answer them;
   the blind-screenshot method cannot.
5. Colour-only meanings for a colour-weak reader (severity dots, heat-strip middle steps):
   position and words carry the meaning; the dots stay decoration for him.

Method notes: round 2's frame change removed the "it recorded me before it said hello"
confound; the fixture still pairs "AI chats aren't being saved" with Inbox rows "from an AI
chat" (plausible in a real vault, read as a contradiction here). The captures the round-2
personas saw still carried the config command in the Ollama hint; it was removed after their
reading and is not part of any measured score.
