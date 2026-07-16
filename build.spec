# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for DocSealer Batch.
#
# Usage:
#   pyinstaller build.spec
#
# If a `poppler/` folder (containing a `bin/` subfolder with pdftoppm.exe,
# pdfinfo.exe, etc.) exists next to this spec file, it will be bundled into
# the exe automatically so pdf2image works without requiring a system-wide
# Poppler install on the end user's machine. See README.md for where to get
# a Windows Poppler build.

import os

block_cipher = None

# Bundle poppler/ only if it exists at build time.
poppler_datas = []
if os.path.isdir('poppler'):
    poppler_datas.append(('poppler', 'poppler'))

a = Analysis(
    ['doc_sealer_batch.py'],
    pathex=[],
    binaries=[],
    datas=poppler_datas,
    hiddenimports=['pillow_heif'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DocSealerBatch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
