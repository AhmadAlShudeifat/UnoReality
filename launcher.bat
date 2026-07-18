@echo off
title UnoReality

echo Starting comhost.py...
start "" python comhost.py
timeout /t 1 /nobreak >nul

echo Starting audio.py...
start "" python audio.py
timeout /t 1 /nobreak >nul

echo Starting vrdisplay.py...
start "" python vrdisplay.py
timeout /t 1 /nobreak >nul

echo Starting vrbridge.py...
start "" python vrbridge.py
timeout /t 1 /nobreak >nul

echo Starting handtracking.py...
start "" python handtracking.py
timeout /t 1 /nobreak >nul

echo Launching SteamVR...
start "" "steam://run/250820"

echo All components launched successfully!
pause
