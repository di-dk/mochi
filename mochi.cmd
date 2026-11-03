@echo off
rem Mochi launcher. Usage: mochi  |  mochi "task"  |  mochi --unattended --task-file x.txt
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
"%~dp0.venv\Scripts\python.exe" -m agent.cli %*
