@echo off
cd /d C:\Users\yiseg\.qclaw\workspace
echo === 1. git add -A ===
git add -A
echo.
echo === 2. git commit ===
git commit -m "backup: 2026-05-29 workspace snapshot"
echo.
echo === 3. git push ===
git push origin master
echo.
echo === DONE (exit code %ERRORLEVEL%) ===
pause
