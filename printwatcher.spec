# PyInstaller spec for the desktop UI binary (windowed, no console).
#
# Build both binaries (UI + CLI):
#   pip install pyinstaller watchdog pystray pillow pypdf reportlab pypdfium2
#   pyinstaller printwatcher.spec --noconfirm
#   pyinstaller printwatcher-cli.spec --noconfirm
#
# Outputs:
#   dist/PrintWatcher.exe       windowed UI (double-click to launch)
#   dist/PrintWatcher-cli.exe   console, dispatches every helper

block_cipher = None

a = Analysis(
    ['print_watcher_ui.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/printwatcher.ico', 'assets'),
        ('assets/printwatcher.png', 'assets'),
    ],
    hiddenimports=[
        'pystray._win32',
        'PIL._tkinter_finder',
        'pypdf',
        'pypdfium2',
        'reportlab',
        'reportlab.pdfgen.canvas',
        'reportlab.lib.pagesizes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'pandas', 'matplotlib', 'scipy',
        'IPython', 'jupyter', 'notebook',
    ],
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
    name='PrintWatcher',
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
    icon='assets/printwatcher.ico',
    version_file=None,
)
