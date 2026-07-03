from setuptools import setup
from glob import glob
from pathlib import Path
import sys

VERSION = (Path(__file__).parent / 'typing_program' / 'VERSION').open('r').read().strip()

setup(
  name='typing-program',
  description='Advanced typing practice program',
  version=VERSION,
  long_description_content_type='text/markdown',
  long_description=open('README.md', 'r').read(),

  author='Frank S. Hestvik',
  author_email='tristesse@gmail.com',
  
  license='GPL3',
  keywords='typing keyboard typist wpm colemak dvorak workman'.split(),
  classifiers=[
    "Development Status :: 5 - Production/Stable",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Intended Audience :: End Users/Desktop",
    "Programming Language :: Python :: 3",
  ],

  packages=['typing_program', 'typing_program.Widgets', 'typing_program.gutenberg'],
  install_requires=['PyQt5', 'translitcodec', 'editdistance'],
  extras_require={
    'test': ['pytest', 'pytest-qt'],
  },
  python_requires='>=3.6', # I use f-strings liberally, carelessly, and licentiously.
  zip_safe=False, # Because we need data/ to be regular files.
  # include_package_data=True,
  entry_points={
    'gui_scripts': ['typing-program = typing_program.main:main_normal'],
  },
  package_data={
    "typing_program": [
      "VERSION",
      "data/texts/*.txt",
      "data/css/*.qss",
      "data/about.html",
      "data/wordlists/*.txt",
      "data/sounds/*",
    ],
  },
  include_package_data=True,
  # install_requires=['appdirs'],
  # data_files=[
  #   ('typing_program', [x for x in glob('data/**/*', recursive=True) if Path(x).is_file()]),
  # ],
)

