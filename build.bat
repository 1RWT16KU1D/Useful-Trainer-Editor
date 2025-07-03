@echo off
:: 1) Obfuscate
setlocal
set OUTDIR=obfuscated
pyarmor obfuscate --recursive -O %OUTDIR% program.py

:: 2) Freeze
pyinstaller --onefile --windowed --icon=trainer.ico %OUTDIR%\program.py

echo Build complete: dist\program.exe
pause
