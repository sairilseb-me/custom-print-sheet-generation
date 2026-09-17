# -*- mode: python ; coding: utf-8 -*-
#
# Build with: pyinstaller build.spec
#
# Targets main.py (not patch_pos/app.py directly) -- running app.py as
# the top-level script breaks its relative imports, since there's no
# parent package in that context. See main.py's docstring.
#
# Cross-platform: this same spec produces dist/PrintSheetPOS.app on
# macOS and dist/PrintSheetPOS/PrintSheetPOS.exe on Windows. The BUNDLE
# step below only has meaning on macOS -- PyInstaller no-ops it on other
# platforms -- so no platform branching is needed here. PyInstaller does
# not cross-compile, though: build on the target OS itself.

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('frontend', 'frontend')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PrintSheetPOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PrintSheetPOS',
)
app = BUNDLE(
    coll,
    name='PrintSheetPOS.app',
    icon=None,
    bundle_identifier='com.mnp.printsheetpos',
)
