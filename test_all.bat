@echo off
setlocal EnableDelayedExpansion

echo ======================================================================
echo    AI-Phone-Debloater - Full Repo Pre-Flight / Local CI Suite
echo ======================================================================
echo.

set "FAIL_COUNT=0"
set "STEP=1"

:: --- Step 1: Python Syntax Compile ---
echo [%STEP%] Compiling Python sources...
python -m py_compile cli\src\debloat_engine.py cli\tests\validate_rules.py cli\tests\test_connection.py
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Python syntax check failed!
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] Python bytecode compiled clean.
)
set /a STEP+=1
echo.

:: --- Step 2: Ruff Linter ---
echo [%STEP%] Running Ruff linter...
python -m ruff check cli\
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Ruff linter found errors!
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] Zero lint errors.
)
set /a STEP+=1
echo.

:: --- Step 3: Rules & Blacklist Validation ---
echo [%STEP%] Validating OEM rules and critical blacklist...
python cli\tests\validate_rules.py
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Rule validation failed!
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] Rules valid, zero collisions with critical packages.
)
set /a STEP+=1
echo.

:: --- Step 4: Connection Subsystem Unit Tests ---
echo [%STEP%] Running connection subsystem tests...
python cli\tests\test_connection.py
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Connection unit tests failed!
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] Connection tests passed.
)
set /a STEP+=1
echo.

:: --- Step 5: Engine Help Smoke Test ---
echo [%STEP%] Smoke testing CLI engine (--help and --version)...
python cli\src\debloat_engine.py --help >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [FAIL] CLI --help failed!
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] CLI --help works.
)

python cli\src\debloat_engine.py --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [FAIL] CLI --version failed!
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] CLI --version works.
)
set /a STEP+=1
echo.

:: --- Step 6: Launcher Smoke Test ---
echo [%STEP%] Smoke testing Windows launcher (cli\bin\debloat.bat)...
call cli\bin\debloat.bat --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Launcher failed!
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] Launcher executed cleanly.
)
set /a STEP+=1
echo.

:: --- Step 7: Version Consistency Check ---
echo [%STEP%] Checking VERSION file consistency...
python -c "import pathlib, sys; sys.path.insert(0, 'cli/src'); import debloat_engine as e; vf = pathlib.Path('VERSION').read_text('utf-8').strip(); assert e.__version__ == vf, f'Mismatch: engine={e.__version__} file={vf}'; print(f'Consistent: v{vf}')"
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Version mismatch between VERSION file and engine!
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] Version consistent across files.
)
set /a STEP+=1
echo.

:: --- Step 8: Web Dashboard Build ---
echo [%STEP%] Building Astro web dashboard...
where npm >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] npm not found on PATH - skipping web build.
) else (
    pushd web
    call npm run build
    if !ERRORLEVEL! neq 0 (
        echo [FAIL] Web build failed!
        set /a FAIL_COUNT+=1
    ) else (
        echo [PASS] Web dashboard built successfully.
    )
    popd
)
echo.

:: --- Summary ---
echo ======================================================================
if !FAIL_COUNT! equ 0 (
    echo    ALL CHECKS PASSED - Repo is clean and ready to commit/push!
    echo ======================================================================
    exit /b 0
) else (
    echo    FAILED: !FAIL_COUNT! checks failed. See output above.
    echo ======================================================================
    exit /b 1
)
