# Project knowledge

Hard-won lessons and context that should survive across agent sessions — setup traps, tooling quirks, things that would have been good to know going in.

Keep scaffold/ARCH-LLM.md for confirmed product and system facts only. One home per fact; don't duplicate architecture content here.

## Never strip the Typer page background

The lesson area is **not** the system window chrome color. Default page is **`#1e1e1e`** (dark). `typer/background_color` (Preferences → Typer Options → “Page background (behind lesson)”) paints a solid fill on `TyperWindow` and `TyperCanvas` via `_applyBackground`. The lesson `QTextEdit` is intentionally transparent so text sits *on* that page fill. Never default this to `QPalette.Window` — that makes the page the same gray as the frame so it looks “gone.”

Agents keep deleting or covering this by accident (tab pane styles, document mode, “cleanup”). Rules:

- Do **not** remove `_applyBackground`, the `background_color` setting, or the solid fill on `TyperWindow` / `#TyperCanvas`.
- **`Qt.WA_StyledBackground` must stay True** on both widgets. Without it, Qt ignores `background-color` in their stylesheets after they are reparented into the main tab pane — the page looks like flat chrome gray even though the stylesheet string is still set.
- If you style `QTabWidget::pane` on the main tabs (e.g. to kill the full-width rule through the session clock), the pane background must be **`transparent`** so the typer page color shows through. Opaque pane = gray void over the user’s dark page.
- Do not make the lesson text edit itself the only place that holds the page color.
- Regression tests: `test_typer_page_background_fill_is_applied`, `test_typer_page_background_survives_main_tab_reparent`.
