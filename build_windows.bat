@echo off
REM Build DocSealer Batch.exe on Windows.
REM Run this from the project root (where doc_sealer_batch.py and build.spec live).

echo Installing/upgrading dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Building executable with PyInstaller...
pyinstaller build.spec --noconfirm

echo.
echo Done. Find your exe at: dist\DocSealerBatch\DocSealerBatch.exe
pause
