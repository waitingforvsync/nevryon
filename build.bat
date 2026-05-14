@echo off
rem Build all four Nevryon runtime binaries from disasm\Nevryon.6502
rem and verify they match the originals byte-for-byte.
setlocal
cd /d "%~dp0"
if not exist build mkdir build

where beebasm >nul 2>&1
if errorlevel 1 (
    echo beebasm not found in PATH -- install BeebAsm ^(https://github.com/stardot/beebasm^) 1>&2
    exit /b 1
)

echo Building from disasm\Nevryon.6502 ...
pushd disasm
beebasm -i Nevryon.6502 >nul
if errorlevel 1 (
    popd
    exit /b 1
)
popd

echo Verifying byte-identity against extracted\ ...
set "status=0"
for %%n in (CODE CODE2 CODE3 GRAPHIX) do (
    fc /b "build\%%n" "extracted\$.%%n" >nul
    if errorlevel 1 (
        echo   %%n MISMATCH
        set "status=1"
    ) else (
        echo   %%n BYTE-IDENTICAL
    )
)

if "%status%"=="0" echo All four binaries match the originals.
exit /b %status%
