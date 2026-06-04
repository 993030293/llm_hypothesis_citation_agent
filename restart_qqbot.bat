@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "NAPCAT_ROOT=C:\Users\99303\git\qqbot-agent\napcat\napcat_app"

title Restart Hypothesis Citation Agent - QQ Bot
cd /d "%ROOT%"

echo ============================================================
echo Restart Hypothesis Citation Agent - QQ Bot
echo ============================================================
echo.

echo [1/3] Stopping old Python QQ bot processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = '%ROOT%';" ^
  "$qq = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and ($_.CommandLine -like '*qqbot\main.py*' -or $_.CommandLine -like '*start_hypothesis_qqbot.py*' -or $_.CommandLine -like ('*' + $root + '*qqbot*main.py*')) };" ^
  "foreach ($p in $qq) { Write-Host ('Stopping QQ bot PID ' + $p.ProcessId); Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue };" ^
  "$listeners = netstat -ano | Select-String ':3002\s+.*LISTENING';" ^
  "foreach ($line in $listeners) { $parts = ($line.ToString() -split '\s+') | Where-Object { $_ }; $pid = [int]$parts[-1]; if ($pid -gt 0) { Write-Host ('Stopping PID ' + $pid + ' on port 3002'); Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } }"

echo.
echo [2/3] Stopping old NapCat processes from qqbot-agent...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = '%NAPCAT_ROOT%';" ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -like ('*' + $root + '*') };" ^
  "foreach ($p in $procs) { Write-Host ('Stopping NapCat PID ' + $p.ProcessId); Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }"

echo.
echo [3/3] Starting fresh bot window...
timeout /t 2 /nobreak >nul
call "%ROOT%start_qqbot.bat"
