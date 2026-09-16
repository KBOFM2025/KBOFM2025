"""팀·개인 훈련과 코치 선임/배정을 처리하는 결정론적 서비스."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from app.config.coach_rosters_2025 import real_coaching_staff_2025
from app.services.training_planner import sessions_for_day
from database.league_simulation_repository import LeagueSimulationRepository


TEAM_FOCUSES = ("균형", "체력", "타격", "투수", "수비", "주루", "회복")
REST_POLICIES = ("회복 우선", "보통", "강행")
HITTER_FOCUSES = ("자동", "컨택", "장타", "선구안", "수비", "주루", "체력", "회복")
PITCHER_FOCUSES = ("자동", "구속", "구위", "제구", "변화구", "체력", "회복")
COACH_ROLES = (
    "수석코치", "타격코치", "투수코치", "수비코치", "주루코치",
    "배터리코치", "피지컬코치", "육성코치",
)
TRAINING_SLOTS = ("오전", "오후", "추가")
TRAINING_UNITS = ("투수조", "포수조", "내야수조", "외야수조")
SESSION_TYPES = (
    "휴식", "회복", "체력", "타격 기술", "장타 훈련", "주루",
    "내야 수비", "외야 수비", "포수 수비", "투수 불펜",
    "투수 제구", "변화구", "라이브 BP", "팀 전술", "자율 훈련",
)
SESSION_EFFECTS = {
    "휴식": (0, -3, 3, -3, "전체"),
    "회복": (1, -2, 2, -2, "전체"),
    "체력": (2, 2, 0, 1, "전체"),
    "타격 기술": (3, 1, 0, 0, "야수"),
    "장타 훈련": (3, 2, 0, 1, "야수"),
    "주루": (2, 1, 0, 0, "야수"),
    "내야 수비": (3, 1, 0, 0, "내야수조"),
    "외야 수비": (3, 1, 0, 0, "외야수조"),
    "포수 수비": (3, 1, 0, 0, "포수조"),
    "투수 불펜": (3, 2, 0, 1, "투수조"),
    "투수 제구": (3, 1, 0, 0, "투수조"),
    "변화구": (3, 2, 0, 1, "투수조"),
    "라이브 BP": (2, 2, 0, 1, "전체"),
    "팀 전술": (2, 1, 0, 0, "전체"),
    "자율 훈련": (1, 0, 0, 0, "전체"),
}

DEFAULT_WEEK_TEMPLATE = (
    ("회복", "팀 전술", "자율 훈련"),
    ("체력", "타격 기술", "투수 불펜"),
    ("내야 수비", "외야 수비", "포수 수비"),
    ("체력", "투수 제구", "장타 훈련"),
    ("라이브 BP", "주루", "자율 훈련"),
    ("타격 기술", "변화구", "팀 전술"),
    ("휴식", "회복", "휴식"),
)
SESSION_FOCUSES = {
    "체력": "체력", "타격 기술": "컨택", "장타 훈련": "장타", "주루": "주루",
    "내야 수비": "수비", "외야 수비": "수비", "포수 수비": "수비",
    "투수 불펜": "구위", "투수 제구": "제구", "변화구": "변화구",
    "팀 전술": "전술",
}

FOCUS_SPECIALTY = {
    "컨택": "타격", "장타": "타격", "선구안": "타격",
    "구속": "투수", "구위": "투수", "제구": "투수", "변화구": "투수",
    "수비": "수비", "주루": "주루", "체력": "피지컬", "회복": "피지컬",
}
COACH_FOCUS_RATING = {
    "컨택": "batting", "장타": "batting", "선구안": "batting",
    "구속": "pitching", "구위": "pitching", "제구": "pitching", "변화구": "pitching",
    "수비": "defense", "주루": "baserunning", "체력": "fitness", "회복": "fitness",
    "타격": "batting", "투수": "pitching", "균형": "tactical",
}
COACH_DEPARTMENTS = ("타격", "투수", "수비", "주루", "체력", "포수", "전술", "육성")
COACH_FOCUS_RATING.update({"포수": "catching", "전술": "tactical", "육성": "youth_development", "총괄": "tactical"})


def coaching_quality(coach, focus, workload):
    """게임 자체의 1~20 지도 품질. UI와 일일 훈련에서 같은 계산을 사용한다."""
    field = COACH_FOCUS_RATING.get(focus, "development")
    skill = (float(coach[field]) * 0.65 + float(coach["motivation"]) * 0.2
             + float(coach["discipline"]) * 0.15)
    return max(1.0, min(20.0, skill / (1 + max(0, workload - 1) * 0.25)))
HITTER_ATTRIBUTES = {
    "컨택": ("contact", "bat_control", "timing"),
    "장타": ("power",),
    "선구안": ("plate_discipline",),
    "수비": ("fielding_range", "catching", "throwing_accuracy", "fielding_judgment"),
    "주루": ("speed", "baserunning_judgment"),
    "체력": (),  # 야수 체력 세션은 컨디션·피로에 반영. 침착성으로 잘못 전환하지 않는다.
}
PITCHER_ATTRIBUTES = {
    "구속": ("pitcher_velocity",),
    "구위": ("pitcher_stuff", "pitcher_strikeout"),
    "제구": ("pitcher_command", "pitcher_walk_control"),
    "변화구": ("pitcher_movement", "pitcher_pitchability"),
    "체력": ("pitcher_stamina",),
}


def _stable_number(*parts, modulo):
    raw = ":".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") % modulo


class TrainingService:
    """감독이 설정한 훈련 계획을 저장하고 일일 성장 효과로 변환한다."""

    GAME_CANDIDATES = (
        ("김기태", "감독·타격코치"),
        ("류지현", "수석·수비코치"),
        ("이동욱", "감독·수비코치"),
        ("허문회", "감독·타격코치"),
        ("김한수", "수석·타격코치"),
        ("박흥식", "타격코치"),
        ("강석천", "수비코치"),
        ("마정길", "투수코치"),
    )

    def __init__(self, saves_db_path, player_db_path, save_id, team):
        self.saves_db_path = str(saves_db_path)
        self.player_db_path = str(player_db_path)
        self.save_id = int(save_id)
        self.team = str(team)
        LeagueSimulationRepository(self.saves_db_path, self.player_db_path)
        self._seed_staff()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _seed_staff(self):
        game_date = self._game_date()
        today = game_date.isoformat()
        with self._connect() as connection:
            # Old generated candidates are no longer offered.  Hired legacy
            # coaches remain in existing saves so assignments are never broken.
            connection.execute(
                """
                DELETE FROM coaching_staff
                WHERE save_id=? AND is_real=0 AND status='candidate'
                  AND source_url=''
                """,
                (self.save_id,),
            )
            # The human manager owns the managed club's first-team manager
            # position.  Real-life managers remain only for the nine AI clubs.
            managed_manager_ids = connection.execute(
                """
                SELECT id FROM coaching_staff
                WHERE save_id=? AND team=? AND squad='1군'
                  AND role LIKE '%감독%' AND is_real=1
                """,
                (self.save_id, self.team),
            ).fetchall()
            for manager_row in managed_manager_ids:
                manager_id = int(manager_row["id"])
                connection.execute(
                    "DELETE FROM coach_assignments WHERE save_id=? AND coach_id=?",
                    (self.save_id, manager_id),
                )
                connection.execute(
                    """
                    UPDATE individual_training_plans SET coach_id=NULL
                    WHERE save_id=? AND coach_id=?
                    """,
                    (self.save_id, manager_id),
                )
            connection.execute(
                """
                DELETE FROM coaching_staff
                WHERE save_id=? AND team=? AND squad='1군'
                  AND role LIKE '%감독%' AND is_real=1
                """,
                (self.save_id, self.team),
            )
            for staff in real_coaching_staff_2025():
                if (
                    staff["team"] == self.team
                    and staff["squad"] == "1군"
                    and "감독" in staff["role"]
                ):
                    continue
                profile = self._coach_profile(staff)
                self._upsert_staff(
                    connection,
                    {
                        **staff,
                        **profile,
                        "status": "hired",
                        "hired_at": today,
                        "contract_end": "2025-12-31",
                        "is_real": 1,
                    },
                )
            for name, role in self.GAME_CANDIDATES:
                staff = {
                    "team": "", "squad": "영입 후보", "name": name, "role": role,
                    "source_label": "실제 지도자 경력 기반 게임 영입 후보",
                    "source_url": "https://www.koreabaseball.com/Player/RegisterAll.aspx",
                    "source_as_of": "2025-11-01",
                }
                already_hired = connection.execute(
                    """
                    SELECT 1 FROM coaching_staff
                    WHERE save_id=? AND name=? AND status='hired'
                      AND source_label='실제 지도자 경력 기반 게임 영입 후보'
                    """,
                    (self.save_id, name),
                ).fetchone()
                if already_hired:
                    continue
                self._upsert_staff(
                    connection,
                    {
                        **staff,
                        **self._coach_profile(staff),
                        "status": "candidate", "hired_at": "", "contract_end": "",
                        "is_real": 1,
                    },
                )

    @staticmethod
    def _specialty_for(role):
        role = str(role)
        if "타격" in role:
            return "타격"
        if "투수" in role or "불펜" in role:
            return "투수"
        if "배터리" in role or "포수" in role:
            return "포수"
        if "수비" in role:
            return "수비"
        if "주루" in role or "작전" in role or "1루" in role or "3루" in role:
            return "주루"
        if any(word in role for word in ("트레이닝", "컨디셔닝", "재활", "퍼포먼스")):
            return "피지컬"
        if any(word in role for word in ("감독", "수석", "총괄", "QC", "벤치", "코디네이터")):
            return "종합"
        return "육성"

    @classmethod
    def _coach_profile(cls, staff):
        """Produce transparent FM-style estimates, never copied FM database values."""
        role = str(staff["role"])
        squad = str(staff["squad"])
        specialty = cls._specialty_for(role)
        seed = _stable_number(staff.get("team", ""), staff["name"], role, modulo=997)
        squad_base = 13 if squad == "1군" else 11 if "퓨처스" in squad else 10
        if squad in ("전 구단", "영입 후보"):
            squad_base = 13
        leadership = 2 if "감독" in role else 1 if any(
            word in role for word in ("수석", "총괄", "QC", "코디네이터", "벤치")
        ) else 0
        values = {
            "batting": squad_base - 3 + seed % 3,
            "pitching": squad_base - 3 + (seed // 3) % 3,
            "defense": squad_base - 3 + (seed // 7) % 3,
            "baserunning": squad_base - 3 + (seed // 11) % 3,
            "catching": squad_base - 3 + (seed // 13) % 3,
        }
        primary = {
            "타격": "batting", "투수": "pitching", "수비": "defense",
            "주루": "baserunning", "포수": "catching",
        }.get(specialty)
        if primary:
            values[primary] += 4
        elif specialty == "종합":
            values = {key: value + 1 for key, value in values.items()}
        values = {key: max(1, min(20, value)) for key, value in values.items()}
        experience = min(30, 7 + seed % 14 + leadership * 4)
        mental = min(20, squad_base + leadership + (seed // 17) % 3)
        motivation = min(20, squad_base + leadership + (seed // 19) % 4)
        discipline = min(20, squad_base + leadership + (seed // 23) % 4)
        man_management = min(20, squad_base + leadership * 2 + (seed // 29) % 3)
        adaptability = min(20, squad_base - 1 + (seed // 31) % 5)
        youth = min(20, squad_base + (2 if squad != "1군" else 0) + (seed // 37) % 3)
        analysis = min(20, squad_base + (2 if any(x in role for x in ("QC", "분석")) else 0)
                       + (seed // 41) % 3)
        fitness = min(20, squad_base + (4 if specialty == "피지컬" else 0) + seed % 2)
        development = youth
        tactical = round((mental + analysis + man_management) / 3)
        reputation = min(20, squad_base + leadership + experience // 8)
        average = (
            sum(values.values()) + mental + motivation + discipline + man_management
            + adaptability + youth + analysis
        ) / 12
        current_ability = min(200, max(55, round(average * 10)))
        potential_ability = min(200, current_ability + 5 + seed % 16)
        personalities = ("신중함", "단호함", "원칙주의", "친화적", "야심가", "침착함")
        styles = ("균형형", "기술 지도형", "소통형", "강한 규율형", "데이터 활용형")
        return {
            "specialty": specialty,
            "development": development,
            "fitness": fitness,
            "tactical": tactical,
            "reputation": reputation,
            "salary_10k": max(3_500, current_ability * 65 + leadership * 1_200),
            **values,
            "mental": mental,
            "motivation": motivation,
            "discipline": discipline,
            "man_management": man_management,
            "adaptability": adaptability,
            "youth_development": youth,
            "data_analysis": analysis,
            "current_ability": current_ability,
            "potential_ability": potential_ability,
            "personality": personalities[seed % len(personalities)],
            "coaching_style": styles[(seed // 5) % len(styles)],
            "qualification": "KBO 지도자",
            "experience_years": experience,
        }

    def _upsert_staff(self, connection, staff):
        columns = (
            "save_id", "team", "name", "role", "specialty", "development", "fitness",
            "tactical", "reputation", "salary_10k", "status", "hired_at", "contract_end",
            "squad", "batting", "pitching", "defense", "baserunning", "catching", "mental",
            "motivation", "discipline", "man_management", "adaptability", "youth_development",
            "data_analysis", "current_ability", "potential_ability", "personality",
            "coaching_style", "qualification", "experience_years", "source_url", "source_label",
            "source_as_of", "is_real",
        )
        values = [self.save_id] + [staff[column] for column in columns[1:]]
        update_columns = [column for column in columns[3:] if column not in ("status", "hired_at")]
        assignments = ",".join(f"{column}=excluded.{column}" for column in update_columns)
        connection.execute(
            f"""
            INSERT INTO coaching_staff ({','.join(columns)})
            VALUES ({','.join('?' for _ in columns)})
            ON CONFLICT(save_id,team,name) DO UPDATE SET {assignments}
            """,
            values,
        )

    def _game_date(self):
        try:
            with self._connect() as connection:
                row = connection.execute(
                    'SELECT "current_date" FROM game_saves WHERE id=?',
                    (self.save_id,),
                ).fetchone()
            if row and row["current_date"]:
                return date.fromisoformat(str(row["current_date"]))
        except (sqlite3.OperationalError, ValueError):
            pass
        return date(2025, 11, 1)

    def team_setting(self):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM team_training_settings WHERE save_id=? AND team=?",
                (self.save_id, self.team),
            ).fetchone()
        return dict(row) if row else {
            "save_id": self.save_id, "team": self.team, "focus": "균형",
            "intensity": 3, "rest_policy": "보통", "updated_at": "",
        }

    def set_team_setting(self, focus, intensity, rest_policy):
        if focus not in TEAM_FOCUSES:
            raise ValueError("지원하지 않는 팀 훈련 중점입니다.")
        if rest_policy not in REST_POLICIES:
            raise ValueError("지원하지 않는 휴식 정책입니다.")
        intensity = max(1, min(5, int(intensity)))
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO team_training_settings
                    (save_id,team,focus,intensity,rest_policy,updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(save_id,team) DO UPDATE SET
                    focus=excluded.focus,intensity=excluded.intensity,
                    rest_policy=excluded.rest_policy,updated_at=excluded.updated_at
                """,
                (self.save_id, self.team, focus, intensity, rest_policy, now),
            )
        return self.team_setting()

    @staticmethod
    def _week_start(day):
        if isinstance(day, str):
            day = date.fromisoformat(day)
        return day - timedelta(days=day.weekday())

    def weekly_schedule(self, week_start=None):
        """FM식 7일×3세션 훈련표를 불러오고 비어 있으면 기본안을 만든다."""
        start = self._week_start(week_start or self._game_date())
        end = start + timedelta(days=6)
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT COUNT(*) FROM weekly_training_sessions
                WHERE save_id=? AND team=? AND session_date BETWEEN ? AND ?
                """,
                (self.save_id, self.team, start.isoformat(), end.isoformat()),
            ).fetchone()[0]
            if existing < 21:
                for day_index in range(7):
                    sessions = sessions_for_day(self.team, start + timedelta(days=day_index))
                    session_date = (start + timedelta(days=day_index)).isoformat()
                    for slot, session_type in zip(TRAINING_SLOTS, sessions):
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO weekly_training_sessions
                                (save_id,team,session_date,slot,session_type,updated_at)
                            VALUES (?,?,?,?,?,?)
                            """,
                            (
                                self.save_id, self.team, session_date, slot,
                                session_type, "",
                            ),
                        )
            rows = connection.execute(
                """
                SELECT * FROM weekly_training_sessions
                WHERE save_id=? AND team=? AND session_date BETWEEN ? AND ?
                ORDER BY session_date,
                    CASE slot WHEN '오전' THEN 1 WHEN '오후' THEN 2 ELSE 3 END
                """,
                (self.save_id, self.team, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_weekly_schedule(self, sessions, week_start=None):
        start = self._week_start(week_start or self._game_date())
        allowed_dates = {
            (start + timedelta(days=offset)).isoformat() for offset in range(7)
        }
        normalized = []
        for item in sessions:
            session_date = str(item.get("session_date") or "")
            slot = str(item.get("slot") or "")
            session_type = str(item.get("session_type") or "")
            if session_date not in allowed_dates:
                raise ValueError("선택한 주간 범위를 벗어난 훈련 날짜입니다.")
            if slot not in TRAINING_SLOTS or session_type not in SESSION_TYPES:
                raise ValueError("지원하지 않는 훈련 세션입니다.")
            normalized.append((session_date, slot, session_type))
        if len(normalized) != 21 or len({row[:2] for row in normalized}) != 21:
            raise ValueError("7일간 오전·오후·추가 훈련 21개를 모두 편성해야 합니다.")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as connection:
            for session_date, slot, session_type in normalized:
                connection.execute(
                    """
                    INSERT INTO weekly_training_sessions
                        (save_id,team,session_date,slot,session_type,updated_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(save_id,team,session_date,slot) DO UPDATE SET
                        session_type=excluded.session_type,
                        updated_at=excluded.updated_at
                    """,
                    (
                        self.save_id, self.team, session_date, slot,
                        session_type, now,
                    ),
                )
        return self.weekly_schedule(start)

    @staticmethod
    def default_unit_for(player):
        position = str(player.get("position_group") or player.get("pos") or "")
        pos = str(player.get("pos") or "")
        if position == "P":
            return "투수조"
        if position == "C" or pos == "C":
            return "포수조"
        if position == "OF" or pos in {"LF", "CF", "RF"}:
            return "외야수조"
        return "내야수조"

    def set_training_unit(self, player_id, unit_name):
        if unit_name not in TRAINING_UNITS:
            raise ValueError("지원하지 않는 훈련 유닛입니다.")
        player = next(
            (item for item in self.players() if int(item["id"]) == int(player_id)),
            None,
        )
        if not player:
            raise ValueError("우리 구단 선수를 찾을 수 없습니다.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO player_training_units
                    (save_id,player_id,team,unit_name,updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(save_id,player_id) DO UPDATE SET
                    team=excluded.team,unit_name=excluded.unit_name,
                    updated_at=excluded.updated_at
                """,
                (
                    self.save_id, int(player_id), self.team, unit_name,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def players(self):
        from app.services.training_ratings import recent_ratings
        player_connection = sqlite3.connect(self.player_db_path)
        try:
            player_connection.row_factory = sqlite3.Row
            players = [dict(row) for row in player_connection.execute(
                "SELECT * FROM players WHERE team=? ORDER BY status DESC, position_group, name",
                (self.team,),
            )]
        finally:
            player_connection.close()
        with self._connect() as connection:
            ratings = recent_ratings(connection, self.save_id, self.team, self._game_date())
            plans = {
                int(row["player_id"]): dict(row) for row in connection.execute(
                    "SELECT * FROM individual_training_plans WHERE save_id=? AND team=?",
                    (self.save_id, self.team),
                )
            }
            states = {
                int(row["player_id"]): dict(row) for row in connection.execute(
                    "SELECT * FROM player_simulation_states WHERE save_id=? AND team=?",
                    (self.save_id, self.team),
                )
            }
            units = {
                int(row["player_id"]): str(row["unit_name"])
                for row in connection.execute(
                    "SELECT * FROM player_training_units WHERE save_id=? AND team=?",
                    (self.save_id, self.team),
                )
            }
        result = []
        for player in players:
            player_id = int(player["id"])
            is_pitcher = (player.get("position_group") or player.get("pos")) == "P"
            result.append({
                **player,
                'training_rating': ratings.get(player_id, {}),
                "training_focus": plans.get(player_id, {}).get("focus", "자동"),
                "training_intensity": int(plans.get(player_id, {}).get("intensity", 2)),
                "coach_id": plans.get(player_id, {}).get("coach_id"),
                "training_unit": units.get(player_id) or self.default_unit_for(player),
                "training_points": int(states.get(player_id, {}).get("training_points", 0)),
                "condition": int(states.get(player_id, {}).get("condition", 85)),
                "fatigue": int(states.get(player_id, {}).get("fatigue", 0)),
                "focus_options": PITCHER_FOCUSES if is_pitcher else HITTER_FOCUSES,
            })
        return result

    def set_individual_plan(self, player_id, focus, intensity=2, coach_id=None):
        player = next((item for item in self.players() if int(item["id"]) == int(player_id)), None)
        if not player:
            raise ValueError("우리 구단 선수를 찾을 수 없습니다.")
        if focus not in player["focus_options"]:
            raise ValueError("해당 선수 유형에 맞지 않는 개인 훈련입니다.")
        intensity = max(1, min(3, int(intensity)))
        if coach_id:
            coach = self.coach(int(coach_id))
            if not coach or coach["status"] != "hired" or coach["team"] != self.team:
                raise ValueError("우리 구단에 선임된 코치만 배정할 수 있습니다.")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as connection:
            previous = connection.execute(
                "SELECT coach_id FROM individual_training_plans WHERE save_id=? AND player_id=?",
                (self.save_id, int(player_id)),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO individual_training_plans
                    (save_id,player_id,team,focus,intensity,coach_id,active,updated_at)
                VALUES (?,?,?,?,?,?,1,?)
                ON CONFLICT(save_id,player_id) DO UPDATE SET
                    team=excluded.team,focus=excluded.focus,intensity=excluded.intensity,
                    coach_id=excluded.coach_id,active=1,updated_at=excluded.updated_at
                """,
                (self.save_id, int(player_id), self.team, focus, intensity, coach_id, now),
            )
            if previous and previous["coach_id"] and previous["coach_id"] != coach_id:
                connection.execute(
                    """
                    DELETE FROM coach_assignments
                    WHERE save_id=? AND coach_id=? AND assignment_type='player' AND target_id=?
                    """,
                    (self.save_id, int(previous["coach_id"]), int(player_id)),
                )
            if coach_id:
                workload = connection.execute(
                    """
                    SELECT COALESCE(SUM(workload),0) FROM coach_assignments
                    WHERE save_id=? AND coach_id=?
                      AND NOT (assignment_type='player' AND target_id=?)
                    """,
                    (self.save_id, int(coach_id), int(player_id)),
                ).fetchone()[0]
                connection.execute(
                    """
                    INSERT INTO coach_assignments
                        (save_id,coach_id,team,assignment_type,target_id,focus,workload,updated_at)
                    VALUES (?,?,?,?,?,?,1,?)
                    ON CONFLICT(save_id,coach_id,assignment_type,target_id) DO UPDATE SET
                        focus=excluded.focus,updated_at=excluded.updated_at
                    """,
                    (self.save_id, int(coach_id), self.team, "player", int(player_id), focus, now),
                )

    def coaches(self, status=None):
        query = "SELECT * FROM coaching_staff WHERE save_id=?"
        params = [self.save_id]
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY CASE status WHEN 'hired' THEN 0 ELSE 1 END, reputation DESC, name"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params)]

    def coach(self, coach_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM coaching_staff WHERE save_id=? AND id=?",
                (self.save_id, int(coach_id)),
            ).fetchone()
        return dict(row) if row else None

    def hire_coach(self, coach_id, role=None, years=2):
        coach = self.coach(coach_id)
        if not coach or coach["status"] != "candidate":
            raise ValueError("현재 선임 가능한 코치가 아닙니다.")
        if len([item for item in self.coaches("hired") if item["team"] == self.team]) >= 40:
            raise ValueError("1군·퓨처스·육성군을 포함한 코칭스태프 정원 40명을 모두 채웠습니다.")
        role = str(role or coach["role"])
        if role not in COACH_ROLES:
            raise ValueError("지원하지 않는 코치 보직입니다.")
        years = max(1, min(5, int(years)))
        today = self._game_date()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE coaching_staff SET team=?,role=?,status='hired',hired_at=?,contract_end=?
                WHERE save_id=? AND id=? AND status='candidate'
                """,
                (self.team, role, today.isoformat(), f"{today.year + years}-12-31",
                 self.save_id, int(coach_id)),
            )
        hired = self.coach(coach_id)
        if hired is None:
            raise RuntimeError("코치 선임 결과를 저장하지 못했습니다.")
        return hired

    def assign_coach(self, coach_id, assignment_type, target_id=0, focus="균형"):
        coach = self.coach(coach_id)
        if not coach or coach["status"] != "hired" or coach["team"] != self.team:
            raise ValueError("우리 구단에 선임된 코치만 배정할 수 있습니다.")
        if assignment_type not in {"team", "unit", "player"}:
            raise ValueError("지원하지 않는 코치 배정 유형입니다.")
        if assignment_type == "team":
            if focus not in (*COACH_DEPARTMENTS, *TEAM_FOCUSES):
                raise ValueError("지원하지 않는 훈련 분야입니다.")
            target_id = COACH_DEPARTMENTS.index(focus) + 1 if focus in COACH_DEPARTMENTS else 0
        if assignment_type == "unit" and int(target_id) not in range(1, len(TRAINING_UNITS) + 1):
            raise ValueError("훈련 유닛을 선택하세요.")
        with self._connect() as connection:
            workload = connection.execute(
                """
                SELECT COALESCE(SUM(workload),0) FROM coach_assignments
                WHERE save_id=? AND coach_id=?
                  AND NOT (assignment_type=? AND target_id=?)
                """,
                (self.save_id, int(coach_id), assignment_type, int(target_id)),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO coach_assignments
                    (save_id,coach_id,team,assignment_type,target_id,focus,workload,updated_at)
                VALUES (?,?,?,?,?,?,1,?)
                ON CONFLICT(save_id,coach_id,assignment_type,target_id) DO UPDATE SET
                    focus=excluded.focus,updated_at=excluded.updated_at
                """,
                (self.save_id, int(coach_id), self.team, assignment_type,
                 int(target_id), str(focus), datetime.now().isoformat(timespec="seconds")),
            )

    def assignments(self):
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                """
                SELECT a.*, c.name AS coach_name, c.role, c.specialty
                FROM coach_assignments a JOIN coaching_staff c ON c.id=a.coach_id
                WHERE a.save_id=? AND a.team=? ORDER BY c.role,c.name
                """,
                (self.save_id, self.team),
            )]

    def save_coaching_structure(self, duties, head_coach_id=None):
        """훈련 담당 분야와 총괄 책임자를 한 트랜잭션으로 저장한다."""
        hired = {int(c["id"]): c for c in self.coaches("hired") if c["team"] == self.team}
        normalized = {int(key): set(values) for key, values in duties.items()}
        if any(key not in hired or not values <= set(COACH_DEPARTMENTS)
               for key, values in normalized.items()):
            raise ValueError("우리 코칭스태프와 지원하는 훈련 분야만 배정할 수 있습니다.")
        if head_coach_id is not None:
            head_coach_id = int(head_coach_id)
            if head_coach_id not in hired or "수석" not in hired[head_coach_id]["role"]:
                raise ValueError("훈련 총괄은 우리 구단 수석 코치를 선택하세요.")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM coach_assignments WHERE save_id=? AND team=? AND assignment_type IN ('team','responsibility')",
                (self.save_id, self.team),
            )
            for coach_id, focuses in normalized.items():
                for focus in sorted(focuses):
                    connection.execute(
                        "INSERT INTO coach_assignments VALUES (?,?,?,?,?,?,1,?)",
                        (self.save_id, coach_id, self.team, "team",
                         COACH_DEPARTMENTS.index(focus) + 1, focus, now),
                    )
            if head_coach_id is not None:
                connection.execute(
                    "INSERT INTO coach_assignments VALUES (?,?,?,?,?,?,1,?)",
                    (self.save_id, head_coach_id, self.team, "responsibility", 0, "총괄", now),
                )

    def recommended_coaching_structure(self):
        coaches = [c for c in self.coaches("hired") if c["team"] == self.team]
        if not coaches:
            raise ValueError("먼저 코칭스태프를 선임하세요.")
        duties = {int(c["id"]): set() for c in coaches}
        for focus in COACH_DEPARTMENTS:
            coach = max(coaches, key=lambda c: coaching_quality(
                c, focus, len(duties[int(c["id"])]) + 1))
            duties[int(coach["id"])].add(focus)
        return duties

    def prepare_head_coach_week(self, week_start=None):
        heads = [a for a in self.assignments() if a["assignment_type"] == "responsibility"]
        if not heads:
            raise ValueError("먼저 수석 코치를 훈련 총괄로 배정하고 저장하세요.")
        players = self.players()
        average_condition = sum(p["condition"] for p in players) / max(1, len(players))
        schedule = self.weekly_schedule(week_start)
        for session in schedule:
            day = date.fromisoformat(session["session_date"])
            slot = TRAINING_SLOTS.index(session["slot"])
            session["session_type"] = sessions_for_day(self.team, day, average_condition)[slot]
            if average_condition < 75 and slot == 2:
                session["session_type"] = "회복"
        return self.set_weekly_schedule(schedule, week_start)

    def management_policy(self):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM training_management WHERE save_id=? AND team=?",
                                     (self.save_id, self.team)).fetchone()
        return dict(row) if row else dict(delegate_team=0, delegate_individual=0)

    def set_management_policy(self, delegate_team, delegate_individual):
        if (delegate_team or delegate_individual) and not any(
            a["assignment_type"] == "responsibility" for a in self.assignments()
        ):
            raise ValueError("훈련 책임 탭에서 수석 코치를 총괄로 배정하고 저장하세요.")
        with self._connect() as connection:
            connection.execute("""INSERT INTO training_management VALUES (?,?,?,?)
                ON CONFLICT(save_id,team) DO UPDATE SET delegate_team=excluded.delegate_team,
                delegate_individual=excluded.delegate_individual""",
                (self.save_id, self.team, int(bool(delegate_team)), int(bool(delegate_individual))))

    def release_training_overrides(self):
        """사용자가 명시적으로 요청한 경우에만 미래 직접 계획을 위임 대상으로 전환."""
        with self._connect() as connection:
            connection.execute("""UPDATE weekly_training_sessions SET updated_at='auto:released'
                WHERE save_id=? AND team=? AND session_date>=?""",
                (self.save_id, self.team, self._game_date().isoformat()))
            connection.execute("""UPDATE individual_training_plans SET updated_at='auto:released'
                WHERE save_id=? AND team=?""", (self.save_id, self.team))

    def delegation_report(self):
        with self._connect() as connection:
            row = connection.execute("""SELECT report_date,summary FROM training_delegation_reports
                WHERE save_id=? AND team=? ORDER BY report_date DESC LIMIT 1""",
                (self.save_id, self.team)).fetchone()
        return f"{row['report_date']} · {row['summary']}" if row else "날짜를 진행하면 수석 코치의 편성 보고가 표시됩니다."

    def development_history(self):
        players = {int(p["id"]): p for p in self.players()}
        with self._connect() as connection:
            rows = connection.execute("""SELECT * FROM player_development_events
                WHERE save_id=? ORDER BY event_date DESC,player_id,attribute""", (self.save_id,)).fetchall()
        return [dict(row, name=players[row["player_id"]]["name"]) for row in rows
                if row["player_id"] in players][:200]

    def coach_workloads(self):
        """배정 수에 따른 코치 업무량과 FM식 5단계 훈련 품질을 계산한다."""
        assignments = self.assignments()
        by_coach = {}
        for assignment in assignments:
            by_coach.setdefault(int(assignment["coach_id"]), []).append(assignment)
        result = []
        for coach in self.coaches("hired"):
            if coach["team"] != self.team:
                continue
            duties = by_coach.get(int(coach["id"]), [])
            workload = sum(int(item.get("workload") or 1) for item in duties)
            quality_score = (sum(coaching_quality(coach, d["focus"], workload) for d in duties)
                             / len(duties)) if duties else 0
            stars = round(quality_score / 4 * 2) / 2
            workload_label = (
                "없음" if workload == 0 else "낮음" if workload == 1
                else "보통" if workload == 2 else "높음" if workload == 3 else "과중"
            )
            result.append({
                **coach,
                "workload": workload,
                "workload_label": workload_label,
                "training_stars": stars,
                "assigned_focuses": [str(item["focus"]) for item in duties],
            })
        return result

    def workflow_progress(self):
        """11월 필수 코치·훈련 업무의 실제 저장 상태를 반환한다."""
        assignments = self.assignments()
        team_focuses = {
            str(item["focus"])
            for item in assignments
            if item["assignment_type"] == "team"
        }
        required_focuses = {"타격", "투수", "수비"}
        setting = self.team_setting()
        with self._connect() as connection:
            individual_count = int(connection.execute(
                """
                SELECT COUNT(*) FROM individual_training_plans
                WHERE save_id=? AND team=? AND active=1 AND focus!='자동'
                """,
                (self.save_id, self.team),
            ).fetchone()[0])
            weekly_session_count = int(connection.execute(
                """
                SELECT COUNT(*) FROM weekly_training_sessions
                WHERE save_id=? AND team=? AND updated_at!=''
                """,
                (self.save_id, self.team),
            ).fetchone()[0])
        missing_focuses = sorted(required_focuses - team_focuses)
        return {
            "staff_ready": not missing_focuses,
            "assigned_focuses": sorted(team_focuses),
            "missing_focuses": missing_focuses,
            "team_plan_ready": bool(setting.get("updated_at")),
            "individual_plan_count": individual_count,
            "individual_plan_required": 3,
            "weekly_session_count": weekly_session_count,
            "weekly_plan_ready": weekly_session_count >= 21,
            "training_ready": (
                bool(setting.get("updated_at"))
                and individual_count >= 3
                and weekly_session_count >= 21
            ),
        }

    @staticmethod
    def daily_effect(
        connection, save_id, player, state, default_intensity,
        simulation_date=None,
    ):
        """열린 시뮬레이션 트랜잭션 안에서 한 선수의 오늘 훈련 효과를 계산한다."""
        team = str(player.get("team") or "")
        setting = connection.execute(
            "SELECT * FROM team_training_settings WHERE save_id=? AND team=?",
            (save_id, team),
        ).fetchone()
        team_focus = str(setting["focus"]) if setting else "균형"
        intensity = int(setting["intensity"]) if setting else int(default_intensity)
        rest_policy = str(setting["rest_policy"]) if setting else "보통"
        unit_row = connection.execute(
            "SELECT unit_name FROM player_training_units WHERE save_id=? AND player_id=?",
            (save_id, int(player["id"])),
        ).fetchone()
        unit_name = (
            str(unit_row["unit_name"])
            if unit_row else TrainingService.default_unit_for(player)
        )
        plan = connection.execute(
            "SELECT * FROM individual_training_plans WHERE save_id=? AND player_id=? AND active=1",
            (save_id, int(player["id"])),
        ).fetchone()
        individual_focus = str(plan["focus"]) if plan else "자동"
        individual_intensity = int(plan["intensity"]) if plan else 2
        coach_bonus = 0
        if plan and plan["coach_id"]:
            coach = connection.execute(
                "SELECT * FROM coaching_staff WHERE save_id=? AND id=? AND status='hired' AND team=?",
                (save_id, int(plan["coach_id"]), team),
            ).fetchone()
            if coach:
                workload = connection.execute(
                    "SELECT COALESCE(SUM(workload),0) FROM coach_assignments WHERE save_id=? AND coach_id=?",
                    (save_id, int(coach["id"])),
                ).fetchone()[0]
                coach_bonus = coaching_quality(coach, individual_focus, workload) / 5
        # 팀·파트 담당 코치도 개인 담당 코치보다 약한 범위에서 전원에게
        # 영향을 준다. 같은 코치가 중복 배정돼도 최고 효과 한 번만 적용한다.
        assigned_coaches = connection.execute(
            """
            SELECT c.*, a.focus,a.assignment_type,a.target_id,
                   (SELECT COALESCE(SUM(w.workload),0) FROM coach_assignments w
                    WHERE w.save_id=a.save_id AND w.coach_id=a.coach_id) AS duty_load
            FROM coach_assignments a
            JOIN coaching_staff c ON c.id=a.coach_id
            WHERE a.save_id=? AND a.team=? AND c.status='hired' AND c.team=a.team
              AND (a.assignment_type IN ('team','unit')
                   OR (a.assignment_type='player' AND a.target_id=?))
            """,
            (save_id, team, int(player["id"])),
        ).fetchall()
        is_pitcher = (player.get("position_group") or player.get("pos")) == "P"
        applied_focus = individual_focus if individual_focus != "자동" else (
            "투수" if is_pitcher and team_focus == "투수"
            else "타격" if not is_pitcher and team_focus == "타격" else "체력"
        )
        for assigned in assigned_coaches:
            if assigned["assignment_type"] == "unit":
                if int(assigned["target_id"]) != TRAINING_UNITS.index(unit_name) + 1:
                    continue
            if assigned["focus"] == "포수" and unit_name != "포수조":
                continue
            if assigned["focus"] not in {"균형", "육성"} and not (
                assigned["focus"] == "포수" and applied_focus == "수비" and unit_name == "포수조"
            ) and (
                COACH_FOCUS_RATING.get(assigned["focus"]) != COACH_FOCUS_RATING.get(applied_focus)
            ):
                continue
            contribution = coaching_quality(assigned, assigned["focus"], assigned["duty_load"]) / 5
            coach_bonus = max(coach_bonus, contribution)
        if int(state.get("injury_days") or 0) > 0 or individual_focus == "회복":
            return {
                "training_gain": 0, "fatigue_load": -2,
                "condition_bonus": 2, "risk_bonus": -3,
                "focus": "회복", "attribute": None,
            }
        rest_adjust = -1 if rest_policy == "회복 우선" else 1 if rest_policy == "강행" else 0
        focus_bonus = 1 if team_focus in {"균형", FOCUS_SPECIALTY.get(individual_focus)} else 0
        session_gain = 0
        session_fatigue = 0
        session_condition = 0
        session_risk = 0
        practiced_focuses = []
        if simulation_date is not None:
            session_day = (
                simulation_date.isoformat()
                if isinstance(simulation_date, date) else str(simulation_date)
            )
            sessions = connection.execute(
                """
                SELECT session_type FROM weekly_training_sessions
                WHERE save_id=? AND team=? AND session_date=?
                """,
                (save_id, team, session_day),
            ).fetchall()
            session_types = [str(session["session_type"]) for session in sessions]
            if not session_types:
                day_value = date.fromisoformat(session_day)
                session_types = list(sessions_for_day(team, day_value))
            for session_type in session_types:
                gain_value, fatigue_value, condition_value, risk_value, target = (
                    SESSION_EFFECTS.get(session_type, (0, 0, 0, 0, "전체"))
                )
                applies = (
                    target == "전체"
                    or target == unit_name
                    or (target == "야수" and unit_name != "투수조")
                )
                if applies:
                    session_gain += gain_value
                    session_fatigue += fatigue_value
                    session_condition += condition_value
                    session_risk += risk_value
                    session_focus = SESSION_FOCUSES.get(session_type)
                    if session_focus:
                        practiced_focuses.append(session_focus)
                        department = "포수" if session_type == "포수 수비" else session_focus
                        quality = max((coaching_quality(c, department, c["duty_load"])
                            for c in assigned_coaches
                            if c["assignment_type"] in {"team", "unit"}
                            and (c["assignment_type"] != "unit" or int(c["target_id"]) == TRAINING_UNITS.index(unit_name) + 1)
                            and COACH_FOCUS_RATING.get(c["focus"]) == COACH_FOCUS_RATING.get(department)
                            and (c["focus"] != "포수" or unit_name == "포수조")), default=0)
                        session_gain += quality / 10
            if session_types:
                session_gain = round(session_gain / len(session_types))
                session_fatigue = round(session_fatigue / 2)
                session_condition = max(-2, min(2, session_condition))
                session_risk = max(-3, min(3, session_risk))
        gain = max(
            0,
            intensity + individual_intensity - 2
            + coach_bonus + focus_bonus + session_gain,
        )
        gain = round(gain)
        if simulation_date is not None and all(s in {"휴식", "회복"} for s in session_types):
            gain = 0
        fatigue_load = max(
            -3,
            intensity - 2 + individual_intensity - 2
            + rest_adjust + session_fatigue,
        )
        if simulation_date is not None and all(s in {"휴식", "회복"} for s in session_types):
            fatigue_load = min(-2, fatigue_load)
        is_pitcher = (player.get("position_group") or player.get("pos")) == "P"
        focus = individual_focus
        if focus == "자동":
            focus = "구위" if is_pitcher and team_focus == "투수" else "컨택" if not is_pitcher and team_focus == "타격" else "체력"
            eligible_focuses = [f for f in practiced_focuses if f in (PITCHER_ATTRIBUTES if is_pitcher else HITTER_ATTRIBUTES)]
            if eligible_focuses:
                focus = eligible_focuses[_stable_number(save_id, player["id"], simulation_date, modulo=len(eligible_focuses))]
        candidates = (PITCHER_ATTRIBUTES if is_pitcher else HITTER_ATTRIBUTES).get(focus, ())
        attribute = candidates[_stable_number(save_id, player["id"], focus, modulo=len(candidates))] if candidates else None
        return {
            "training_gain": gain,
            "fatigue_load": fatigue_load,
            "condition_bonus": (
                1 if rest_policy == "회복 우선" else 0
            ) + session_condition,
            "risk_bonus": (
                -2 if rest_policy == "회복 우선"
                else 2 if rest_policy == "강행" else 0
            ) + session_risk,
            "focus": focus, "attribute": attribute,
            "unit": unit_name,
            "sessions": len(session_types) if simulation_date is not None else 0,
            "focus_aligned": individual_focus == '자동' or individual_focus in practiced_focuses,
            "coaching_support": coach_bonus,
            "rest_day": simulation_date is not None and all(s in {'휴식', '회복'} for s in session_types),
        }

    @staticmethod
    def apply_development_checkpoint(connection, player_id, old_points, gained, attribute):
        """누적 훈련 포인트 60점 경계를 넘으면 목표 능력치를 1 올린다."""
        if not attribute or gained <= 0 or int(old_points) // 60 == (int(old_points) + int(gained)) // 60:
            return False
        connection.execute(
            f"UPDATE playerdb.players SET {attribute}=MIN(20,COALESCE({attribute},0)+1) WHERE id=?",
            (int(player_id),),
        )
        return True
