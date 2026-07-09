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
| **Typer** | Practice. Modes: **improve** (weak spots / focus drills), **book** (chapter through a novel), **corpus** (random imported text). Footer extras: read ahead, **Block ⌫**, heatmap. |
| **Performance Analysis** | Ranked characters / trigrams / words; progress card (WPM, practice time); drill or find a target in corpus. |
| **Preferences** | Font, sounds, thresholds; typer options; import books from Project Gutenberg. |

**Improve** builds readable practice from your worst items (not random letter soup). Submodes (normal / oblivion / slowest / hesitant / damage) pick different weak-word pools. Finishing a focus drill repeats it until you leave.

**Block ⌫** (on by default): plain Backspace does nothing; only Option/Ctrl/Alt/Cmd+Backspace deletes (whole word). Habit training for faster correction.

---

## Data the app cares about

- **Per keystroke** timing and mistakes while you type a lesson.
- **At lesson end:** characters, 3-character trigrams, and words are saved into SQLite (`statistic`), plus a lesson summary row (`result`) for normal practice (not pure focus drills).
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
