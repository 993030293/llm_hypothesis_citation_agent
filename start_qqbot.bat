@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "NAPCAT_ROOT=C:\Users\99303\git\qqbot-agent\napcat\napcat_app"

title Hypothesis Citation Agent - QQ Bot
cd /d "%ROOT%"

echo ============================================================
echo Hypothesis Citation Agent - QQ Bot
echo ============================================================
echo Project: %ROOT%
echo WebSocket: ws://127.0.0.1:3002
echo.
echo QQ commands:
echo   /official "C:\Users\99303\Desktop\paper.pdf"
echo   /local "C:\Users\99303\Desktop\paper.pdf"
echo.

echo [1/2] Checking NapCat...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = '%NAPCAT_ROOT%';" ^
  "$running = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -like ('*' + $root + '*') };" ^
  "if ($running) { Write-Host 'NapCat already running.' } else { $node = Join-Path $root 'node.exe'; $index = Join-Path $root 'index.js'; if ((Test-Path $node) -and (Test-Path $index)) { Start-Process -FilePath $node -ArgumentList $index -WorkingDirectory $root; Write-Host 'NapCat started.' } else { Write-Host 'NapCat not found. Start NapCat manually from qqbot-agent.' } }"

echo.
echo [2/2] Starting Python QQ bot in this window...
echo Keep this window open. Press Ctrl+C to stop the bot.
echo.

python qqbot\main.py --host 127.0.0.1 --port 3002 --debug

echo.
echo QQ bot stopped. Press any key to close this window.
pause >nul
