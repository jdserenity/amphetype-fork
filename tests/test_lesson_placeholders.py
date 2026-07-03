from typing_program.lesson_placeholders import IMPROVE_EMPTY_LABEL


def test_improve_empty_label_wording():
  assert 'lessons will start generating once you have enough' in IMPROVE_EMPTY_LABEL
  assert "they'll show up here once" not in IMPROVE_EMPTY_LABEL
