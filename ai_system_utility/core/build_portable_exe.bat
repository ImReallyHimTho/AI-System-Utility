@echo off
title Building PORTABLE AI System Utility (single EXE)...
echo ==========================================
echo   AI SYSTEM UTILITY - PORTABLE EXE BUILD
echo ==========================================
echo.

REM ---- CLEAN OLD BUILDS (PORTABLE) ----
echo Cleaning old build folders...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist AI_System_Utility_Portable.spec del /q AI_System_Utility_Portable.spec

REM ---- RUN PYINSTALLER (ONEFILE) ----
echo Running PyInstaller (portable, single EXE)...

pyinstaller ^
    --name "AI_System_Utility_Portable" ^
    --onefile ^
    --noconsole ^
    --clean ^
    --icon=icon.ico ^
    -m ai_system_utility.gui

echo.
echo ==========================================
echo   PORTABLE BUILD COMPLETE
echo   Output EXE:
echo     dist\AI_System_Utility_Portable.exe
echo ==========================================
pause
