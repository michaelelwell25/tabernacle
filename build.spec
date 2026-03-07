# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Tabernacle.

Can be used directly:  pyinstaller build.spec
Or via the helper:     python build.py
"""
import os

block_cipher = None

a = Analysis(
    ['tabernacle.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/templates', 'app/templates'),
        ('app/static', 'app/static'),
    ],
    hiddenimports=[
        'flask',
        'flask_sqlalchemy',
        'flask_migrate',
        'flask_wtf',
        'sqlalchemy',
        'sqlalchemy.sql.default_comparator',
        'pulp',
        'pandas',
        'dotenv',
        'flaskwebgui',
        'wtforms',
        'wtforms.fields',
        'wtforms.validators',
        'jinja2',
        'markupsafe',
        'werkzeug',
        'click',
        'email_validator',
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
    [],
    exclude_binaries=True,
    name='Tabernacle',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Tabernacle',
)
