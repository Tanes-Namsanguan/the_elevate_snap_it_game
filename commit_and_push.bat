@echo off
REM ============================================================
REM  commit_and_push.bat
REM  Stage all changes, commit, and push to the current branch.
REM
REM  Usage:
REM    commit_and_push.bat "your commit message"
REM    commit_and_push.bat            (will prompt for a message)
REM ============================================================
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo === git status ===
git status --short
echo.

REM Combine all arguments into one commit message (so quotes are optional)
set "MSG=%*"

if "%MSG%"=="" (
    set /p MSG=Commit message: 
)

if "%MSG%"=="" (
    echo No commit message given, aborting.
    goto :end
)

git add -A

git diff --cached --quiet
if %errorlevel%==0 (
    echo Nothing staged to commit — skipping commit step.
) else (
    git commit -m "%MSG%"
    if errorlevel 1 (
        echo Commit failed. Aborting push.
        goto :end
    )
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"

echo.
echo === Pushing to origin/%BRANCH% ===
git push origin %BRANCH%

if errorlevel 1 (
    echo Push failed. Check the error above.
) else (
    echo Done.
)

:end
echo.
pause
