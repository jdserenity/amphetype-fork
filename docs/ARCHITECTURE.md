# Amphetype Architecture

## Stack

- Python 3.6+ (local dev: 3.11 — see `docs/DEPLOY.md`), PyQt5 GUI, SQLite (`statistic`, `text`, `source`, `result`) via `amphetype.Data.DB`.
- Marketing site: static HTML/CSS/JS in `website/`, deployed to Cloudflare Pages (`wrangler.jsonc` → `pages_build_output_dir: ./website`). Checkout URL in `website/checkout.json`; buy buttons open Lemon Squeezy. Post-purchase redirect: `website/thanks.html?order_id=[order_id]` — content shown only after `website/functions/api/verify-order.js` confirms a paid order via Lemon Squeezy API (`LEMONSQUEEZY_API_KEY` secret).
- Sales: Lemon Squeezy ($5 one-time). LS generates license keys per sale. App activates via LS License API on first launch (`amphetype/license.py`); settings keys `license_key`, `license_instance_id`, `license_machine_id`. Offline grace: if a key was activated before and the network is down, launch is allowed.
- Typing stats: `type` 0 = character, 1 = trigram (3 chars, including spaces/punctuation), 2 = word (`amphetype/typer.py`).
- Main window tabs (`amphetype/Amphetype.py`): Typer, Performance Analysis, Preferences (sub-tabs: General Options, Typer Options, Sources). Last Preferences sub-tab index persists in SQLite (`app_meta.preferences_tab`). Lesson Generator (off-tab, for `auto_review`), Database, About/Help, and the old Weakspot tab are not shown; weakspot runs from the Typer tab mode switch.

## Typing practice (Typer)

- `amphetype/typer.py`: `LessonDocument` (`QTextDocument` subclass), `TyperWidget` (`QTextEdit`), `TyperWindow`. Wired to sources, lesson generator, Weakspot, performance history, and statistics via signals in `amphetype/Amphetype.py`.
- Target text is rendered in the editable document with per-character styling (untyped, correct, error, blocking errors).
- Keystrokes mutate the document in place; timing and statistics via `RunStats` (`amphetype/timingtuple.py`).
- **Pause (ESC)**: during an active lesson (including before the first keystroke), ESC pauses (does not cancel). WPM timing freezes while paused (`RunStats.pause` / `resume`; no timer until typing starts). The lesson canvas greys out with **Continue**, **New**, and **Restart** (stacked); ESC again or **Continue** resumes. **New** loads another exercise for the current mode (normal / book / weakspot). **Restart** resets the lesson to the beginning. No on-screen ESC hint.
- Supports overwrite/lenient modes, word-aware protected backspacing, progress, and full result recording.
- Footer: faint **normal** / **book** / **weakspot** mode toggles (persisted as `practice_mode`: 0 / 1 / 2); book mode shows chapter progress beside **book** (`Chapter N · done/total`); click **— Title** (bottom right) to switch books. **Read ahead** toggle + level button (`read_ahead_enabled`, `typer/read_ahead_level`: normal / hard / easy — applies in any practice mode); novel attribution (`— Title`) in normal and book modes.
- **Read ahead** (`amphetype/read_ahead.py`): off by default; when on, level cycles normal (hide current + next word) → hard (+ one more) → easy (current only). Before the lesson starts, full text is shown; the first keystroke applies hiding. Hidden letters use page `background_color` as foreground. Mistyping on a hidden word reveals that word only; other hidden words stay hidden. Compatible with speed heatmap: hidden words stay masked; visible untyped text still gets heatmap colors.
- Completing a lesson in **normal** mode advances via `TextManager.nextText`; in **book** mode advances to the next chapter (or chapter part when over `book_max_chars`) via `BookLessonBuilder` (`amphetype/book_mode.py`); in **weakspot** mode builds the next weakspot lesson (`WeakSpotLessonBuilder` in `amphetype/WeakSpot.py`).
- **Book mode** loads full book text from `data/texts/<source name>` when present (fuzzy match on ` - <filename>` if needed), else concatenates imported `text` rows in rowid order. Gutenberg wraps are reflowed (`reflow_paragraphs`); formatted chapters are cached in SQLite (`book_chapter_cache`). Each chapter is shown in full (grey inactive before/after); the active slice uses `min_chars`/`max_chars` from Preferences. At each chapter chunk load (and in normal mode at each text load), the active typing block is vertically centered when a scrollbar is needed. Single newlines (soft wraps) display as line breaks and auto-skip; paragraph breaks (`\n\n`) still use the ⏎ match character (must type Enter) but the glyph is drawn in the page background color so it is invisible (extra newline in the pair auto-skips). Progress per source in `book_progress` (`chapter_index`, `chunk_index`); completed chunks in `book_lesson_done`. Stats recorded per chunk like normal mode.
- Page background uses `typer/background_color` (defaults to Qt window grey); lesson text defaults to light foreground on clear glyph backgrounds (errors still highlighted).
- **Speed heatmap** (off by default): footer **heatmap** click-toggle (white = on, grey = off); when on, one **words** / **trigrams** / **chars** label (click to cycle) plus single-line WPM legend (`<30` purple oblivion, `30–59`, `60–89`, `90–119`, `120+`). Untyped text with stats gets foreground color from `statistic` (all-time query; same counted-row rules as Performance Analysis). Case-sensitive key lookup. Word stats include all lengths (no min length). Trigram mode paints non-overlapping 3-char blocks; contested spans use highest damage (`count·time²·(1+misses/count)`, same as Performance Analysis). Logic: `amphetype/speed_heatmap.py`.

### Settings

- Typer options under `typer` and `colors` groups (`amphetype/Config.py`); many general options (font, `show_last`, `auto_review`, `min_*` thresholds, etc.) apply to the typer.

## Performance Analysis tab

- Single tab (`amphetype/PerformanceAnalysis.py`) with sub-tabs **Stats** (aggregated keys/trigrams/words from `statistic` with impact/damage ranking) and **Progress** (session `result` history, source filter, grouping, WPM/accuracy/viscosity graph, double-click to retry a text). Header shows **Unique words typed** / **Unique trigrams typed** (`count_unique_typed` in `stats_query.py`, distinct `statistic.data` in the history window). Both share the `history` days window (tab header + Preferences); session rows are also capped by `perf_items`, Stats rows by `ana_many` and `ana_count`.

## Lesson generation (baseline)

- **Lesson Generator** (`amphetype/Lesson.py`) is off-tab (used by `auto_review` only).
- Generator repeats/shuffles list entries and joins with spaces — trigram/key practice produces unreadable strings.
- Novel/text import (`LessonMiner`, `text` table) is separate from stats-based generation.
- **Project Gutenberg US/AUS** (Preferences → Sources): search merged US (`pg_catalog.csv`) + Australia (`GUTINDEX.AUS`) catalogs (stale after 7 days); duplicate titles prefer US. US import uses `pg{id}.txt`; AUS uses PGA URLs (`.txt` or `.html` → text). Boilerplate stripped (`amphetype/gutenberg/strip_headers.py`), saved under `data/texts/`, then `LessonMiner`. Cache: `gutenberg/` under local `data/` or `QStandardPaths` AppLocalData.

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
16. **Weakspot drill stats** (`amphetype/stats_query.py`): weakspot runs write `statistic` rows tagged `<Weakspot>` with `count=0` (one row per type target touched per session). They update median time/hesitation for that target but not `sum(count)`, `sum(mistakes)` used for damage/accuracy. Performance Analysis **Stats** **Drilled** column counts weakspot sessions per target. Lesson Generator / Reviews remain discounted with no writes unless `use_lesson_stats` is on. Heatmap WPM uses the same median-time pool as Analysis (`SPEED_STATS_SQL`); heatmap damage still uses counted rows only.

### Focus drill (Performance Analysis → Typer)

- **Stats** sub-tab: right-click **Drill** / **Find in corpus**; **Drill worst 3** (top damage); **Drill 3 oblivion** (random three with WPM `<30` for current keys/trigrams/words). **Find in corpus** (`amphetype/corpus_find.py`, `amphetype/text_index.py`): random matching chunk from imported novels via SQLite FTS5 (`text_fts`, indexed on novel import). Existing DBs: run `python scripts/backfill_corpus_index.py` once manually. Word lookup uses FTS then case-sensitive verify; trigrams/chars scan chunks. On success switches Typer to **normal** mode; on failure stays on Stats with an inline message (cleared on list refresh, sub-tab change, or leaving Performance Analysis). **Drill** switches to weakspot with a half-length lesson built only from those targets (`build_focus_lesson` in `WeakSpotLessons.py`); focus lessons emit each target word with the exact `data` string from Analysis (no re-capitalization). Finishing replays the same drill; click **weakspot** in the footer or leave weakspot and return to resume mixed weakspot lessons. Focus drills write no stats (no `result` or `statistic` rows). Word heatmap colors use case-sensitive stat keys; focus-drill targets also use the Analysis WPM captured at drill start.

### Implementation

- Composer: `amphetype/WeakSpotLessons.py` — weak stats drive content; bundled dict (`words-20.txt`) only completes trigram-boundary slots. Tests: `tests/test_weakspot_lessons.py`.
- Widget caches lesson until stats change or user clicks New lesson; preview + Start typing → Typer.
