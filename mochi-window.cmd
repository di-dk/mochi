@echo off
rem Mochi's own chat window (no console). Same agent as the terminal; use mochi.cmd for the terminal.
setlocal
set "PYTHONPATH=%~dp0.;%PYTHONPATH%"
set PYTHONUTF8=1
start "" "%~dp0.venv\Scripts\pythonw.exe" -m agent.cli --gui %*
