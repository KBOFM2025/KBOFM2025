"""llama.cpp·Ollama의 OpenAI 호환 로컬 엔드포인트 클라이언트."""

import json
import os
import re
import signal
import subprocess
import sys
import threading
from http import client as http_client
from pathlib import Path
from urllib import parse


class LocalModelError(RuntimeError):
    pass


def local_ai_enabled():
    return os.getenv("KBOFM_AI_ENABLED", "1").lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


class LocalModelClient:
    def __init__(self, base_url=None, model=None, timeout=None):
        self.base_url = (base_url or os.getenv("KBOFM_AI_BASE_URL", "http://127.0.0.1:8080/v1")).rstrip("/")
        self.model = model or os.getenv("KBOFM_AI_MODEL", "kbofm-local")
        self.timeout = float(timeout or os.getenv("KBOFM_AI_TIMEOUT", "35"))
        self.enabled = local_ai_enabled()
        self._connection = None
        self._connection_lock = threading.Lock()

    def cancel(self):
        """진행 중인 로컬 모델 HTTP 연결을 닫아 대기 중인 요청을 중단한다."""
        with self._connection_lock:
            connection = self._connection
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass

    def generate_json(self, system_prompt, context, schema=None):
        if not self.enabled:
            raise LocalModelError("로컬 AI가 환경 설정에서 비활성화되어 있습니다.")

        request_type = context.get("request_type")
        is_batch_review = request_type == "board_vision_batch_review"
        is_team_batch = request_type == "team_daily_batch"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "/no_think\n" + json.dumps(
                        context,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "temperature": 0.35 if is_batch_review or is_team_batch else 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "presence_penalty": 1.2,
            "max_tokens": 480 if is_team_batch else 360 if is_batch_review else 220,
            "stream": False,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if schema:
            constrained_schema = json.loads(json.dumps(schema))
            body["response_format"] = {
                "type": "json_object",
                "schema": constrained_schema,
            }
            body["json_schema"] = constrained_schema

        endpoint = parse.urlsplit(f"{self.base_url}/chat/completions")
        connection_class = (
            http_client.HTTPSConnection if endpoint.scheme == "https"
            else http_client.HTTPConnection
        )
        request_timeout = max(self.timeout, 75) if is_batch_review or is_team_batch else self.timeout
        connection = connection_class(endpoint.hostname, endpoint.port, timeout=request_timeout)
        with self._connection_lock:
            self._connection = connection
        try:
            path = endpoint.path or "/"
            if endpoint.query:
                path += f"?{endpoint.query}"
            connection.request(
                "POST", path,
                body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer local-no-key"},
            )
            response = connection.getresponse()
            response_payload = json.loads(response.read().decode("utf-8"))
            if response.status >= 400:
                raise LocalModelError(f"로컬 모델 HTTP 오류: {response.status}")
        except (http_client.HTTPException, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise LocalModelError(f"로컬 모델 연결 실패: {exc}") from exc
        finally:
            with self._connection_lock:
                if self._connection is connection:
                    self._connection = None
            connection.close()

        try:
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalModelError("로컬 모델 응답 형식이 올바르지 않습니다.") from exc
        return self._parse_json_content(content)

    @staticmethod
    def _parse_json_content(content):
        if isinstance(content, dict):
            return content
        text = str(content).strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
        raise LocalModelError("로컬 모델이 유효한 JSON을 반환하지 않았습니다.")


def owned_ai_pid_path():
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parents[2] / "data" / "ai_logs" / "local_ai.pid"
    executable_dir = Path(sys.executable).resolve().parent
    candidates = (
        executable_dir / "data" / "ai_logs" / "local_ai.pid",
        executable_dir.parent / "data" / "ai_logs" / "local_ai.pid",
    )
    return next((path for path in candidates if path.exists()), candidates[0])


def stop_owned_local_ai_server():
    """KBOFM 실행 스크립트가 시작했다고 기록한 llama-server만 종료한다."""
    pid_path = owned_ai_pid_path()
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=3, creationflags=flags,
        )
        if "llama-server.exe" not in result.stdout.lower():
            return False
        os.kill(pid, signal.SIGTERM)
        print(f"[로컬 AI 서버] llama-server 종료 완료 · PID {pid}", flush=True)
        return True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"[로컬 AI 서버] 종료 확인 실패 · {error}", flush=True)
        return False
    finally:
        try:
            pid_path.unlink(missing_ok=True)
        except OSError:
            pass
