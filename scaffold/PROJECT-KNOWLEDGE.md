# Project knowledge

Hard-won lessons and context that should survive across agent sessions — setup traps, tooling quirks, things that would have been good to know going in.

Keep scaffold/ARCH-LLM.md for confirmed product and system facts only. One home per fact; don't duplicate architecture content here.

## Book progress must save on every finished chunk

`typingDone` used to call `BookLessonBuilder.on_chunk_completed` only when `has_next_book_chunk()` was false (last chunk of a chapter). Mid-chapter finishes only advanced in-memory (`book_chunk` pending action), so quitting/reopening always restarted the same chapter chunk. Save place in SQLite on **every** completed chunk, then decide whether the next action is mid-chapter advance or chapter load.

## Never strip the two-layer Typer background

The Typer view has **two** background layers. Painting one color on both (or only on the outer widget) is the classic way agents “delete” the look.

1. **Outer chrome (`TyperWindow`)** — `#4a4a4a` (`TYPER_CHROME_COLOR`). Footer row, margins around the lesson. Lighter than the canvas.
2. **Lesson canvas (`#TyperCanvas`)** — `typer/background_color` (default `#383838`). Same size as the ESC pause overlay. Darker than chrome, lighter than pause dim — **not** near-black (`#1e1e1e` was too dark). Preferences → Typer Options → “Page background (behind lesson)” edits this layer only.
3. **Pause overlay** — semi-transparent black on top of the canvas only.

The lesson `QTextEdit` is transparent on the canvas.

Rules:

- Do **not** apply `background_color` to `TyperWindow`. Canvas only.
- Do **not** make canvas transparent “over” a painted window — the visible dark page *is* the canvas fill.
- **`Qt.WA_StyledBackground` must stay True** on the canvas (and chrome widget if styled). Without it, Qt ignores stylesheet fills after tab reparent.
- Main tab `QTabWidget::pane` must stay **`background: transparent`** so the layers show through.
- Regression tests: `test_typer_canvas_page_differs_from_window_chrome`, `test_typer_page_background_survives_main_tab_reparent`.
