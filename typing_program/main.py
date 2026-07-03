

def main_normal():
  import typing_program.mainwindow as A
  from typing_program.license import ensure_licensed

  if not ensure_licensed(A.app, A.Settings):
    return 1

  w = A.MainWindow()
  w.show()
  r = A.app.exec_()
  A.DB.commit()
  return r


def main_portable():
  import sys
  sys.argv.append('--local')
  return main_normal()
  
