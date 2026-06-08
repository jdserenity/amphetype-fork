
# XXX: TODO, .exe installs for windows, app(??) for osx
# from distutils.core import setup
# import py2exe

# setup(
#       windows=[{"script" : "Amphetype.py"}],
#         options={"py2exe" :
#             {"includes" : ["sip"],
#             "dist_dir": "Amphetype"}},
#         data_files=[('txt', glob.glob('txt/*.txt')),
#             ('', ['about.html', "gpl.txt"]),
#             ('txt/wordlists', glob.glob('txt/wordlists/*.txt'))]
#     )

from setuptools import setup
from glob import glob
from pathlib import Path
import sys

VERSION = (Path(__file__).parent / 'amphetype' / 'VERSION').open('r').read().strip()

setup(
  name='amphetype',
  description='Advanced typing practice program',
  version=VERSION,
  long_description_content_type='text/markdown',
  long_description=open('README.md', 'r').read(),

  url='https://gitlab.com/franksh/amphetype',
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

  packages=['amphetype', 'amphetype.Widgets', 'amphetype.gutenberg'],
  install_requires=['PyQt5', 'translitcodec', 'editdistance'],
  extras_require={
    'test': ['pytest', 'pytest-qt'],
  },
  python_requires='>=3.6', # I use f-strings liberally, carelessly, and licentiously.
  zip_safe=False, # Because we need data/ to be regular files.
  # include_package_data=True,
  entry_points={
    'gui_scripts': ['amphetype = amphetype.main:main_normal'],
  },
  package_data={
    "amphetype": [
      "VERSION",
      "data/texts/*.txt",
      "data/css/*.qss",
      "data/about.html",
      "data/wordlists/*.txt"
    ],
  },
  include_package_data=True,
  # install_requires=['appdirs'],
  # data_files=[
  #   ('amphetype', [x for x in glob('data/**/*', recursive=True) if Path(x).is_file()]),
  # ],
)

