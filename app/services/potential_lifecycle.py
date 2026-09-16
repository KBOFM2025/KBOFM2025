"""입단 1~4년차 재평가 / 5년차 이후 고정, 기록 누락과 무출장 구분."""
import csv
import hashlib
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path


def overseas_history_required(player, verified):
    """KBO tables do not attest to seasons played outside Korea."""
    if player.get('is_foreign'):
        return True
    domestic = {'KIA', '해태', '삼성', '롯데', 'LG', 'MBC', '한화', '빙그레', 'KT', 'kt',
                '두산', 'OB', 'SSG', 'SK', 'NC', '넥센', '키움', '히어로즈', '우리',
                '현대', '태평양', '쌍방울', '삼미', '청보', '상무', '경찰청'}
    join_team = re.sub(r'^\d+\s*', '', verified.get('official_join') or '').strip()
    if join_team and join_team not in domestic:
        return True
    overseas = ('텍사스', '샌프란시스코', '볼티모어', '필라델피아', '세인트루이스',
                '미네소타', 'LA다저스', '토론토', '시카고', '보스턴', '피츠버그',
                '애리조나', '시애틀', '클리블랜드', '탬파베이', '뉴욕', '오클랜드',
                '샌디에이고', 'LA에인절스', '소프트뱅크', '지바롯데', '요미우리',
                '한신', '오릭스', '주니치', '야쿠르트', '라쿠텐', '요코하마')
    return any(team in str(player.get('career') or '') for team in overseas)


@lru_cache(maxsize=1)
def verified_careers():
    path = Path(__file__).resolve().parents[2] / 'data/source/kbo_potential_career_coverage.csv'
    if not path.exists():
        return {}
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return {(row['kbo_player_id'], row['level']): row for row in csv.DictReader(stream)}


@lru_cache(maxsize=1)
def career_index():
    path = Path(__file__).resolve().parents[2] / "data/source/kbo_player_career_history.csv"
    result = {}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    result.setdefault(row["kbo_player_id"], set()).add(int(row["season"]))
                except (ValueError, KeyError):
                    continue
    lifetime = path.with_name('kbo_potential_career_records.csv')
    if lifetime.exists():
        with lifetime.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                result.setdefault(row['kbo_player_id'], set()).add(int(row['season']))
    return result


@lru_cache(maxsize=1)
def coverage_index():
    """has_record=0도 수집 완료다. 파일/행이 없는 것은 무출장으로 처리하지 않는다."""
    root = Path(__file__).resolve().parents[2] / "data/source"
    result = set()
    for path in root.glob("kbo_*_*.csv"):
        parts = path.stem.split("_")
        if len(parts) < 4 or not parts[1].isdigit():
            continue
        level = "first_team" if "_first_team_" in path.stem else "futures" if "_futures_" in path.stem else None
        role = parts[-1]
        if not level or role not in ("hitting", "pitching"):
            continue
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("kbo_player_id") and row.get("has_record") in ("0", "1"):
                    result.add((row["kbo_player_id"], role, int(parts[1]), level))
    return result


def lifecycle_for(player, as_of, history):
    day = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    identifier = str(player.get("kbo_player_id") or "")
    known_years = sorted(y for y in career_index().get(identifier, set()) if y <= day.year)
    explicit = player.get("professional_entry_year") or (player.get("draft_year") if not player.get("is_foreign") else None)
    verified = verified_careers().get((identifier, 'first_team'), {})
    identity_matches = bool(verified and verified.get('birth_date') == str(player.get('birth_date') or '')[:10])
    official_entry = verified.get('professional_entry_year') if identity_matches and not player.get('is_foreign') else None
    if official_entry:
        explicit = official_entry
    try:
        entry = int(explicit) if explicit else None
    except (TypeError, ValueError):
        entry = None
    if entry and (entry < 1900 or entry > day.year + 1):
        entry = None
    reported_entry = entry
    conflict = bool(entry and known_years and entry > known_years[0])
    if conflict:
        entry = None
    # First 1st-team appearance proves a minimum career length, not the professional entry date.
    minimum_years = day.year - known_years[0] + 1 if known_years else None
    career_year = day.year - entry + 1 if entry else None
    eligible = career_year >= 5 if career_year is not None else minimum_years is not None and minimum_years >= 5
    last_completed = day.year - 1 if day < date(day.year, 11, 1) else day.year
    first = entry if entry else known_years[0] if known_years else None
    role = "pitching" if (player.get("position_group") or player.get("pos")) == "P" else "hitting"
    missing = []
    if first is not None:
        for year in range(first, last_completed + 1):
            for level in ("first_team", "futures"):
                page = verified_careers().get((identifier, level), {})
                covered_by_career = (identity_matches and page.get('birth_date') == verified.get('birth_date')
                                     and page.get('role') == role and year <= int(page.get('verified_through') or 0))
                if not covered_by_career and (identifier, role, year, level) not in coverage_index():
                    missing.append(f"{year}:{level}")
    overseas = overseas_history_required(player, verified if identity_matches else {})
    if overseas:
        missing.append('overseas:career')
    complete = entry is not None and not missing and first <= last_completed
    state = "fixed" if eligible and complete else "awaiting_history" if eligible else "developing" if entry else "entry_unknown"
    fingerprint = hashlib.sha256(json.dumps(dict(records=history["records"], missing=missing,
                                                entry=entry, eligible=bool(eligible)), sort_keys=True).encode()).hexdigest()[:20]
    return dict(state=state, career_year=career_year, minimum_career_years=minimum_years,
                entry_year=entry, reported_entry_year=reported_entry, entry_conflict=conflict,
                entry_source="입단·경력 자료 불일치" if conflict else "KBO 공식 입단·지명 정보" if official_entry else "등록 입단/드래프트 연도" if entry else "입단 연도 미확인",
                entry_source_url=verified.get('source_url') if official_entry else None,
                fixed_at=day.isoformat() if state == "fixed" else None,
                evaluated_through=last_completed, missing_records=missing,
                history_complete=complete, evidence_fingerprint=fingerprint,
                overseas_history_required=overseas,
                note="1~4년차 누적 1·2군 성적 재평가, 이후 고정. 입단 연도/전 경력 자료 누락 시 고정 보류.")
