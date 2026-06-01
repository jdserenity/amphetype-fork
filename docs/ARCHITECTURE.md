# Amphetype Architecture

## Typer (typing practice) implementations

The application provides two runtime-selectable implementations for the core typing practice surface, controlled by the `which_typer` setting (0 or 1).

- **Primary (default)**: Inline typing directly on the lesson text.
  - Implemented in `amphetype/typer.py` as `LessonDocument` (subclass of `QTextDocument`), `TyperWidget` (`QTextEdit`), and `TyperWindow`.
  - The target text is rendered inside the editable document with per-character styling (untyped, correct, error states, blocking errors).
  - User keystrokes mutate the document in place. Timing and statistics are collected via `RunStats` (see `amphetype/timingtuple.py`).
  - Supports overwrite/lenient modes, backspacing (word-aware, protected), progress, and full result recording.

- **Legacy fallback**: Split view (lesson text displayed above a separate plain input field).
  - Implemented in `amphetype/Quizzer.py` as `Typer` (`QTextEdit`) + `Quizzer` container widget with a `WWLabel`.
  - Retained during a transition period; scheduled for later removal.

The primary inline implementation is now the default. Both remain functional and wired to sources, lesson generator, performance history, and statistics via signals in `amphetype/Amphetype.py`.

## Settings

- `which_typer` (integer): 0 = legacy split view, 1 = primary inline. Default: 1.
- Typer-specific options live under the `typer` and `colors` groups (see `amphetype/Config.py`).
- Many general options (font, show_last, auto_review, min_* thresholds, etc.) apply to both.

## Other notes

- Statistics collection, viscosity calculation, and per-char/trigram/word aggregation are shared in concept but have implementation differences between the two typers (notably viscosity measure in the inline version).
- No other major subsystems documented here yet.
