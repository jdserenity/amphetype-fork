
_tagged = set()

class editdistance:
  @staticmethod
  def eval(a, b):
    global _tagged
    if 'editdistance' not in _tagged:
      _tagged.add('editdistance')
      from PyQt5.QtWidgets import QMessageBox as qmb
      qmb.information(None, "Missing Module",
                      """The <code>editdistance</code> module is missing!
Try <code>pip install editdistance</code>""")
    return 0 if a == b else 1
