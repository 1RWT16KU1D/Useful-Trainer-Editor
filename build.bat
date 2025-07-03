@echo off
:: 1) Obfuscate
pyarmor obfuscate --recursive program.py

:: 2) Freeze
pyinstaller --onefile --windowed --icon="C:\Users\mhade\Desktop\Useful-Trainer-Editor\trainer.ico" dist\program.py

echo Build complete: dist\program.exe
pause
