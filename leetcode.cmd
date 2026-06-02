@echo off
rem leetcode-assistant launcher (Windows). Lets you run `leetcode <command>` from
rem any directory without installing, by pointing Python at this folder.
setlocal
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
py -m leetcode_assistant %*
