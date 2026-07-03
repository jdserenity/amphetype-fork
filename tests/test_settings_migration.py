"""Settings key migrations."""

from PyQt5.QtCore import QSettings


def test_migrate_ana_settings_to_analysis(qapp, tmp_path, monkeypatch):
  import amphetype.Config as cfg
  ini = tmp_path / 'amphetype.ini'
  qs = QSettings(str(ini), QSettings.IniFormat)
  qs.setValue('ana_which', 'damage desc')
  qs.setValue('ana_what', 2)
  qs.setValue('ana_many', 40)
  qs.setValue('ana_count', 3)
  qs.sync()
  monkeypatch.setattr(
    cfg, 'cli_options',
    type('o', (), {'settings': str(ini), 'local': False, 'database': None})())
  s = cfg.AmphSettings()
  assert s.get('analysis_which') == 'damage desc'
  assert s.get('analysis_what') == 2
  assert s.get('analysis_many') == 40
  assert s.get('analysis_count') == 3
  assert not s.contains('ana_which')
  assert not s.contains('ana_count')
