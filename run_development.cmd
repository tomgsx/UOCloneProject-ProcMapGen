@echo off
rem Run the desktop application from source on Windows.
rem Needs Python 3.11 or newer from python.org with the py launcher, and the
rem dependencies from pyproject.toml installed (py -3 -m pip install numpy scipy Pillow PySide6 edt).
cd /d "%~dp0"
py -3 -m gui
