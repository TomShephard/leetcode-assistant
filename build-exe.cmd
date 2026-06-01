@echo off
rem Build a standalone Windows EXE for the LeetCode GUI using PyInstaller.
rem Output: dist\LeetCodeCLI.exe  (double-clickable, no Python needed)
setlocal
cd /d "%~dp0"

echo Installing PyInstaller (if needed)...
py -m pip install --user --upgrade pyinstaller
if errorlevel 1 (
  echo.
  echo Failed to install PyInstaller. See the message above.
  exit /b 1
)

echo.
echo Building EXE...
py -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name LeetCodeCLI ^
  --icon "%~dp0leetcode_cli\icon.ico" ^
  --paths "%~dp0" ^
  --collect-submodules leetcode_cli ^
  --collect-data leetcode_cli ^
  gui_app.py

if errorlevel 1 (
  echo.
  echo Build failed. See the message above.
  exit /b 1
)

echo.
echo Done. Your EXE is at: %~dp0dist\LeetCodeCLI.exe
endlocal
