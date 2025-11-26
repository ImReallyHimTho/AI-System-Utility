@echo off
title Building AI System Utility Installer...

echo STEP 1: Building EXE...
call build_exe.bat

echo STEP 2: Building Installer...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss

echo ==========================================
echo   INSTALLER BUILD COMPLETE!
echo   Output:
echo     AI_System_Utility_Installer.exe
echo ==========================================
pause
