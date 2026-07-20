# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('image', 'image'),
        ('data/source/kbo_2025_final_roster.csv', 'data/source'),
        ('data/source/kbo_2025_final_first_team.csv', 'data/source'),
        ('data/source/kbo_2025_hitter_abilities.csv', 'data/source'),
        ('data/source/kbo_2025_first_team_hitting.csv', 'data/source'),
        ('data/source/kbo_2025_first_team_pitching.csv', 'data/source'),
        ('data/config/club_governance_profiles.json', 'data/config'),
    ],
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
    a.binaries,
    a.datas,
    [],
    name='main',
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
)
