Seepseek benchmark harness
=========================

Files:
- `run_benchmark.py` : Python script to run the prompt template against dialog chunks and save responses.
- `requirements.txt` : Python dependency (requests).
- `requirements.txt` : Python dependencies (requests, openai).

Quick start (Windows cmd.exe):

1. Install Python dependencies:
```
python -m pip install -r requirements.txt
```

2. Set your API key and run the benchmark:
```
set SEEPSEEK_API_KEY=your_key_here
python run_benchmark.py --prompt extract_prompt.txt --input dialog.txt --output outputs.jsonl
```

SDK usage (Deepseek / OpenAI-style)
```
set DEEPSEEK_API_KEY=your_deepseek_key
python run_benchmark.py --use-sdk --sdk-base-url https://api.deepseek.com --prompt extract_prompt.txt --input dialog.txt --output outputs.jsonl --model deepseek-v4-pro --extra-body "{\"thinking\": {\"type\": \"enabled\"}}" --reasoning-effort high
```

Notes:
- The script uses a default API URL `https://api.seepseek.com/v1/completions` and a default model name `seepseek-large`.
  If Seepseek's API uses a different endpoint or request body, provide `--api-url` and `--model` or adapt the script's
  payload/response parsing accordingly.
- The prompt template `extract_prompt.txt` is expected to contain the placeholder `{chunk_text}` which will be replaced
  with each dialog chunk.
- Outputs are written to JSONL where each line is a JSON object with fields: index, input_chunk, prompt, response.

If you'd like, I can:
- adapt the script to a precise Seepseek API specification if you provide the endpoint/payload/response format,
- add concurrency, or
- implement automatic metric computation (e.g., exact-match, custom validators) for the JSON extraction task.

