"""Collect official lifetime evidence once per player/level; never mutate player abilities.

Public HTML is cached for reproducible parsing. Only validated career tables may
attest that a season has no listed record. Overseas careers are not inferred.
"""
import argparse
import csv
import html
import json
import re
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HITTING = 'AVG G PA AB R H 2B 3B HR TB RBI SB CS BB HBP SO GDP SLG OBP E'.split()
PITCHING = 'ERA G CG SHO W L SV HLD WPCT TBF IP H HR BB HBP SO R ER'.split()


def clean(value):
    return ' '.join(html.unescape(re.sub('<[^>]+>', '', value)).split())


def field(page, suffix):
    found = re.search(r'<span[^>]*id="[^"]*' + suffix + r'"[^>]*>(.*?)</span>', page, re.S)
    return clean(found[1]) if found else ''


def entry_year(value, through):
    match = re.match(r'^(\d{2,4})(?=\D|$)', value)
    if not match:
        return None
    year = int(match[1])
    if year < 100:
        year += 2000 if year <= through % 100 else 1900
    return year if 1950 <= year <= through + 1 else None


def innings_outs(value):
    value = value.replace('⅓', ' 1/3').replace('⅔', ' 2/3').strip()
    if value in ('', '-'):
        return 0
    if value in ('1/3', '2/3'):
        return int(value[0])
    match = re.fullmatch(r'(\d+)(?:\s+([12])/3)?', value)
    if not match:
        raise ValueError('Unrecognized innings: ' + value)
    return 3 * int(match[1]) + int(match[2] or 0)


def parse_table(page, role):
    columns = PITCHING if role == 'pitching' else HITTING
    for table in re.findall(r'<table\b.*?</table>', page, re.S | re.I):
        header = re.search(r'<thead\b.*?</thead>', table, re.S | re.I)
        if not header:
            continue
        headings = [clean(c) for c in re.findall(r'<th\b[^>]*>(.*?)</th>', header[0], re.S | re.I)]
        if headings != ['연도', '팀명', *columns]:
            continue
        result = []
        for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table, re.S | re.I):
            cells = [clean(c) for c in re.findall(r'<td\b[^>]*>(.*?)</td>', tr, re.S | re.I)]
            if not cells or not re.fullmatch(r'\d{4}', cells[0]):
                continue
            if len(cells) != len(columns) + 2:
                raise ValueError('Unsupported career row layout')
            row = dict(zip(columns, cells[2:]))
            row.update(season=int(cells[0]), record_team=cells[1])
            if role == 'pitching':
                row['IP_OUTS'] = innings_outs(row['IP'])
                row['IP_DECIMAL'] = round(row['IP_OUTS'] / 3, 6)
            result.append(row)
        # The career total must reconcile with all displayed years, including
        # years beyond the game cutoff. A partial/changed table cannot mean zero.
        footer = re.search(r'<tfoot\b.*?</tfoot>', table, re.S | re.I)
        totals = [clean(c) for c in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', footer[0], re.S | re.I)] if footer else []
        if not result and totals == ['데이터가 존재하지 않습니다']:
            return []
        if not totals or totals[0] != '통산' or len(totals) != len(columns) + 1:
            raise ValueError('Missing career total')
        total_g = totals[1 + columns.index('G')]
        if (total_g in ('-', '') and result) or (total_g not in ('-', '') and int(total_g) != sum(int(r['G']) for r in result)):
            raise ValueError('Career games do not reconcile')
        return result
    raise ValueError('Expected career table not found')


def collect(player, level, through, cache):
    identifier = str(player['kbo_player_id'])
    role = 'pitching' if (player.get('position_group') or player.get('pos')) == 'P' else 'hitting'
    kind = 'Pitcher' if role == 'pitching' else 'Hitter'
    path = f'/Record/Player/{kind}Detail/Total.aspx' if level == 'first_team' else f'/Futures/Player/{kind}Total.aspx'
    url = f'https://www.koreabaseball.com{path}?playerId={identifier}'
    target = cache / f'{identifier}_{level}_{role}.html'
    cutoff = date(through, 11, 1)
    if target.exists() and datetime.fromtimestamp(target.stat().st_mtime).date() >= cutoff:
        page = target.read_text(encoding='utf-8')
    else:
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'KBOFM-career-data/1.0'})
                with urllib.request.urlopen(request, timeout=25) as response:
                    page = response.read().decode('utf-8-sig')
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        target.write_text(page, encoding='utf-8')
    birth = re.findall(r'\d+', field(page, 'lblBirthday'))
    birthday = '-'.join([birth[0], birth[1].zfill(2), birth[2].zfill(2)]) if len(birth) == 3 else ''
    name = field(page, 'lblName')
    if not birthday or not player.get('birth_date') or birthday != player['birth_date'][:10]:
        raise ValueError('Official birthday does not match database identity')
    rows = parse_table(page, role)
    join = field(page, 'lblJoinInfo')
    draft = field(page, 'lblDraft')
    years = [y for y in (entry_year(join, through), entry_year(draft, through)) if y]
    entry = min(years) if years and not player.get('is_foreign') else None
    if entry and rows and entry > min(r['season'] for r in rows):
        entry = None
    metadata = dict(kbo_player_id=identifier, player_name=name, birth_date=birthday,
                    professional_entry_year=entry or '', official_join=join, official_draft=draft,
                    source_url=url, level=level, role=role, verified_through=through)
    for row in rows:
        row.update(kbo_player_id=identifier, player_name=name, level=level, role=role,
                   has_record='1', source_url=url)
    return metadata, [row for row in rows if row['season'] <= through]


def write_csv(path, rows):
    if not rows:
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--through', type=int, default=2025)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    today = date.today()
    completed = today.year if today >= date(today.year, 11, 1) else today.year - 1
    if not 1982 <= args.through <= completed:
        parser.error(f'--through must be a completed season, 1982..{completed}')
    cache = ROOT / 'tmp/potential-career-html'
    cache.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ROOT / 'data/players.db') as connection:
        connection.row_factory = sqlite3.Row
        players = [dict(r) for r in connection.execute('SELECT * FROM players WHERE kbo_player_id IS NOT NULL ORDER BY id')]
    players = list({str(p['kbo_player_id']): p for p in players if str(p['kbo_player_id']).isdigit()}.values())
    if args.limit:
        players = players[:args.limit]
    metadata, records, errors = [], [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(collect, p, level, args.through, cache): (p['kbo_player_id'], level)
                for p in players for level in ('first_team', 'futures')}
        for count, job in enumerate(as_completed(jobs), 1):
            try:
                meta, rows = job.result()
                metadata.append(meta)
                records.extend(rows)
            except Exception as error:
                errors.append(dict(target=jobs[job], error=str(error)))
            if count % 80 == 0 or count == len(jobs):
                print(f'COLLECT {count}/{len(jobs)} verified={len(metadata)} rows={len(records)} errors={len(errors)}', flush=True)
    destination = ROOT / ('tmp' if args.limit else 'data/source')
    write_csv(destination / 'kbo_potential_career_records.csv', sorted(records, key=lambda r: (r['kbo_player_id'], r['level'], r['season'], r['record_team'])))
    write_csv(destination / 'kbo_potential_career_coverage.csv', sorted(metadata, key=lambda r: (r['kbo_player_id'], r['level'])))
    report = dict(players=len(players), pages_verified=len(metadata), records=len(records), errors=errors)
    (ROOT / 'tmp/potential-career-collection-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(report, errors=len(errors))), flush=True)


if __name__ == '__main__':
    main()
