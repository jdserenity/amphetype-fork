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
8. **Coverage = substring truth**: a target is practiced iff its exact surface appears in the rendered lesson — trigram/char as a literal substring (case-sensitive, incl. spaces/punctuation), word as a whitespace token (punctuation-stripped, case-insensitive). `covered_targets()` is the single source of truth for both building and verifying.
9. **General trigram matching**: a trigram is any 3-char window. Handled by space pattern — no space → one token (in-word substring, or letters+trailing punct like `ol,`/`o,"`, or leading punct/hyphen like `-fe`/`"fe`, or letter·punct·letter); space at middle → cross-word (left token ends `[0]`, right starts `[2]`, with quote/period surface forms); space at edge → token prefix/suffix with a productive neighbor (` Al`, `At `).
10. **Weak words first**: weak DB words are the building blocks; the dictionary only completes a boundary slot when no weak word fits. No random filler (see invariant below).
11. **Hyper-compression**: within any single phrase, slot fillers are chosen to also cover other outstanding targets, so one word/biword can satisfy several weak items at once (e.g. `Cool,` covers char `C` + trigram `ol,`).
12. **Selection = importance ("damage")**: `score = time² · (count + misses)` (`time` = median sec/char). This is the total cost the item imposes: a moderately-slow item typed constantly outranks a very-slow item typed once. Slowness still matters (quadratic), but frequency is linear and decisive.
13. **Importance-weighted repetition**: a lesson is not one-pass coverage. Each target is repeated proportional to its score (`allocate_repeats`, every target ≥1, capped so no item swamps), so high-impact error spaces get real practice, not a single token. Repetition of a weak target is practice, not filler.
14. **Cross-lesson freshness**: consecutive lessons over the same static error space must not feel identical. Achieved by (a) a fresh RNG per build → varied word realizations (`e h` → `above home` one time, `blue horizon` the next) and varied ordering; (b) weighted repetition that differs run-to-run; (c) `recent` keys passed from the widget (a session deque of recently-emphasized targets) whose weights are halved so emphasis rotates across the top of the error space.
15. **No filler invariant**: every emitted phrase covers at least one target (new or a repeat). A phrase that practises nothing is never emitted; the dictionary only completes trigram-boundary slots.
16. **Weakspot tab** (`amphetype/WeakSpot.py`): auto-generates a lesson on tab open from latest DB stats; preview + Start typing → Typer. Reuses cached lesson until stats change or user clicks New lesson. The widget keeps a 2-lesson recency deque and feeds it to the worker for cross-lesson rotation. Lesson Generator tab kept for dev; hide later (see `docs/TODO.md`).
17. **Weakspot feedback loop guard**: `statistic.source` tags each stats row with its text source. Weakspot selection excludes rows whose source has `discount` set (generated-lesson sources, including `<Weakspot>`). New Weakspot sessions do not write stats by default (same rule as old Lesson Generator); optional `use_lesson_stats` setting still allows saving them, but they remain excluded from Weakspot target selection.

### Implementation

- Composer: `amphetype/WeakSpotLessons.py` — weak stats drive content; bundled dict (`words-20.txt`) only completes trigram-boundary slots, never random padding. Tests: `tests/test_weakspot_lessons.py`.
- UI: **Weakspot** tab; caches lesson until stats change or New lesson.
