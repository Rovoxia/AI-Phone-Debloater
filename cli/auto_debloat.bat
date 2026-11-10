@echo off
setlocal EnableDelayedExpansion

rem AI-Phone-Debloater auto rule pipeline
rem Modes:
rem   dump    dump packages -> draft rules -> validate -> sync
rem   apply   apply categorization manifest -> validate -> sync
rem   check   validate + sync only (no device needed)

set "MODE=%~1"
if "%MODE%"=="" set MODE=dump

rem --- Shared checks ---
where adb >nul 2>&1
if errorlevel 1 (
    if not "%MODE%"=="check" (
        echo ERROR: adb not found on PATH. Install Android Platform-Tools or add adb to PATH.
        goto end
    )
)
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found on PATH.
    goto end
)

rem --- MODE: dump ---
if "%MODE%"=="dump" (
    if not exist "scans" mkdir scans
    set MODEL=
    set /p MODEL="Enter device model (e.g. pixel7a, xiaomi_note10): "
    if "%MODEL%"=="" (echo ERROR: Model name required. & goto end)
    set MFR=
    set /p MFR="Enter manufacturer (Xiaomi, Samsung, OnePlus, etc.): "
    if "%MFR%"=="" (echo ERROR: Manufacturer required. & goto end)
    set DUMP_FILE=scans\%MODEL%.txt

    echo Dumping User 0 packages to %DUMP_FILE% ...
    adb shell pm list packages -U --user 0 > "%DUMP_FILE%"
    if errorlevel 1 (echo ERROR: ADB dump failed. Check device connection and USB debugging. & goto end)
    echo Dump saved: %DUMP_FILE%

    echo Generating draft rules for %MFR% ...
    python cli\tools\scan_to_rules.py --input "%DUMP_FILE%" --manufacturer "%MFR%" --output "cli\rules\%MODEL%.json" --drop-uncategorized
    if errorlevel 1 (echo ERROR: Rule draft generation failed. & goto end)
    echo Draft rule file: cli\rules\%MODEL%.json

    echo Running rule validation ...
    python cli/tests/validate_rules.py
    if errorlevel 1 (echo ERROR: Validation failed. Fix Tier-4 collisions or duplicate packages before merge. & goto end)
    echo Validation passed: Zero collisions.

    echo Syncing web rules dataset ...
    python cli/generate_rules_dataset.py
    if errorlevel 1 (echo ERROR: Dataset sync failed. & goto end)
    echo SUCCESS: Rules updated and web dataset in sync.
    echo Next step: open PR from QA branch targeting main.
    goto end
)

rem --- MODE: apply ---
if "%MODE%"=="apply" (
    set MANIFEST=%~2
    if "%MANIFEST%"=="" (echo ERROR: Usage: auto_debloat.bat apply ^<manifest.json^> & goto end)
    if not exist "%MANIFEST%" (echo ERROR: Manifest file not found: %MANIFEST% & goto end)
    set OUTFILE=%~3
    if "%OUTFILE%"=="" set OUTFILE=cli\rules\%MANIFEST%.json

    echo Applying categorization manifest %MANIFEST% ...
    python cli\tools\scan_to_rules.py --input "%MANIFEST%" --manufacturer "auto" --apply-manifest "%MANIFEST%" --output "%OUTFILE%"
    if errorlevel 1 (echo ERROR: Manifest apply failed. & goto end)

    echo Running rule validation ...
    python cli/tests/validate_rules.py
    if errorlevel 1 (echo ERROR: Validation failed. Fix Tier-4 collisions or duplicate packages before merge. & goto end)
    echo Validation passed: Zero collisions.

    echo Syncing web rules dataset ...
    python cli/generate_rules_dataset.py
    if errorlevel 1 (echo ERROR: Dataset sync failed. & goto end)
    echo SUCCESS: Rules updated and web dataset in sync.
    goto end
)

rem --- MODE: check ---
if "%MODE%"=="check" (
    echo Running rule validation ...
    python cli/tests/validate_rules.py
    if errorlevel 1 (echo ERROR: Validation failed. & goto end)
    echo Validation passed: Zero collisions.

    echo Syncing web rules dataset ...
    python cli/generate_rules_dataset.py
    if errorlevel 1 (echo ERROR: Dataset sync failed. & goto end)
    echo SUCCESS: Web dataset in sync.
    goto end
)

echo ERROR: Unknown mode "%MODE%". Use dump, apply, or check.
goto end

:end
echo.
pause