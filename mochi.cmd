@echo off
rem Mochi launcher. Usage: mochi  |  mochi "task"  |  mochi --unattended --task-file x.txt
rem Works from any folder: PYTHONPATH points at this script's folder so the 'agent' package is found.
setlocal
title Mochi
set "PYTHONPATH=%~dp0.;%PYTHONPATH%"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
"%~dp0.venv\Scripts\python.exe" -m agent.cli %*
