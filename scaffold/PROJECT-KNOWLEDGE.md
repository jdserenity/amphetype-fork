# Project knowledge

Hard-won lessons and context that should survive across agent sessions — setup traps, tooling quirks, things that would have been good to know going in.

Keep scaffold/ARCH-LLM.md for confirmed product and system facts only. One home per fact; don't duplicate architecture content here.

## Never strip the Typer page background

The lesson area is **not** the system window chrome color. `typer/background_color` (Preferences → Typer Options → “Page background (behind lesson)”) paints a solid fill on `TyperWindow` and `TyperCanvas` via `_applyBackground`. The lesson `QTextEdit` is intentionally transparent so text sits *on* that page fill.

Agents keep deleting or covering this by accident (tab pane styles, document mode, “cleanup”). Rules:

- Do **not** remove `_applyBackground`, the `background_color` setting, or the solid fill on `TyperWindow` / `#TyperCanvas`.
- If you style `QTabWidget::pane` on the main tabs (e.g. to kill the full-width rule through the session clock), the pane background must be **`transparent`** so the typer page color shows through. Opaque pane = gray void over the user’s dark page.
- Do not make the lesson text edit itself the only place that holds the page color.
- Regression test: `tests/test_typer_document.py::test_typer_page_background_fill_is_applied`.
