@echo off
REM ============================================================
REM  Greyhound Pipeline — Windows Task Scheduler Setup
REM
REM  Creates two daily tasks:
REM    Greyhound_Morning  — 7:00 AM AEST
REM    Greyhound_Evening  — 4:00 PM AEST
REM
REM  Each task runs: python run_pipeline.py --email
REM
REM  Requirements:
REM    - Run this script as Administrator (or the tasks will be
REM      created for the current user only)
REM    - Python must be on the system PATH
REM    - Working directory: C:\greyhound_realtime\Greyhound-Agent
REM ============================================================

SET PYTHON=python
SET WORKDIR=C:\greyhound_realtime\Greyhound-Agent
SET SCRIPT=%WORKDIR%\run_pipeline.py
SET TASK_MORNING=Greyhound_Morning
SET TASK_EVENING=Greyhound_Evening

echo.
echo ============================================================
echo  Greyhound Pipeline Task Scheduler Setup
echo ============================================================
echo.

REM ── Morning task (7:00 AM AEST) ─────────────────────────────────────────────
echo [1/2] Creating task: %TASK_MORNING% (07:00 daily)

schtasks /create ^
  /tn "%TASK_MORNING%" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\" --email" ^
  /sc DAILY ^
  /st 07:00 ^
  /sd %DATE% ^
  /rl HIGHEST ^
  /ru "" ^
  /f ^
  /HRESULT

IF %ERRORLEVEL% EQU 0 (
    echo     OK — %TASK_MORNING% created.
) ELSE (
    echo     WARN — Could not set HIGHEST privilege. Retrying without /rl ...
    schtasks /create ^
      /tn "%TASK_MORNING%" ^
      /tr "\"%PYTHON%\" \"%SCRIPT%\" --email" ^
      /sc DAILY ^
      /st 07:00 ^
      /sd %DATE% ^
      /ru "" ^
      /f
    IF %ERRORLEVEL% EQU 0 (
        echo     OK — %TASK_MORNING% created (standard privilege).
    ) ELSE (
        echo     ERROR — Failed to create %TASK_MORNING%.
    )
)

REM Limit execution time to 30 minutes
schtasks /change /tn "%TASK_MORNING%" /ET 00:30 >NUL 2>&1

REM Do not start new instance if already running
schtasks /change /tn "%TASK_MORNING%" /HRESULT >NUL 2>&1

echo.

REM ── Evening task (4:00 PM AEST) ─────────────────────────────────────────────
echo [2/2] Creating task: %TASK_EVENING% (16:00 daily)

schtasks /create ^
  /tn "%TASK_EVENING%" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\" --email" ^
  /sc DAILY ^
  /st 16:00 ^
  /sd %DATE% ^
  /rl HIGHEST ^
  /ru "" ^
  /f ^
  /HRESULT

IF %ERRORLEVEL% EQU 0 (
    echo     OK — %TASK_EVENING% created.
) ELSE (
    echo     WARN — Could not set HIGHEST privilege. Retrying without /rl ...
    schtasks /create ^
      /tn "%TASK_EVENING%" ^
      /tr "\"%PYTHON%\" \"%SCRIPT%\" --email" ^
      /sc DAILY ^
      /st 16:00 ^
      /sd %DATE% ^
      /ru "" ^
      /f
    IF %ERRORLEVEL% EQU 0 (
        echo     OK — %TASK_EVENING% created (standard privilege).
    ) ELSE (
        echo     ERROR — Failed to create %TASK_EVENING%.
    )
)

schtasks /change /tn "%TASK_EVENING%" /ET 00:30 >NUL 2>&1

echo.

REM ── Confirm tasks ────────────────────────────────────────────────────────────
echo ============================================================
echo  Verification (schtasks /query):
echo ============================================================
echo.
schtasks /query /tn "%TASK_MORNING%" /fo LIST 2>NUL | findstr /i "TaskName Status Next Run"
echo.
schtasks /query /tn "%TASK_EVENING%" /fo LIST 2>NUL | findstr /i "TaskName Status Next Run"
echo.

echo ============================================================
echo  Done. To remove tasks:
echo    schtasks /delete /tn "Greyhound_Morning" /f
echo    schtasks /delete /tn "Greyhound_Evening" /f
echo ============================================================
echo.
pause
