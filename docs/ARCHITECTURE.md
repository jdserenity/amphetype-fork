# Amphetype fork — architecture

## Stack

- Python 3.6+, PyQt5 GUI, SQLite (`statistic`, `text`, `source`, `result` tables) via `amphetype.Data.DB`.
- Typing stats: `type` 0 = character, 1 = trigram (3 chars, including spaces/punctuation), 2 = word (`amphetype/typer.py`).

## Current lesson generator (baseline)

- Analysis tab ranks slow keys/trigrams/words; user sends the list to **Lesson Generator** (`amphetype/Lesson.py`).
- Generator repeats/shuffles list entries and joins with spaces — trigram/key practice produces unreadable strings.
- Novel/text import (`LessonMiner`, `text` table) is separate from stats-based generation.

## Weak-spot intelligent lessons (product decision)

Auto-build practice text from ranked weak **characters**, **trigrams**, and **words** so the user types real words/phrases, not raw n-grams.

### Rules

1. **No bare trigrams or characters** in lesson output — every line is composed of normal words (letters; capitalization allowed for character practice).
2. **No symbol gibberish** — do not emit random punctuation/symbol runs; lessons need not read like prose but must stay word-like.
3. **Trigram practice** embeds the exact 3-character trigram inside word pairs or phrases (e.g. trigram `e h` → `above home`, `blue horizon` …).
4. **Word practice** includes the weak word (e.g. `from` → `from blue horizon` or combined with a weak trigram → `fly from`).
5. **Character practice** via real words (e.g. weak `C` + weak word `cloth` → `Cloth`).
6. **Multi-target lines** when one phrase can cover several weak spots (e.g. weak trigram `" c"` + weak word + weak char — only when corpus yields a natural word match; otherwise combine what fits).
7. **Mix** weak words, trigrams, and characters across a lesson set; prefer stacking targets on the same line when compatible.
8. **Fill dictionary** only: bundled `data/wordlists/words-20.txt` (~11k words) for padding and fallback when weak DB words cannot satisfy a target.
9. **Weak words first**: when a trigram, character, or in-word match can be satisfied by a weak word from stats, prefer it over a dictionary word (e.g. trigram `com` → `become` before `community`).
10. **Punctuation trigrams** (e.g. `" e`, `. y`): cross-word rule — decorate weak/dict words with trailing `"`, `.`, etc. on the left token and match the right token’s start letter (e.g. `"Grape" ever`, `tripod. your`).
11. **Weakspot tab** (`amphetype/WeakSpot.py`): auto-generates a lesson on tab open from latest DB stats; preview + Start typing → Typer. Reuses cached lesson until stats change or user clicks New lesson. Lesson Generator tab kept for dev; hide later (see `docs/TODO.md`).

### Implementation

- Composer: `amphetype/WeakSpotLessons.py` — weak stats drive content; bundled dict (`words-20.txt`) only for token lookup when weak words cannot complete a trigram boundary, **not** random lesson padding.
- UI: **Weakspot** tab; caches lesson until stats change or New lesson.
