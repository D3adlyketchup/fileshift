# fileshift.spec
# Build the standalone .exe with:
#   pyinstaller fileshift.spec

import sys
import customtkinter
from pathlib import Path

block_cipher = None

# Dynamically find customtkinter — works in venv AND system/CI installs
ctk_path = str(Path(customtkinter.__file__).parent)

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        (ctk_path, 'customtkinter'),
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL.Image',
        'moviepy',
        'moviepy.editor',
        'pdf2image',
        'pptx',
        'comtypes',
        'comtypes.client',
        'tkinter',
        'tkinterdnd2',
        'imageio',
        'imageio.plugins.ffmpeg',
        'proglog',
        'tqdm',
    ],
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
    name='FileShift',
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
