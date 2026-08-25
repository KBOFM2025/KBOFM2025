"""llama.cpp·Ollama의 OpenAI 호환 로컬 엔드포인트 클라이언트."""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
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


def _local_ai_health_url(base_url=None):
    base_url = (
        base_url
        or os.getenv("KBOFM_AI_BASE_URL", "http://127.0.0.1:8080/v1")
    ).rstrip("/")
    endpoint = parse.urlsplit(base_url)
    port = endpoint.port or (443 if endpoint.scheme == "https" else 80)
    return endpoint.scheme or "http", endpoint.hostname, port


def local_ai_ready(base_url=None, timeout=1.0):
    """llama.cpp 서버가 모델 로딩까지 끝내고 요청을 받을 수 있는지 확인한다."""
    try:
        scheme, hostname, port = _local_ai_health_url(base_url)
        connection_class = (
            http_client.HTTPSConnection
            if scheme == "https"
            else http_client.HTTPConnection
        )
        connection = connection_class(hostname, port, timeout=timeout)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            response.read()
            return response.status == 200
        finally:
            connection.close()
    except (http_client.HTTPException, TimeoutError, OSError):
        return False


def ensure_local_ai_server(progress_callback=None, startup_timeout=None):
    """main.py 부팅 중 로컬 AI 서버를 시작하고 모델 준비 완료까지 기다린다."""
    if not local_ai_enabled():
        return {
            "ready": False,
            "started": False,
            "message": "환경 설정에서 로컬 AI가 비활성화되어 있습니다.",
        }
    if local_ai_ready():
        return {
            "ready": True,
            "started": False,
            "message": "실행 중인 로컬 AI 서버를 사용합니다.",
        }

    project_root = Path(__file__).resolve().parents[2]
    script_path = project_root / "scripts" / "start_local_ai.ps1"
    if not script_path.exists():
        return {
            "ready": False,
            "started": False,
            "message": f"AI 시작 스크립트를 찾을 수 없습니다: {script_path}",
        }

    context_size = int(os.getenv("KBOFM_AI_CONTEXT_SIZE", "8192"))
    timeout = float(
        startup_timeout or os.getenv("KBOFM_AI_STARTUP_TIMEOUT", "120")
    )
    if progress_callback is not None:
        progress_callback("Qwen 로컬 AI 서버를 시작하고 있습니다")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-ContextSize",
                str(context_size),
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "ready": False,
            "started": False,
            "message": f"로컬 AI 실행 명령 실패: {error}",
        }
    if result.returncode != 0:
        reason = (result.stderr or result.stdout or "알 수 없는 오류").strip()
        return {
            "ready": False,
            "started": False,
            "message": f"로컬 AI 서버 시작 실패: {reason}",
        }

    deadline = time.monotonic() + max(5.0, timeout)
    while time.monotonic() < deadline:
        if local_ai_ready(timeout=1.0):
            return {
                "ready": True,
                "started": True,
                "message": (
                    f"로컬 AI 준비 완료 · 컨텍스트 {context_size}"
                ),
            }
        if progress_callback is not None:
            progress_callback("Qwen 모델을 메모리에 불러오고 있습니다")
        time.sleep(0.35)
    return {
        "ready": False,
        "started": True,
        "message": (
            f"로컬 AI 준비 시간이 {int(timeout)}초를 초과했습니다. "
            "data/ai_logs/local_ai.stderr.log를 확인하십시오."
        ),
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
        is_player_meeting = (
            request_type == "manager_negotiation_turn"
            and context.get("event_type") == "player_complaint"
        )
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
            "temperature": (
                0.35 if is_batch_review or is_team_batch
                else 0.55 if is_player_meeting
                else 0.7
            ),
            "top_p": 0.85 if is_player_meeting else 0.8,
            "top_k": 20,
            "presence_penalty": 1.2,
            "max_tokens": (
                480 if is_team_batch
                else 240 if is_batch_review
                else 180 if is_player_meeting
                else 220
            ),
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
        if is_batch_review:
            request_timeout = max(
                self.timeout,
                float(os.getenv("KBOFM_AI_BOARD_TIMEOUT", "180")),
            )
        elif is_team_batch:
            request_timeout = max(self.timeout, 120)
        else:
            request_timeout = self.timeout
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
