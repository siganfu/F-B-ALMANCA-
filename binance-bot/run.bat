@echo off
REM Windows: botu bir kez çalıştırır (Görev Zamanlayıcı tarafından saat başı tetiklenir).
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m bot.main %*
) else (
    python -m bot.main %*
)
exit /b %ERRORLEVEL%
