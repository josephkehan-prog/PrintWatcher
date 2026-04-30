# PyInstaller spec for the console CLI binary.
#
# Bundles every companion in scripts/ as a hidden import. The unified
# launcher in printwatcher_app.py uses importlib to dispatch by name,
# which PyInstaller's static analyser can't follow — hence the explicit
# list below.
#
# Output:
#   dist/PrintWatcher-cli.exe   console binary; subcommand-driven

block_cipher = None

HIDDEN_SCRIPTS = [
    'scripts',
    'scripts.pdf_inspect',
    'scripts.pdf_merge',
    'scripts.pdf_compress',
    'scripts.pdf_split',
    'scripts.pdf_watermark',
    'scripts.redact',
    'scripts.name_stamper',
    'scripts.roster_split',
    'scripts.roster',
    'scripts.verify_environment',
    'scripts.dedupe_inbox',
    'scripts.cleanup_printed',
    'scripts.clear_queue',
    'scripts.setup_inbox_presets',
    'scripts.printer_test',
    'scripts.schedule_print',
    'scripts.auto_merge',
    'scripts.email_to_inbox',
    'scripts.screenshot_to_print',
    'scripts.weekly_report',
    'scripts.history_search',
    'scripts.web_to_pdf',
    'scripts.preview_shortcut_path',
]

a = Analysis(
    ['printwatcher_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/printwatcher.ico', 'assets'),
        ('assets/printwatcher.png', 'assets'),
        # Bundled so each helper's discover_inbox() finds the
        # YOUR_USERNAME placeholder and falls back to %OneDrive%/PrintInbox.
        ('print_watcher_tray.py', '.'),
        ('print_watcher.py', '.'),
    ],
    hiddenimports=[
        'pystray._win32',
        'PIL._tkinter_finder',
        'pypdf',
        'pypdfium2',
        'reportlab',
        'reportlab.pdfgen.canvas',
        'reportlab.lib.pagesizes',
    ] + HIDDEN_SCRIPTS,
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
    name='PrintWatcher-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/printwatcher.ico',
    version_file=None,
)
