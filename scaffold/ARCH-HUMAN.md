# Architecture (human-readable)

## What this app is

**Typing Program** is a desktop typing trainer (Python + PyQt5). You practice in a lesson canvas; the app saves per-character, per-trigram, and per-word speed/mistake stats in SQLite and builds weakspot lessons from the worst targets.

## Main screens

| Tab | Role |
|-----|------|
| Typer | Practice (improve / book / corpus). Footer toggles: read ahead, **Block ⌫**, heatmap. |
| Performance Analysis | Ranked keys/trigrams/words, progress card, drill / find in corpus. |
| Preferences | General, Typer Options, Sources (Gutenberg import). |

## Block ⌫

Footer toggle (default on). Plain Backspace does nothing; only Opt/Alt/Ctrl/Cmd+Backspace deletes (whole word). Pref key: `typer/word_delete_enabled`. Code: `typing_program/block_bkspc.py`.

## Where the code lives

- `typing_program/` — app package (typer, stats, license, updater, …)
- `tests/` — pytest
- `website/` — marketing site + Pages functions
- `scaffold/` — agent rules + architecture (this folder)

Full agent map: `scaffold/ARCH-LLM.md`. Deploy notes: `scaffold/archive/DEPLOY.md`.
