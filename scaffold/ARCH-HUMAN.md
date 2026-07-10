# Typing Program — architecture (human)

Desktop typing trainer. You practice on a lesson canvas; the app records speed and mistakes, shows where you struggle, and builds practice from those weak spots.

**Stack:** Python 3.11 + PyQt5, SQLite on disk, static marketing site on Cloudflare Pages, sales via Lemon Squeezy ($5 one-time license).

---

## Big picture

```
┌─────────────────────────────────────────────────────────────┐
│  Desktop app (PyInstaller build, or ./run-dev.sh)            │
│  ┌──────────┐  ┌────────────────────┐  ┌─────────────────┐  │
│  │  Typer   │  │ Performance        │  │ Preferences     │  │
│  │ practice │  │ Analysis           │  │ General / Typer │  │
│  │          │  │ ranked targets +   │  │ / Sources       │  │
│  │          │  │ progress card      │  │                 │  │
│  └────┬─────┘  └─────────┬──────────┘  └────────┬────────┘  │
│       │                  │                      │           │
│       └──────────────────┴──────────────────────┘           │
│                          │                                  │
│                    SQLite DB                                │
│         (stats, texts, results, progress)                   │
└─────────────────────────────────────────────────────────────┘
                          │
     license activate / check-update (HTTPS)
                          │
┌─────────────────────────▼───────────────────────────────────┐
│  website/ on Cloudflare Pages                               │
│  buy → Lemon Squeezy → thanks.html (order check)            │
│  updates: R2 + /api/check-update                            │
└─────────────────────────────────────────────────────────────┘
```

---

## What you do in the app

| Tab | Purpose |
|-----|---------|
| **Typer** | Practice. Modes: **improve** (weak spots / focus drills), **corpus** (random imported text), **book** (chapter through a novel). Footer extras: read ahead, **Block ⌫**, heatmap. |
| **Performance Analysis** | Ranked characters / trigrams / words / biword pairs; progress card (perfect rate, practice time); columns include corpus / drill / perfect; drill or find a target in corpus. |
| **Preferences** | Font, sounds, thresholds; typer options; import books from Project Gutenberg. |

**Improve** builds practice from your worst items. Submodes: **normal** (readable weakspot mix), **trigrams** (raw 3-character chunks only — looks like alien gibberish), then **oblivion / slowest / hesitant / accuracy / damage** (focus drills). Each focus drill pulls from your 20 worst words in that category and randomly picks 5 (or fewer if you have not typed 20 yet). **Accuracy** drills the words you mistype most often (lowest perfect %). **Oblivion** only appears in the cycle when you actually have words that slow — under the oblivion speed line. Words only count after you’ve typed them enough times to show up in Performance Analysis (default: at least twice). Finishing an auto focus drill loads a **new** random set; drills started from Performance Analysis keep your chosen targets. Focus-drill length is set in Preferences → General (under the normal lesson size fields).

**Cold start:** opening the app always lands on Typer in **improve · normal**, not whatever mode you left last time.

**Keyboard (macOS):** **Tab** cycles improve submode (when you’re in improve). **⌘⌥← / ⌘⌥→** cycle practice mode (improve · corpus · book). **⌥⌘[ / ⌥⌘]** cycle the top tabs (Typer / Performance Analysis / Preferences).

**Book place:** finishing a chunk always saves where you are (chapter + chunk). Reopening the book mode resumes from that place — not only after you finish a whole chapter.

**Mouse pointer:** on the practice canvas it hides after about two seconds still, then comes back when you move the mouse.

**Block ⌫** (on by default): plain Backspace does nothing; only Option/Ctrl/Alt/Cmd+Backspace deletes (whole word). Habit training for faster correction.

---

## Data the app cares about

- **Per keystroke** timing and mistakes while you type a lesson.
- **At lesson end:** characters, 3-character trigrams, words, and biword pairs (two words typed next to each other) are saved into SQLite (`statistic`), plus a lesson summary row (`result`) for normal practice (not pure focus drills).
- **Weakspot/focus drills** update timing medians but do not inflate “how many times you typed this for real” counts the same way counted practice does.
- **Database location:** OS app-data folder for “Typing Program” by default; local dev can use a DB under the package. Old Amphetype DBs can be copied once on first launch.

---

## Money and updates (short)

1. Buyer pays on Lemon Squeezy → gets a license key.
2. App activates the key (and works offline for a while if already activated).
3. Installers are built per OS with PyInstaller (must build on that OS).
4. First download is usually via Lemon Squeezy product files; later updates can use **Check for updates…** (license-gated download from Cloudflare R2).

---

## Repo map (coarse)

| Path | What |
|------|------|
| `typing_program/` | Desktop app |
| `tests/` | pytest |
| `website/` | Landing page + Pages Functions (checkout verify, updates) |
| `scripts/` | Build installers, publish updates, utilities |
| `scaffold/` | Agent rules + this architecture |
| `data/` | Bundled word lists, sounds, sample texts |

Agent-level detail (files, settings keys, exact behaviors): **`scaffold/ARCH-LLM.md`**.
