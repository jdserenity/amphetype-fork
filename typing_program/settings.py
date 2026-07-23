

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QSpinBox, QDoubleSpinBox
from typing_program.fwidgets import FColorButton


class FVar(QObject):
  onChange = pyqtSignal(QObject)

  def __init__(self, parent, name):
    super().__init__(parent, objectName=name)
    self._name = name


class FValueVar(FVar):
  def __init__(self, parent, name, val):
    super().__init__(parent, name)
    self._value = self.convert(val)

  def __call__(self, val=None):
    if val is not None:
      return self.set(val)
    return self.get()

  def get(self):
    return self._value

  def set(self, val):
    val = self.convert(val)
    self._value = val
    self.onValue.emit(val)
    self.onChange.emit(self)

  def bind_value(self, func, call=True):
    self.onValue.connect(func)
    if call:
      return func(self.get())

  def bind_change(self, func, call=True):
    self.onChange.connect(func)
    if call:
      return func()

  def button(self, text):
    raise NotImplementedError

  def spin_box(self, min, max=None, step=None):
    if not hasattr(self, '_spin_box_class'):
      raise NotImplementedError

    if max is None:
      min, max = self.convert(0), max
    if step is None:
      step = self.convert(1)

    return self._spin_box_class(
      minimum=min, maximum=max, singleStep=step,
      value=self.get(), valueChanged=self.set)

class FIntVar(FValueVar):
  onValue = pyqtSignal(int)
  _spin_box_class = QSpinBox

  def convert(self, val):
    return int(val)
  
class FFloatVar(FValueVar):
  onValue = pyqtSignal(float)
  _spin_box_class = QDoubleSpinBox

  def convert(self, val):
    return float(val)


class FColorVar(FValueVar):
  onValue = pyqtSignal(QColor)

  def convert(self, val):
    return QColor(val)

  def button(self, text=''):
    return FColorButton(self, text)
  
class FBoolVar(FValueVar):
  onValue = pyqtSignal(bool)

  def convert(self, val):
    if isinstance(val, str):
      return False if not val or val.lower() == 'false' else True
    if isinstance(val, (bool, int)):
      return val
    raise TypeError(f'invalid type given for bool variable {type(val)}')


class FStringVar(FValueVar):
  onValue = pyqtSignal(str)

  def convert(self, val):
    return '' if val is None else str(val)


class FChoiceVar(FValueVar):
  onValue = pyqtSignal(int)
  
  def __init__(self, parent, name, val, choices):
    self._choices = list(choices)
    super().__init__(parent, name, val)

  def choices(self):
    return self._choices

  def choice(self):
    return self._choices[self._value]

  def convert(self, val):
    try:
      return self._choices.index(val)
    except ValueError:
      pass
    val = int(val)
    if not (0 <= val < len(self._choices)):
      raise ValueError(f'{val} neither an index nor value in {self._choices}')
    return val


class FGroupVar(FVar):
  def __getitem__(self, name):
    return self(name).get()

  def __setitem__(self, name, value):
    self(name).set(val)

  def __call__(self, name):
    obj = self.findChild(FVar, self.objectName() + '/' + name)
    if not obj:
      raise ValueError(f"variable not found: {name}")
    return obj

  def __iter__(self):
    return (x for x in self.children() if isinstance(x, FValueVar))


class FSettings(QSettings):
  def __init__(self, *args, appname=None, filename=None, **kwargs):
    assert appname or filename
    if filename:
      super().__init__(filename, QSettings.IniFormat)
    else:
      super().__init__(QSettings.IniFormat, QSettings.UserScope, appname, appname)

  def __getitem__(self, name):
    ch = self.findChild(FVar, name)
    assert ch is not None
    return ch

  def create(self, parent, name, val):
    if isinstance(val, dict):
      return self.makeSettings(name, val, parent=None)

    extra = None
    if isinstance(val, tuple):
      val, extra = val

    actual = self.value(name) if self.contains(name) else val

    if isinstance(val, int) and isinstance(extra, (list, tuple)):
      obj = FChoiceVar(parent, name, actual, extra)
    elif isinstance(val, int) and extra is None:
      obj = FIntVar(parent, name, actual)
    elif isinstance(val, float):
      obj = FFloatVar(parent, name, actual)
    elif isinstance(val, QColor):
      obj = FColorVar(parent, name, actual)
    elif isinstance(val, bool):
      obj = FBoolVar(parent, name, actual)
    elif isinstance(val, str):
      obj = FStringVar(parent, name, actual)
    else:
      raise RuntimeError(f'unknown type {type(val)} for {name}')

    return obj

  def makeSettings(self, name, opts=None, parent=None):
    grp = FGroupVar(parent or self, name)
    for k, v in opts.items():
      obj = self.create(grp, name + '/' + k, v)
      obj.onChange.connect(grp.onChange)
    if not parent:
      grp.onChange.connect(self.varChanged)
    return grp

  def varChanged(self, obj):
    self.setValue(obj.objectName(), obj.get())