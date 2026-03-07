"""
Build script for Tabernacle.

Generates a single-folder PyInstaller distribution.
Run:  python build.py
Output lands in dist/Tabernacle/
"""
import subprocess
import sys

HIDDEN_IMPORTS = [
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
]

DATA_FILES = [
    ('app/templates', 'app/templates'),
    ('app/static', 'app/static'),
]

def build():
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--name', 'Tabernacle',
        '--onedir',
        '--windowed',
    ]

    for mod in HIDDEN_IMPORTS:
        cmd += ['--hidden-import', mod]

    for src, dst in DATA_FILES:
        cmd += ['--add-data', f'{src}{os.pathsep}{dst}']

    cmd.append('tabernacle.py')

    print('Running:', ' '.join(cmd))
    subprocess.run(cmd, check=True)
    print('\nBuild complete. Output: dist/Tabernacle/')

if __name__ == '__main__':
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    build()
