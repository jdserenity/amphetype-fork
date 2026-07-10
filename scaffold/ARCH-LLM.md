# Typing Program — agent architecture

Confirmed facts only. Package root: `typing_program/`. Version file: `typing_program/VERSION`.

## Product

Desktop typing trainer: lesson canvas, SQLite stats, weakspot lessons, book/corpus practice. Window title: **Typing Program That Helps You Type Better**. Tabs: Typer, Performance Analysis, Preferences (General / Typer Options / Sources). Off-tab but present: Lesson Generator (`Lesson.py`, `auto_review` only).

## Stack

| Layer | Choice |
|-------|--------|
| App | Python 3.11 (PyQt5 unreliable on 3.12+), PyQt5 |
| DB | SQLite via `Data.DB` — tables include `statistic`, `text`, `source`, `result`, book progress/cache, FTS `text_fts` |
| Settings | `Config.AppSettings` + `typer` / color groups (`settings.py` FSettings) |
| Site | Static `website/`, Cloudflare Pages (`wrangler.jsonc` → `pages_build_output_dir: ./website`) |
| Sales | Lemon Squeezy $5 one-time; LS license keys |
| Package | PyInstaller `typing_program.spec`, entry `main_entry.py`; bundles `VERSION`, `data/`, certifi CA |
| HTTPS | `https.py` + certifi (frozen builds) |

## Data locations

- **Default DB:** OS app-data / Typing Program / `typing-program.db` (`db_paths.py`, `legacy_data.py`).
- **Dev local DB:** `--local` / `TYPING_PROGRAM_LOCAL=1` → `typing_program/data/typing-program.db`.
- **Legacy:** one-time copy from Amphetype app-data if new DB empty.
- Prefs may override `db_name`.

## Repo layout

```
typing_program/   # app
tests/            # pytest
website/          # marketing + Pages Functions
  functions/api/  # verify-order, check-update, download-update
scripts/          # build-*, publish-update, reset_db, …
data/             # wordlists, sounds, texts (also shipped in bundle)
scaffold/         # agent docs (this file)
```

## Entry / wiring

- Dev: `./run-dev.sh` or `typing-program --skip-license` after `pip install -e .`
- Skip license: `--skip-license` / `TYPING_PROGRAM_SKIP_LICENSE=1`
- Main window: `mainwindow.py` / `main.py` — wires Typer, Performance Analysis, Preferences, session timer
- Typer core: `typer.py` — `LessonDocument`, `TyperWidget`, `TyperWindow`
- Timing/stats collect: `timingtuple.py` (`RunStats`, `collect_run_stat_rows`, `collect_focus_drill_stat_rows`)
- Analysis queries: `stats_query.py`
- Settings defaults: `Config.py`

## Practice modes (`practice_mode` 0/1/2)

| Mode | Value | Advance / content |
|------|-------|-------------------|
| improve | 0 (default) | Weakspot lesson (`WeakSpot.py` + `WeakSpotLessons.py`); submode via `typer/improve_submode` |
| book | 1 | `book_mode.py` — chapters/chunks, progress in `book_progress` / `book_lesson_done`. **Every finished chunk** calls `BookLessonBuilder.on_chunk_completed` (marks done + advances `book_progress` to next chunk/chapter) — not only chapter ends. Mid-chapter advances used to skip the save and reopened the same place. |
| corpus | 2 | `TextManager.nextText`; re-click corpus → another text |

Improve submodes: normal | trigrams | oblivion | slowest | hesitant | damage (`improve_mode.py`). **trigrams** (index 1): raw weak-trigram soup via `fetch_weak_trigram_targets` + `build_trigram_gibberish_lesson` — no dictionary words, not a focus drill. Other non-normal = focus drills on **words**: take worst `FOCUS_DRILL_POOL_SIZE` (20) in category, random-sample `FOCUS_DRILL_PICK_COUNT` (5) — or fewer if the user has not typed that many eligible words yet; single-word pool ⇒ that word only. All word picks gated by `analysis_min_count`. **Oblivion** = display WPM (1 decimal, same as PA) **&lt; 32** (`OBLIVION_WPM`; 32 is red, ≤31.9 purple); omitted from the submode cycle when its pool is empty (`oblivion_submode_available` / `next_improve_submode`). Auto focus drills **re-sample targets every finish/new** (`_load_improve_lesson`); PA-started drills keep the chosen targets and only re-shuffle the lesson. Focus text: `build_focus_lesson` uses equal-weight `allocate_repeats` + plain `rng.shuffle` (adjacent repeats allowed — true random order). Focus size prefs: `focus_min_chars` / `focus_max_chars` (default 80–300). **trigrams** lesson join collapses consecutive spaces so leading/trailing spaces inside trigrams never produce `  ` runs.

**Cold start:** every app launch forces practice mode improve + submode normal (`apply_cold_start_practice_mode` in `book_mode.py`, called from `TyperWindow` init). Last session’s book/corpus/submode is not restored.

**Idle mouse cursor:** on the typer canvas (`TyperWidget` + `idle_cursor.py`), the pointer blanks after `MOUSE_CURSOR_IDLE_MS` (2000) with no movement; reappears on move/enter. Mouse moves are watched via a **viewport** event filter (QTextEdit delivers moves there, not to `mouseMoveEvent` on the widget). Hide is skipped if the pointer has already left the canvas (`should_apply_idle_blank`). Footer mode strip (`_footer_controls`) uses `setCursor(PointingHandCursor)` so gaps between modes keep the hand — never stylesheet `cursor:` (unsupported: no effect + `Unknown property cursor` spam).

Empty lessons: `lesson_placeholders.py` (non-typable canvas messages).

## Keyboard navigation

| Shortcut | Action | Where |
|----------|--------|--------|
| **Tab** | Next improve submode (`cycle_improve_submode`; no-op outside improve) | Typer canvas (`TyperWidget.keyPressEvent` → `_on_tab_nav`) |
| **Cmd/Ctrl+Opt/Alt+← / →** | Previous / next practice mode (improve · corpus · book) | `TyperWindow` QShortcut (`Ctrl+Alt+Left/Right`); helpers in `keyboard_nav.py` |
| **Cmd+Shift+[ / Cmd+Shift+]** | Previous / next main toolbar tab (Typer / Performance Analysis / Preferences) | `MainWindow` QShortcut |

`QKeySequence` uses `Ctrl` for Command on macOS. Pure helpers: `cycle_practice_mode`, `cycle_index`.

## Typer behavior

- **Backgrounds (two layers):** `TyperWindow` chrome `#4a4a4a` (`TYPER_CHROME_COLOR`); `#TyperCanvas` = `typer/background_color` (default `#383838`) — same rect as ESC pause overlay, darker than chrome, not near-black. Do not paint page color on the whole window. Lesson `QTextEdit` transparent on canvas. `_applyBackground` + `WA_StyledBackground`. Main tab `::pane` transparent.
- Document: type on top of target; styles untyped/correct/error/blocked.
- ESC pause: Continue / New / Restart overlay; `RunStats.pause`/`resume`.
- Footer order (left): improve [+submode] · corpus · book · read ahead [+level] · **Block ⌫** · heatmap [+kind + legend] · **follow** [+WPM] · source title.
- **Read ahead** (`read_ahead.py`): off default; levels normal/hard/easy; hide upcoming words after first keystroke; mistype reveals current word only. Prefs: `read_ahead_enabled`, `typer/read_ahead_level`.
- **Block ⌫** (`block_bkspc.py`): on default. Pref: `typer/word_delete_enabled`. Plain Backspace no-op; Opt/Alt/Ctrl/Meta+Backspace = by-word. `allows_backspace(enabled, by_word)`.
- **Heatmap** (`speed_heatmap.py`): off default; modes words/trigrams/chars; all-time stats; prefs `typer/speed_heatmap`, `typer/speed_heatmap_mode`.
- **Follow** (`follow_mode.py`): off default; **corpus/book only** (not improve). Footer toggle after heatmap; when on, minimal WPM stepper beside it (arrows ±1 or type; live, no Enter; Enter/Esc unfocus). Prefs: `typer/follow_mode`, `typer/follow_wpm` (default 70, persists). Preference stays on across mode switches; in improve the control is greyed/disabled immediately; returning to corpus/book restores active follow if it was on; if never on, eligible modes do not auto-enable. Race: a second caret advances through the lesson at the set WPM (5 chars = 1 word); starts with the run (first keystroke); pauses with ESC. Finish before the caret → “You beat the cursor!” (cyan). Caret first → “The cursor beat you… 👎” (heatmap red). Either way: normal progress stats; **book place still advances** on failure.
- **Typer keyboard focus** (`typer_focus.py`): while the Typer tab is visible, focus stays on the lesson canvas — footer/chrome clicks cannot “click out” of typing. Sole exception: the follow WPM `QLineEdit`. `QApplication.focusChanged` → `should_refocus_typer` → deferred `_ensure_typer_focus`.
- Sounds: `typing_sounds.py`; prefs `typer/typing_sound`, `typing_error_sound`, `typing_sound_volume`.
- Word progress: `word_progress.py` — green + badges when median improves; orange = **new common words** that cross the PA min-count pool this run (`analysis_min_count` / `WORD_ANALYSIS_MIN_COUNT`). Message: “You found N new common word(s)!”. **Improve modes (all submodes including normal) never show this** and never gather counted word samples (`count=0` on discounted `<Weakspot>`).
- Footer source title (`_source_lbl`): always reserves **two lines** of height (even when empty in improve) via `QSizePolicy.Minimum` + `minimumHeight`, so the lesson canvas height matches book/corpus with typical wrapping titles.
- Book: full chapter grey inactive; active chunk sized by min/max chars; soft newlines auto-skip; para ⏎ match invisible; vertical center when scroll needed.
- `limit_backspace` (typer pref): separate — won’t back over correct text when set.

## Stats model

- `statistic.type`: 0 char, 1 trigram (any 3-char window), 2 word.
- End of lesson: `collect_run_stat_rows` — each completed **occurrence** is one sample; same spelling in one lesson → one row with `count` = samples (e.g. two “the” → count 2).
- `RunStats.pop_char` on backspace: moves index; does **not** clear mistakes/first timings → retype of same slot still one sample, mistakes accumulate.
- Idle: `IDLE_THRESHOLD = 3.0` s in `timingtuple.py` — gaps capped for WPM/`active_duration`.
- Focus/weakspot drills: `<Weakspot>` rows, `count=0` — affect medians/hesitation, not counted damage totals the same way (`stats_query.py`).
- Counted practice writes `result` with `char_count`/`duration` (corpus, book, improve-normal). Focus drills skip counted `result`/counts.
- Analysis: all-time (`ALL_TIME_HIST = 0`); words need ≥ `WORD_ANALYSIS_MIN_COUNT` (2) via `analysis_min_count` — **holy floor for all word pulls** (Performance Analysis, focus drills oblivion/slowest/hesitant/damage, weakspot `fetch_weak_targets`, Lesson Generator “from typed”). Chars/trigrams may use a lower configured min. WPM card gated on `WPM_GATE_MIN_LESSONS` (10) qualifying results.
- Damage/importance: time² · frequency-style factors (see weakspot / heatmap). Heatmap WPM uses median-time pool (`SPEED_STATS_SQL`).

## Weakspot rules (composer)

`WeakSpotLessons.py` + builder `WeakSpot.py`. Targets: weak chars/trigrams/words → real words only (no bare n-grams, no symbol gibberish). Coverage = substring/token truth via `covered_targets()`. Damage score drives selection + weighted repeats. Dict `data/wordlists/words-20.txt` only fills trigram boundary slots. Tests: `tests/test_weakspot_lessons.py`.

## Performance Analysis

`PerformanceAnalysis.py` + `progress_card.py`. Columns: speed, hesitation, count, perfect (count−mistakes), drilled, impact; words: Improved. Sort includes lowest perfect %, most improved. Actions: drill, find in corpus (`corpus_find.py` + FTS5 `text_index.py`), delete stats. Progress: WPM since start, avg WPM / adult percentile (`wpm_percentile.py`), unique common words, total practice time.

## Session timer

`session_timer.py`: top-right; ticks when focused + interaction within 60s. Session clock keeps elapsed time across focus loss (pause + flush must not reset display). Persist `app_meta.total_practice_seconds`. Pref `show_session_timer` default on. Main tabs: `documentMode` + `::pane { border: none; background: transparent }`; session clock vertically centered on tab labels.

## License

`license.py` + `LicenseDialog.py`: LS public License API activate/validate. Settings: `license_key`, `license_instance_id`, `license_machine_id`. Offline grace if previously activated. Checkout URL: `website/checkout.json` / optional `TYPING_PROGRAM_CHECKOUT_URL`.

## Website / commerce

- Buy buttons → Lemon Squeezy; `website/main.js` + `checkout.json`.
- Post-purchase: `thanks.html?order_id=[order_id]` → `functions/api/verify-order.js` (secret `LEMONSQUEEZY_API_KEY`).
- Local site: `cd website && npm install && npm run dev` (wrangler ~8788).
- Deploy: `npx wrangler pages deploy . --project-name=typing-program` from `website/`, or Git connect root `website`.

## Packaging

Build **on target OS** (no cross-compile).

| OS | Script | Artifacts |
|----|--------|-----------|
| macOS | `scripts/build-mac-dmg.sh` | `.app`, `.dmg` (LS), `Typing Program-mac.zip` via `mac_app_zip.py` (updater) |
| Windows | `scripts/build-windows.ps1` | `Typing Program-win.zip` |
| Linux | `scripts/build-linux.sh` | `Typing Program-linux.tar.gz` |

GHA: `.github/workflows/build-{mac,windows,linux}.yml` — **workflow_dispatch only**. v1 unsigned (Gatekeeper/SmartScreen warnings). Extra build deps: pyinstaller, pillow.

Smoke frozen Mac:  
`TYPING_PROGRAM_SKIP_LICENSE=1 TYPING_PROGRAM_LOGFILE=- dist/Typing\ Program.app/Contents/MacOS/Typing\ Program`

## In-app updates

Frozen only. UI: Preferences → Check for updates… (`updater.py`, `UpdateDialog.py`).

- `POST /api/check-update` — license_key, instance_id, platform, current_version → optional signed download.
- `GET /api/download-update?token=…` — R2 stream after HMAC.
- R2 bucket `typing-program-updates` (binding `UPDATES` in wrangler). Secrets: `UPDATE_SIGNING_SECRET`, `LEMONSQUEEZY_API_KEY`.
- Publish: `./scripts/publish-update.sh <ver> <darwin|win32|linux> <path>`; bump `VERSION` first. Manifest example: `updates/manifest.example.json`.
- Override: `TYPING_PROGRAM_UPDATE_API` (default `https://typing-program.pages.dev/api/check-update`).

## Dev install

```sh
./run-dev.sh
# or: uv venv venv --python 3.11 && source venv/bin/activate
#     uv pip install -r requirements.txt && uv pip install -e .
typing-program --skip-license
```

Tests: `python -m pytest tests/ -q` (pytest-qt for GUI).

## Key modules (index)

| Concern | Module(s) |
|---------|-----------|
| Typer UI/doc | `typer.py` |
| Block ⌫ | `block_bkspc.py` |
| Read ahead | `read_ahead.py` |
| Heatmap | `speed_heatmap.py` |
| Follow | `follow_mode.py` |
| Book | `book_mode.py` |
| Keyboard nav | `keyboard_nav.py` |
| Weakspot | `WeakSpot.py`, `WeakSpotLessons.py`, `improve_mode.py` |
| Stats I/O | `timingtuple.py`, `stats_query.py`, `Data.py` |
| Analysis UI | `PerformanceAnalysis.py`, `progress_card.py` |
| Corpus find | `corpus_find.py`, `text_index.py` |
| Gutenberg | `gutenberg/`, Sources tab |
| License/update | `license.py`, `updater.py` |
| Paths/legacy | `db_paths.py`, `legacy_data.py` |
