#!/usr/bin/env python3
"""
run_benchmark.py

Generic evaluation harness to call a language model HTTP API (Seepseek) over a set
of dialog chunks using a prompt template. Saves outputs to JSONL for later analysis.

Usage examples (Windows cmd.exe):
  set SEEPSEEK_API_KEY=your_key_here
  python run_benchmark.py --prompt extract_prompt.txt --input dialog.txt --output outputs.jsonl

If the Seepseek API endpoint or request format differs, provide --api-url and adjust
--model or request payload template as needed.
"""
import os
import sys
import argparse
import json
import time
import requests
from typing import List
from pathlib import Path


def load_prompt_template(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def split_dialogs(path: Path) -> List[str]:
    """
    Split the dialog file into chunks. The provided `dialog.txt` uses the token "end"
    to separate dialogs. We'll split by lines that are exactly 'end' (case-insensitive)
    or by double newlines if 'end' isn't present.
    """
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    chunks = []
    cur = []
    for ln in lines:
        if ln.strip().lower() == 'end':
            if cur:
                chunks.append('\n'.join(cur).strip())
                cur = []
            continue
        # treat explicit blank separator as well
        if ln.strip() == '' and cur:
            chunks.append('\n'.join(cur).strip())
            cur = []
            continue
        cur.append(ln)
    if cur:
        chunks.append('\n'.join(cur).strip())
    # filter empty
    return [c for c in chunks if c]


def call_seepseek(api_url: str, api_key: str, model: str, prompt: str, timeout=60):
    """
    Generic POST call. The function tries to work with several common response shapes:
    - OpenAI-like: {choices: [{text: ...}]}
    - {result: ...} or {data: [{text: ...}]}
    Adjust payload / parsing as required by Seepseek.
    """
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'prompt': prompt,
        'max_tokens': 2048,
        'temperature': 0.0,
    }
    try:
        r = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    except Exception as e:
        return {'error': str(e)}
    if r.status_code >= 400:
        return {'error': f'status {r.status_code}', 'body': r.text}
    try:
        data = r.json()
    except Exception:
        return {'error': 'invalid_json', 'body': r.text}

    # try common shapes
    if isinstance(data, dict):
        if 'choices' in data and isinstance(data['choices'], list) and data['choices']:
            text = data['choices'][0].get('text') or data['choices'][0].get('message', {}).get('content')
            return {'text': text, 'raw': data}
        if 'result' in data:
            return {'text': data['result'], 'raw': data}
        if 'data' in data and isinstance(data['data'], list) and data['data']:
            # try to find a text field
            first = data['data'][0]
            text = first.get('text') or first.get('content') or first.get('answer')
            return {'text': text, 'raw': data}
    # fallback: return whole json
    return {'text': json.dumps(data, ensure_ascii=False), 'raw': data}


def call_seepseek_sdk(api_key: str, base_url: str, model: str, prompt: str, reasoning_effort=None, extra_body=None, timeout=60):
    """
    Call Deepseek/Seepseek via OpenAI-style SDK pattern.
    Uses chat completions with the prompt as a single user message. Returns dict with 'text' and 'raw' or 'error'.
    """
    try:
        from openai import OpenAI
    except Exception as e:
        return {'error': f'openai SDK not installed: {e}'}

    # Try the constructor style shown in the user's snippet
    client = None
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
    except Exception:
        # fallback: set module-level values
        try:
            import openai as _openai
            _openai.api_key = api_key
            _openai.api_base = base_url
            client = _openai
        except Exception as e:
            return {'error': f'failed to init OpenAI client: {e}'}

    messages = [
        {"role": "user", "content": prompt}
    ]

    call_kwargs = {
        'model': model,
        'messages': messages,
        'stream': False,
    }
    if reasoning_effort is not None:
        call_kwargs['reasoning_effort'] = reasoning_effort
    if extra_body is not None:
        call_kwargs['extra_body'] = extra_body

    try:
        if hasattr(client, 'chat') and hasattr(client.chat, 'completions'):
            resp = client.chat.completions.create(**call_kwargs)
        elif hasattr(client, 'ChatCompletion'):
            resp = client.ChatCompletion.create(**call_kwargs)
        else:
            resp = client.chat.completions.create(**call_kwargs)
    except Exception as e:
        return {'error': f'call failed: {e}'}

    # Try to extract text from common response shapes
    try:
        # dict-like
        if isinstance(resp, dict) and 'choices' in resp and resp['choices']:
            text = resp['choices'][0].get('message', {}).get('content') or resp['choices'][0].get('text')
            return {'text': text, 'raw': make_json_safe(resp)}
        # object-like
        if hasattr(resp, 'choices') and resp.choices:
            c0 = resp.choices[0]
            msg = getattr(c0, 'message', None)
            if isinstance(msg, dict):
                content = msg.get('content')
            else:
                content = getattr(msg, 'content', None)
            content = content or getattr(c0, 'text', None)
            return {'text': content, 'raw': make_json_safe(resp)}
    except Exception:
        pass

    return {'text': str(resp), 'raw': make_json_safe(resp)}


def make_json_safe(obj):
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        pass

    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return obj.__dict__
        except Exception:
            pass
    return str(obj)


def main():
    parser = argparse.ArgumentParser(description='Run Seepseek benchmark on dialogs')
    parser.add_argument('--prompt', required=True, help='Prompt template file path (contains {chunk_text})')
    parser.add_argument('--input', required=True, help='Dialog input file path')
    parser.add_argument('--output', default='outputs.jsonl', help='Output JSONL file')
    parser.add_argument('--api-key', default=None, help='Seepseek API key (or use SEEPSEEK_API_KEY env var)')
    parser.add_argument('--api-url', default='https://api.seepseek.com/v1/completions', help='Seepseek API URL (override if different)')
    parser.add_argument('--model', default='seepseek-large', help='Model name to send')
    parser.add_argument('--use-sdk', action='store_true', help='Use OpenAI-style SDK (Deepseek) instead of raw HTTP')
    parser.add_argument('--sdk-base-url', default='https://api.deepseek.com', help='Base URL for SDK client')
    parser.add_argument('--sdk-api-env', default='DEEPSEEK_API_KEY', help='Env var name for SDK API key if --api-key not provided')
    parser.add_argument('--reasoning-effort', default=None, help='Optional reasoning_effort for SDK')
    parser.add_argument('--extra-body', default=None, help='Optional extra_body JSON string to pass to SDK')
    parser.add_argument('--max', type=int, default=0, help='Maximum number of chunks to run (0 = all)')
    parser.add_argument('--sleep', type=float, default=0.5, help='Seconds to sleep between requests')
    parser.add_argument('--retry', type=int, default=3, help='Request retries on failure')
    args = parser.parse_args()

    if args.use_sdk:
        api_key = args.api_key or os.environ.get(args.sdk_api_env)
        if not api_key:
            print(f'Error: SDK API key not provided. Set --api-key or {args.sdk_api_env} env var.', file=sys.stderr)
            sys.exit(1)
    else:
        api_key = args.api_key or os.environ.get('SEEPSEEK_API_KEY')
        if not api_key:
            print('Error: API key not provided. Set --api-key or SEEPSEEK_API_KEY env var.', file=sys.stderr)
            sys.exit(1)

    prompt_template = load_prompt_template(Path(args.prompt))
    chunks = split_dialogs(Path(args.input))
    if args.max > 0:
        chunks = chunks[: args.max]

    out_path = Path(args.output)
    out_f = out_path.open('w', encoding='utf-8')

    total = len(chunks)
    print(f'Running {total} chunks against {args.api_url} (model={args.model})')

    for i, chunk in enumerate(chunks, start=1):
        full_prompt = prompt_template.replace('{chunk_text}', chunk)
        attempt = 0
        resp = None
        while attempt <= args.retry:
            attempt += 1
            try:
                if args.use_sdk:
                    extra_body = None
                    if args.extra_body:
                        try:
                            extra_body = json.loads(args.extra_body)
                        except Exception as e:
                            resp = {'error': f'failed to parse --extra-body JSON: {e}'}
                            break
                    resp = call_seepseek_sdk(api_key=api_key, base_url=args.sdk_base_url, model=args.model, prompt=full_prompt, reasoning_effort=(args.reasoning_effort or None), extra_body=extra_body)
                else:
                    resp = call_seepseek(args.api_url, api_key, args.model, full_prompt)
            except Exception as e:
                resp = {'error': str(e)}
            if resp and 'error' not in resp:
                break
            print(f'Chunk {i}/{total} attempt {attempt} failed: {resp.get("error")}. Retrying...')
            time.sleep(1.0 * attempt)

        record = {
            'index': i,
            'input_chunk': chunk,
            'prompt': full_prompt,
            'response': make_json_safe(resp),
        }
        out_f.write(json.dumps(record, ensure_ascii=False) + '\n')
        out_f.flush()
        print(f'[{i}/{total}] saved.')
        time.sleep(args.sleep)

    out_f.close()
    print(f'Done. Outputs written to {out_path.resolve()}')


if __name__ == '__main__':
    main()


