# Amphetype Architecture

## Stack

- Python 3.6+ (local dev: 3.11 — see `docs/DEPLOY.md`), PyQt5 GUI, SQLite (`statistic`, `text`, `source`, `result`) via `amphetype.Data.DB`.
- Typing stats: `type` 0 = character, 1 = trigram (3 chars, including spaces/punctuation), 2 = word (`amphetype/typer.py`).
- Main window tabs (`amphetype/Amphetype.py`): Typer, Sources, Performance Analysis, Preferences. Lesson Generator (off-tab, for `auto_review`), Database, About/Help, and the old Weakspot tab are not shown; weakspot runs from the Typer tab mode switch.

## Typing practice (Typer)

Two runtime-selectable implementations, controlled by `which_typer` (0 = legacy split view, 1 = primary inline; default 1). Both are wired to sources, lesson generator, Weakspot, performance history, and statistics via signals in `amphetype/Amphetype.py`.

### Primary (inline, default)

- `amphetype/typer.py`: `LessonDocument` (`QTextDocument` subclass), `TyperWidget` (`QTextEdit`), `TyperWindow`.
- Target text is rendered in the editable document with per-character styling (untyped, correct, error, blocking errors).
- Keystrokes mutate the document in place; timing and statistics via `RunStats` (`amphetype/timingtuple.py`).
- Supports overwrite/lenient modes, word-aware protected backspacing, progress, and full result recording.
- Footer: faint **normal** / **weakspot** mode toggles (persisted as `practice_mode`); **read ahead** toggle + level button (`read_ahead_enabled`, `typer/read_ahead_level`: normal / hard / easy — applies in either practice mode); novel attribution (`— Title`) in normal mode only.
- **Read ahead** (`amphetype/read_ahead.py`): off by default; when on, level cycles normal (hide current + next word) → hard (+ one more) → easy (current only). Before the lesson starts, full text is shown; the first keystroke applies hiding. Hidden letters use page `background_color` as foreground. Mistyping on a hidden word reveals that word only; other hidden words stay hidden. Compatible with speed heatmap: hidden words stay masked; visible untyped text still gets heatmap colors.
- Completing a lesson in **normal** mode advances via `TextManager.nextText`; in **weakspot** mode builds the next weakspot lesson (`WeakSpotLessonBuilder` in `amphetype/WeakSpot.py`).
- Page background uses `typer/background_color` (defaults to Qt window grey); lesson text defaults to light foreground on clear glyph backgrounds (errors still highlighted).
- **Speed heatmap** (off by default): footer **heatmap** click-toggle (white = on, grey = off); when on, one **words** / **trigrams** / **chars** label (click to cycle) plus single-line stoplight WPM legend appear to its right. Untyped text with stats gets bright stoplight foreground color from `statistic` (same history window and discounted-source omission as Performance Analysis Stats). Trigram mode paints non-overlapping 3-char blocks; contested spans use highest damage (`count·time²·(1+misses/count)`, same as Performance Analysis). Logic: `amphetype/speed_heatmap.py`.

### Legacy (split view)

- `amphetype/Quizzer.py`: `Typer` (`QTextEdit`) + `Quizzer` container with `WWLabel`.
- Lesson text above a separate plain input field. Retained during transition; scheduled for removal (see `docs/TODO.md`).

### Settings

- `which_typer`: 0 = legacy, 1 = inline.
- Typer options under `typer` and `colors` groups (`amphetype/Config.py`); many general options (font, `show_last`, `auto_review`, `min_*` thresholds, etc.) apply to both.
- Statistics collection, viscosity, and per-char/trigram/word aggregation are shared in concept but differ in implementation between the two typers (notably viscosity in the inline version).

## Performance Analysis tab

- Single tab (`amphetype/PerformanceAnalysis.py`) with sub-tabs **Stats** (aggregated keys/trigrams/words from `statistic` with impact/damage ranking) and **Progress** (session `result` history, source filter, grouping, WPM/accuracy/viscosity graph, double-click to retry a text). Both share the `history` days window (tab header + Preferences); session rows are also capped by `perf_items`, Stats rows by `ana_many` and `ana_count`.

## Lesson generation (baseline)

- **Lesson Generator** (`amphetype/Lesson.py`) is off-tab (used by `auto_review` only).
- Generator repeats/shuffles list entries and joins with spaces — trigram/key practice produces unreadable strings.
- Novel/text import (`LessonMiner`, `text` table) is separate from stats-based generation.

## Weakspot intelligent lessons

Auto-build practice text from ranked weak **characters**, **trigrams**, and **words** so the user types real words/phrases, not raw n-grams. Started from Typer tab **weakspot** mode (`amphetype/WeakSpot.py` builder + `WeakSpotLessons.py`).

### Rules

1. **No bare trigrams or characters** — every line is composed of normal words (letters; capitalization allowed for character practice).
2. **No symbol gibberish** — no random punctuation/symbol runs; lessons need not read like prose but must stay word-like.
3. **Trigram practice** embeds the exact 3-character trigram inside word pairs or phrases (e.g. `e h` → `above home`, `blue horizon`).
4. **Word practice** includes the weak word (e.g. `from` → `from blue horizon`, or combined with a weak trigram → `fly from`).
5. **Character practice** via real words (e.g. weak `C` + weak word `cloth` → `Cloth`).
6. **Multi-target lines** when one phrase covers several weak spots (only when corpus yields a natural match; otherwise combine what fits).
7. **Mix** weak words, trigrams, and characters; prefer stacking targets on the same line when compatible.
8. **Coverage = substring truth**: a target is practiced iff its exact surface appears in the rendered lesson — trigram/char as literal substring (case-sensitive, incl. spaces/punctuation), word as whitespace token (punctuation-stripped, case-insensitive). `covered_targets()` is the single source of truth for building and verifying.
9. **General trigram matching**: any 3-char window. Space pattern — no space → one token (in-word substring, letters+trailing punct like `ol,`/`o,"`, leading punct/hyphen like `-fe`/`"fe`, letter·punct·letter); space at middle → cross-word (left token ends `[0]`, right starts `[2]`, with quote/period surface forms); space at edge → token prefix/suffix with a productive neighbor (` Al`, `At `).
10. **Weak words first**: weak DB words are building blocks; dictionary only completes a boundary slot when no weak word fits. No random filler (see invariant below).
11. **Hyper-compression**: slot fillers also cover other outstanding targets when possible (e.g. `Cool,` covers char `C` + trigram `ol,`).
12. **Selection = importance ("damage")**: `score = time² · (count + misses)` (`time` = median sec/char). Total cost the item imposes: a moderately slow item typed often outranks a very slow item typed once. Slowness is quadratic; frequency is linear and decisive.
13. **Importance-weighted repetition**: each target repeated proportional to score (`allocate_repeats`, every target ≥1, capped); high-impact items get real practice, not a single token.
14. **Cross-lesson freshness**: fresh RNG per build (varied word realizations and order); weighted repetition differs run-to-run; widget passes a 2-lesson recency deque as `recent` keys (weights halved) so emphasis rotates.
15. **No filler invariant**: every emitted phrase covers at least one target (new or repeat); dictionary only completes trigram-boundary slots.
16. **Weakspot feedback loop guard**: `statistic.source` tags each stats row. Generated-lesson sources (`<Weakspot>`, Lesson Generator, Reviews) have `source.discount` set. Inline typer does not write stats in **weakspot** mode; other discounted lessons only write if `use_lesson_stats` is on. Rows from discounted sources are omitted from **Performance Analysis** Stats rankings and weakspot target selection (`STAT_OMIT_DISCOUNTED` in `amphetype/Data.py`).

### Implementation

- Composer: `amphetype/WeakSpotLessons.py` — weak stats drive content; bundled dict (`words-20.txt`) only completes trigram-boundary slots. Tests: `tests/test_weakspot_lessons.py`.
- Widget caches lesson until stats change or user clicks New lesson; preview + Start typing → Typer.
