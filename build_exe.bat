@echo off
rem ---------------------------------------------------------------------------
rem Build a standalone Windows executable of the ClassIsland ManagementServer
rem (Python reimplementation) with Nuitka.
rem
rem Output: out\ManagementServer.exe  (+ the WebUI under out\static\)
rem ---------------------------------------------------------------------------
setlocal

set PYTHON=%~dp0miniconda3\envs\man\python.exe
if not exist "%PYTHON%" (
    echo [ERROR] Python environment not found: %PYTHON%
    exit /b 1
)

set PYTHONPATH=%~dp0protos

"%PYTHON%" -m nuitka ^
    --mingw64 ^
    --assume-yes-for-downloads ^
    --standalone ^
    --output-dir=%~dp0out ^
    --output-filename=ManagementServer.exe ^
    --include-data-dir=%~dp0app\static=static ^
    --include-package=Protobuf ^
    --include-package=uvicorn ^
    --include-package=grpc ^
    --include-package=sqlalchemy ^
    --include-package=fastapi ^
    --include-package=pgpy ^
    --include-package=cryptography ^
    --include-package=bcrypt ^
    --include-package=jwt ^
    --include-package=pymysql ^
    --nofollow-import-to=pytest,tests,test ^
    "%~dp0main.py"

if errorlevel 1 (
    echo [ERROR] Nuitka build failed.
    exit /b 1
)

rem ---------------------------------------------------------------------------
rem Copy the conda runtime DLLs that the standalone build cannot discover.
rem
rem Nuitka does not track DLLs that extension modules load at *runtime* via
rem ctypes/import mechanism, so these must be staged next to the executable:
rem   libssl / libcrypto  -> required by the _ssl module (anyio, httpx, jwt)
rem   sqlite3             -> required by _sqlite3 (SQLAlchemy default driver)
rem   zlib/liblzma/libbz2/libexpat -> required by zlib/bz2/lzma/pyexpat
rem   ffi-8/ffi-7/ffi     -> required by _ctypes, which `click` imports
rem
rem Missing libffi is especially nasty: `import click` inside a frozen build
rem terminates the process with exit code 3 and no output at all, because
rem uvicorn.server imports click at module scope.
rem ---------------------------------------------------------------------------
set CONDA_BIN=%~dp0miniconda3\envs\man\Library\bin
set DIST=%~dp0out\main.dist
if not exist "%CONDA_BIN%" (
    echo [ERROR] Conda library directory not found: %CONDA_BIN%
    exit /b 1
)

for %%F in (
    libssl-3-x64.dll
    libcrypto-3-x64.dll
    sqlite3.dll
    zlib.dll
    libexpat.dll
    libbz2.dll
    liblzma.dll
    ffi-8.dll
    ffi-7.dll
    ffi.dll
) do (
    if exist "%CONDA_BIN%\%%F" (
        copy /Y "%CONDA_BIN%\%%F" "%DIST%\%%F" >nul
    ) else (
        echo [WARN] Missing runtime DLL: %CONDA_BIN%\%%F
    )
)

echo.
echo Build finished: %DIST%\ManagementServer.exe
endlocal
