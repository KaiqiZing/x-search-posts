@echo off
REM ============================================================
REM  x-search-posts  -  one-time X (Twitter) login helper
REM  Double-click this file. A Chrome window opens; log in to X
REM  there (including 2FA). The session is saved automatically.
REM ============================================================
setlocal

REM --- Locate Node.js (tries managed runtime with any version, then common installs) ---
set "NODE="
for /f "delims=" %%F in ('dir /b /s /o-n "%USERPROFILE%\.workbuddy\binaries\node\versions\*\node.exe" 2^>nul') do (
  if not defined NODE set "NODE=%%F"
)
if not defined NODE if exist "C:\nvm4w\nodejs\node.exe" set "NODE=C:\nvm4w\nodejs\node.exe"
if not defined NODE if exist "%ProgramFiles%\nodejs\node.exe" set "NODE=%ProgramFiles%\nodejs\node.exe"
if not defined NODE for /f "delims=" %%F in ('where node 2^>nul') do (
  if not defined NODE set "NODE=%%F"
)
if not defined NODE (
  echo [ERROR] Node.js not found. Install Node.js 18+ first:
  echo   https://nodejs.org/
  pause
  exit /b 1
)
echo   Using Node: %NODE%

set "SCRIPT=%~dp0browser_collect.js"

echo.
echo   ============================================================
echo     x-search-posts  -  X login (one time only)
echo   ============================================================
echo     A Chrome window will open at x.com/login.
echo     Log in to X there (including 2FA if enabled).
echo     This window keeps waiting - take your time.
echo     Once login is detected it saves and closes by itself.
echo   ============================================================
echo.

"%NODE%" "%SCRIPT%" --login --timeout 0

set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" echo   [OK] Login saved. You never need to do this again.
if "%RC%"=="2" echo   [TIMEOUT] No login detected. Run this file again when ready.
if "%RC%"=="5" echo   [CLOSED] The browser window was closed before login finished.
echo.
pause
endlocal
