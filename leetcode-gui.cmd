@echo off
rem Double-click this to open the leetcode-assistant GUI (no terminal needed).
setlocal
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
rem pythonw runs without a console window; fall back to py if unavailable.
where pythonw >nul 2>nul && (pythonw -m leetcode_assistant gui) || (py -m leetcode_assistant gui)
