"""하루 진행을 막지 않고 상대 구단의 중요 의사결정을 Qwen으로 생성한다."""

import json
import sqlite3

from PySide6.QtCore import QThread, Signal

from app.ai.local_model import LocalModelClient, LocalModelError


SYSTEM_PROMPT = """당신은 KBO 구단 운영 시뮬레이션의 상대 구단 단장 AI다.
구단마다 다른 시즌 목표, 프런트 철학, 포지션 뎁스, 선수 능력·나이·연봉,
현재 컨디션과 최근 의사결정을 함께 비교해 실제 단장처럼 판단한다.
이사회 협상 AI와 달리 감독에게 답하지 말고 상대 구단이 실제로 취할 내부 행동만 작성한다.
context에 없는 선수, 기록, 계약 또는 예산을 만들어내지 않는다.
최근 결정을 특별한 사유 없이 즉시 뒤집지 않는다.
action은 실행 주체와 대상이 드러나는 한 문장으로 쓴다.
reason에는 context의 구체적인 선수 또는 포지션 수치와 구단 철학을 모두 포함한다.
expected_effect와 risk는 서로 다른 내용을 쓴다.
반드시 요청된 JSON 형식만 반환한다."""


def _ai_log(message):
    print(f"[상대 구단 Qwen AI] {message}", flush=True)


class TeamAIDecisionWorker(QThread):
    processed = Signal(int)

    def __init__(self, saves_db_path, save_id, parent=None):
        super().__init__(parent)
        self.saves_db_path = str(saves_db_path)
        self.save_id = save_id
        self.client = LocalModelClient(timeout=45)

    def stop(self):
        self.requestInterruption()
        self.client.cancel()

    def defer_processing_rows(self):
        """종료 도중 점유했던 결정을 다음 실행에서 다시 처리할 수 있게 돌려놓는다."""
        with self._connect() as connection:
            connection.execute(
                """UPDATE team_ai_decision_queue SET status='deferred'
                WHERE save_id=? AND status='processing'""",
                (self.save_id,),
            )

    def run(self):
        total = 0
        _ai_log(f"세이브 {self.save_id} 백그라운드 의사결정 처리 시작")
        try:
            self._reactivate_deferred()
            while True:
                if self.isInterruptionRequested():
                    _ai_log("게임 종료 요청으로 추가 작업을 중단합니다")
                    break
                rows = self._claim_batch()
                if not rows:
                    _ai_log("처리할 중요 일정이 없습니다")
                    break
                teams = ", ".join(row["team"] for row in rows)
                _ai_log(f"Qwen 요청 · {len(rows)}건 · {teams}")
                try:
                    result = self.client.generate_json(
                        SYSTEM_PROMPT,
                        {
                            "request_type": "team_daily_batch",
                            "decisions": [
                                {"id": row["id"], "team": row["team"],
                                 "decision_type": row["decision_type"],
                                 "context": json.loads(row["context_json"])}
                                for row in rows
                            ],
                            "output": {
                                "decisions": [{
                                    "id": "integer",
                                    "action": "string",
                                    "reason": "string",
                                    "targets": ["선수명 또는 포지션"],
                                    "expected_effect": "string",
                                    "risk": "string",
                                }]
                            },
                        },
                    )
                    if self.isInterruptionRequested():
                        self._defer_batch(rows, "게임 종료로 AI 요청 중단")
                        _ai_log("게임 종료 요청으로 응답 반영을 취소합니다")
                        break
                    resolved = self._validate_answers(
                        rows, result.get("decisions", [])
                    )
                    self._finish_batch(rows, resolved)
                    total += len(resolved)
                    _ai_log(f"Qwen 응답 저장 완료 · {len(resolved)}/{len(rows)}건")
                except (LocalModelError, ValueError, TypeError, AttributeError, KeyError, json.JSONDecodeError) as error:
                    self._defer_batch(rows, str(error))
                    _ai_log(f"Qwen 처리 보류 · {error}")
                    break
        finally:
            _ai_log(f"백그라운드 처리 종료 · 완료 {total}건")
            self.processed.emit(total)

    def _reactivate_deferred(self):
        """이전 날 서버가 꺼져 있었다면 다음 백그라운드 실행에서 한 번 재시도한다."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE team_ai_decision_queue SET status='ready_for_qwen' WHERE save_id=? AND status='deferred'",
                (self.save_id,),
            )

    def _connect(self):
        connection = sqlite3.connect(self.saves_db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _claim_batch(self):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM team_ai_decision_queue
                WHERE save_id=? AND status='ready_for_qwen'
                ORDER BY decision_date,id LIMIT 5""", (self.save_id,)
            ).fetchall()
            if rows:
                connection.executemany(
                    "UPDATE team_ai_decision_queue SET status='processing' WHERE id=?",
                    [(row["id"],) for row in rows],
                )
            return [dict(row) for row in rows]

    def _finish_batch(self, rows, resolved):
        with self._connect() as connection:
            for row in rows:
                answer = resolved.get(row["id"])
                if answer:
                    connection.execute(
                        "UPDATE team_ai_decision_queue SET status='completed',result_json=? WHERE id=?",
                        (json.dumps(answer, ensure_ascii=False), row["id"]),
                    )
                    context = json.loads(row["context_json"])
                    event = context.get("event") or {}
                    target_text = ", ".join(answer.get("targets") or ())
                    body = (
                        f"실행안: {answer['action']}\n"
                        f"판단 근거: {answer['reason']}\n"
                        f"기대 효과: {answer['expected_effect']}\n"
                        f"위험 요소: {answer['risk']}"
                    )
                    if target_text:
                        body += f"\n검토 대상: {target_text}"
                    connection.execute(
                        """INSERT OR IGNORE INTO daily_news
                        (save_id,news_date,category,headline,body,created_at)
                        VALUES (?,?, '상대 구단', ?, ?, CURRENT_TIMESTAMP)""",
                        (self.save_id, row["decision_date"],
                         f"{row['team']}, {event.get('title') or row['decision_type']} 대응안 확정",
                         body)
                    )
                else:
                    connection.execute(
                        "UPDATE team_ai_decision_queue SET status='deferred',result_json=? WHERE id=?",
                        (json.dumps({"error": "AI 응답에서 해당 구단 결정이 누락됨"}, ensure_ascii=False), row["id"]),
                    )

    @staticmethod
    def _validate_answers(rows, answers):
        """작은 모델의 누락·환각 응답이 게임 뉴스로 들어가는 것을 막는다."""
        rows_by_id = {int(row["id"]): row for row in rows}
        validated = {}
        if not isinstance(answers, list):
            return validated
        for raw in answers:
            if not isinstance(raw, dict):
                continue
            raw_id = raw.get("id")
            if raw_id is None:
                continue
            try:
                decision_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            row = rows_by_id.get(decision_id)
            if row is None:
                continue
            action = str(raw.get("action") or "").strip()
            reason = str(raw.get("reason") or "").strip()
            expected = str(raw.get("expected_effect") or "").strip()
            risk = str(raw.get("risk") or "").strip()
            if not action or not reason:
                continue
            context = json.loads(row["context_json"])
            roster = context.get("roster") or {}
            allowed_targets = {
                str(item.get("name"))
                for key in ("key_players", "prospects")
                for item in roster.get(key, ())
                if item.get("name")
            }
            allowed_targets.update(
                (roster.get("position_depth") or {}).keys()
            )
            raw_targets = raw.get("targets")
            if not isinstance(raw_targets, list):
                raw_targets = []
            targets = [
                str(target).strip()
                for target in raw_targets
                if str(target).strip() in allowed_targets
            ][:5]
            validated[decision_id] = {
                "id": decision_id,
                "action": action[:180],
                "reason": reason[:450],
                "targets": targets,
                "expected_effect": (
                    expected[:240] or "선수단 운영 목표에 맞춘 전력 효율 개선"
                ),
                "risk": (
                    risk[:240] or "실행 이후 선수 상태와 뎁스 변화를 재점검해야 함"
                ),
            }
        return validated

    def _defer_batch(self, rows, message):
        with self._connect() as connection:
            connection.executemany(
                "UPDATE team_ai_decision_queue SET status='deferred',result_json=? WHERE id=?",
                [(json.dumps({"error": message}, ensure_ascii=False), row["id"]) for row in rows],
            )
