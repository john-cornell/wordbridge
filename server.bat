@echo off
title Wordbridge Server
echo Starting Wordbridge via WSL (Ubuntu)...
echo.
wsl.exe -d Ubuntu bash -lc "cd ~/Code/wordbridge && source .venv/bin/activate && python app.py"
echo.
echo Server stopped.
pause
