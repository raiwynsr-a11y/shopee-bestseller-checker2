@echo off
setlocal
echo Installing dependencies...
pip install -r requirements.txt
echo Installing PyInstaller...
pip install pyinstaller
echo Building one-file EXE...
pyinstaller --onefile --noconsole --name ShopeeBestSeller main.py
echo.
echo Build complete. See the dist\ShopeeBestSeller.exe
endlocal
