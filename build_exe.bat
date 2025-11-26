@echo off
title Building AI System Utility EXE...
echo ==========================================
echo   AI SYSTEM UTILITY - EXE BUILD SCRIPT
echo ==========================================
echo.

REM ---- CLEAN OLD BUILDS ----
echo Cleaning old build folders...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist AI_System_Utility.spec del /q AI_System_Utility.spec

REM ---- RUN PYINSTALLER ----
echo Running PyInstaller...
pyinstaller ^
    --name "AI_System_Utility" ^
    --noconsole ^
    --windowed ^
    --clean ^
    --icon=icon.ico ^
    -m ai_system_utility.gui

echo.
echo ==========================================
echo   BUILD COMPLETE
echo   Output EXE is in: dist\AI_System_Utility\
echo ==========================================
pause
