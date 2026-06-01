@echo off
rem leetcode-cli launcher (Windows). Lets you run `leetcode <command>` from
rem any directory without installing, by pointing Python at this folder.
setlocal
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
py -m leetcode_cli %*
