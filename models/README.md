# KBOFM 로컬 AI 모델

이 폴더에는 Git으로 배포하지 않는 GGUF 모델을 둡니다. `*.gguf`, `*.bin`,
`*.safetensors` 가중치는 `.gitignore`로 제외됩니다.

기본 권장 모델 파일:

`Qwen3-4B-Q4_K_M.gguf`

다운로드:

```powershell
python -m pip install --upgrade huggingface_hub
hf download ggml-org/Qwen3-4B-GGUF Qwen3-4B-Q4_K_M.gguf --local-dir models
```

모델 페이지: https://huggingface.co/ggml-org/Qwen3-4B-GGUF

4B 모델이 없으면 `Qwen3-1.7B-Q4_K_M.gguf`를 자동으로 사용합니다.

로컬 AI 서버 실행:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local_ai.ps1
```
