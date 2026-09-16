"""Read-only check of publishable files; never print matched secret values."""
from pathlib import Path
import re
import sqlite3
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    files = set(subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=root, text=True).splitlines())
    pattern = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{32,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
    errors = []
    for name in sorted(files):
        path = root / name
        if not path.is_file():
            continue
        if path.stat().st_size > 95_000_000:
            errors.append('Oversized file: ' + name)
        if name.startswith(('tmp/', 'release/', 'venv/', '.venv/', 'data/saves/', 'data/logs/', 'image/players/local/')) and not name.endswith('.gitkeep'):
            errors.append('Private/generated file: ' + name)
        if path.name.startswith('.env') and path.name != '.env.example' or path.name.startswith('kbo_fm_saves.db'):
            errors.append('Private file: ' + name)
        if path.suffix in ('.py', '.json', '.md', '.yml', '.yaml', '.txt', '.csv', '.ps1', '.bat', '.mjs') and pattern.search(path.read_bytes()):
            errors.append('Possible secret: ' + name)
    with sqlite3.connect((root / 'data/players.db').as_uri() + '?mode=ro', uri=True) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if any('credential' in table or 'save' in table for table in tables):
            errors.append('Unexpected private table in players.db')
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    for error in errors:
        print(error)
    print(f'Checked {len(files)} candidate paths; issues={len(errors)} (pattern scan, not a complete secret audit).')
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
