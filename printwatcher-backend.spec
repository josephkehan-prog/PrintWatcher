# PyInstaller spec for the headless Python backend that the WinUI 3 shell
# launches as a child process.
#
# Build:
#   pip install pyinstaller watchdog pystray pillow fastapi "uvicorn[standard]" \
#       pydantic python-multipart pypdf reportlab pypdfium2
#   pyinstaller printwatcher-backend.spec --noconfirm
#
# Output: dist/PrintWatcher-backend.exe
# No console window, no tray. Bind 127.0.0.1:<ephemeral> and write the port
# to %LOCALAPPDATA%/PrintWatcher/server.json so the shell can connect.

block_cipher = None

a = Analysis(
    ['printwatcher/server/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/printwatcher.ico', 'assets'),
        ('assets/printwatcher.png', 'assets'),
    ],
    hiddenimports=[
        'fastapi',
        'fastapi.security',
        'pydantic',
        'pydantic_core',
        'starlette.routing',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        'multipart',
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
        # Backend binary is headless — keep CTk + Tk out so the bundle stays small.
        'customtkinter',
        'tkinter',
        '_tkinter',
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
    name='PrintWatcher-backend',
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
