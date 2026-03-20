@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ========================================
echo Skills Junction Link Builder
echo ========================================
echo.

set "SOURCE_DIR=C:\Users\Administrator\.cc-switch\skills"
set "TARGET1=C:\Users\Administrator\.cursor\skills"
set "TARGET2=C:\Users\Administrator\.kilocode\skills"
set "TARGET3=C:\Users\Administrator\.claude\skills"
set "TARGET4=C:\Users\Administrator\.codex\skills"

set /a OK_COUNT=0
set /a SKIP_COUNT=0
set /a FAIL_COUNT=0
set "FOUND_ANY="

if not exist "%SOURCE_DIR%" (
    echo [ERROR] Source directory not found:
    echo %SOURCE_DIR%
    echo.
    pause
    exit /b 1
)

call :ensure_dir "%TARGET1%" || goto :end_fail
call :ensure_dir "%TARGET2%" || goto :end_fail
call :ensure_dir "%TARGET3%" || goto :end_fail
call :ensure_dir "%TARGET4%" || goto :end_fail

echo Source:
echo   %SOURCE_DIR%
echo.
echo Targets:
echo   %TARGET1%
echo   %TARGET2%
echo   %TARGET3%
echo   %TARGET4%
echo.

for /d %%S in ("%SOURCE_DIR%\*") do (
    set "FOUND_ANY=1"
    echo ----------------------------------------
    echo Processing folder: %%~nxS
    call :link_one "%%~fS" "%TARGET1%\%%~nxS"
    call :link_one "%%~fS" "%TARGET2%\%%~nxS"
    call :link_one "%%~fS" "%TARGET3%\%%~nxS"
    call :link_one "%%~fS" "%TARGET4%\%%~nxS"
)

if not defined FOUND_ANY (
    echo [WARN] No subfolders found under source directory.
    echo.
)

echo ========================================
echo Done
echo   OK   : !OK_COUNT!
echo   SKIP : !SKIP_COUNT!
echo   FAIL : !FAIL_COUNT!
echo ========================================
echo.
pause
exit /b 0

:ensure_dir
if exist "%~1" exit /b 0
mkdir "%~1" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Failed to create target directory:
    echo %~1
    exit /b 1
)
echo [INIT] Created target directory:
echo %~1
exit /b 0

:link_one
set "TARGET_PATH=%~2"
set "TARGET_DIR=%~dp2"
set "TARGET_NAME=%~nx2"
set "ENTRY_EXISTS="
set "ENTRY_IS_LINK="

dir /a /b "%TARGET_DIR%" 2>nul | findstr /i /x /c:"%TARGET_NAME%" >nul && set "ENTRY_EXISTS=1"
dir /a:l /b "%TARGET_DIR%" 2>nul | findstr /i /x /c:"%TARGET_NAME%" >nul && set "ENTRY_IS_LINK=1"

if defined ENTRY_EXISTS (
    pushd "%TARGET_PATH%" >nul 2>nul && (
        popd
        if defined ENTRY_IS_LINK (
            echo [SKIP] Junction already exists: %TARGET_PATH%
        ) else (
            echo [SKIP] Directory already exists: %TARGET_PATH%
        )
        set /a SKIP_COUNT+=1
        exit /b 0
    )

    if defined ENTRY_IS_LINK (
        echo [SKIP] Broken or inaccessible junction already exists: %TARGET_PATH%
        echo        -> %~1
    ) else (
        echo [SKIP] Existing item is inaccessible or not a directory: %TARGET_PATH%
        echo        -> %~1
    )
    set /a SKIP_COUNT+=1
    exit /b 0
)

mklink /J "%TARGET_PATH%" "%~1" >nul 2>nul
if errorlevel 1 (
    echo [FAIL] Failed to create junction: %TARGET_PATH%
    echo        -> %~1
    echo        Check permissions or whether another item already occupies the path.
    set /a FAIL_COUNT+=1
    exit /b 1
)

echo [OK] %TARGET_PATH%
echo      -> %~1
set /a OK_COUNT+=1
exit /b 0

:end_fail
echo.
echo Script stopped because a target directory could not be prepared.
echo.
pause
exit /b 1
