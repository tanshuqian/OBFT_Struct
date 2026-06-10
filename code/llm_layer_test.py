import argparse
import json
import os
import time
from datetime import datetime

from llm_extractor import LLMExtractor

DEFAULT_INPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "input", "dialog_new.txt")
DEFAULT_EXP_NAME = "LLM_Layer_Test"


def parse_input_file(filepath: str):
    """Parse sessions separated by 'end' and filter empty text."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    sessions = content.split("end")
    parsed_sessions = []

    for i, session_text in enumerate(sessions):
        clean_text = session_text.strip()
        if len(clean_text) < 10:
            continue
        parsed_sessions.append({
            "session_id": f"session_{i + 1}",
            "text": clean_text
        })
    return parsed_sessions


def split_into_chunks(text: str, lines_per_chunk: int = 4) -> list:
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    chunks = []
    for i in range(0, len(lines), lines_per_chunk):
        chunks.append("\n".join(lines[i:i + lines_per_chunk]))
    return chunks


def log_performance(output_dir: str, exp_name: str, total_sessions: int, total_time: float, llm_time: float):
    qps = total_sessions / total_time if total_time > 0 else 0
    log_content = f"""========================================
性能评估日志 | 实验: {exp_name}
========================================
测试时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
处理会话总数 (Sessions): {total_sessions}
----------------------------------------
LLM 纯推理总耗时: {llm_time:.4f} 秒
端到端整体总耗时: {total_time:.4f} 秒
端到端 QPS (Query Per Second): {qps:.4f} sessions/sec
平均单 Session 推理延迟: {(llm_time / total_sessions) if total_sessions > 0 else 0:.4f} 秒
========================================
"""
    perf_log_file = os.path.join(output_dir, "performance.log")
    with open(perf_log_file, 'w', encoding='utf-8') as f:
        f.write(log_content)
    print(f"\n📊 性能日志已写入: {perf_log_file}")


def validate_four_fields(items: list) -> dict:
    required = ("key", "term", "value", "raw")
    summary = {
        "total": len(items),
        "missing_any": 0,
        "missing_detail": {k: 0 for k in required},
        "invalid_items": []
    }

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            summary["missing_any"] += 1
            summary["invalid_items"].append({"index": idx, "reason": "not_dict"})
            continue
        missing = [k for k in required if k not in item or item.get(k) in (None, "")]
        if missing:
            summary["missing_any"] += 1
            for k in missing:
                summary["missing_detail"][k] += 1
            summary["invalid_items"].append({"index": idx, "missing": missing})

    return summary


def _write_parsed_jsonl(output_dir: str, sessions_payload: list) -> str:
    result_file = os.path.join(output_dir, "parsed_data.jsonl")
    with open(result_file, "w", encoding="utf-8") as f:
        for idx, items in enumerate(sessions_payload):
            f.write(json.dumps(items, ensure_ascii=False, indent=2))
            if idx < len(sessions_payload) - 1:
                f.write("\n\n")
    return result_file


def run_llm_test(input_file: str, output_dir: str, exp_name: str, lines_per_chunk: int, dry_run: bool,
                 base_url: str | None, model_name: str | None, fallback_dry_run: bool, print_raw: bool,
                 parsed_only: bool):
    sessions = parse_input_file(input_file)
    extractor = None
    if not dry_run:
        extractor = LLMExtractor(base_url=base_url, model_name=model_name, print_raw=print_raw)
        if not extractor.ping():
            msg = "⚠️ vLLM 服务不可用，确认 8000 端口已启动并可访问。"
            print(msg)
            if fallback_dry_run:
                print("⚠️ 自动切换为 dry-run 模式，仅输出空结果用于流程验证。")
                dry_run = True
                extractor = None

    results = {
        "experiment": exp_name,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input_file": os.path.abspath(input_file),
        "lines_per_chunk": lines_per_chunk,
        "dry_run": dry_run,
        "sessions": [],
        "performance": {}
    }

    parsed_sessions_payload = []

    total_start_time = time.time()
    total_llm_time = 0.0

    for idx, session in enumerate(sessions):
        print("\n\n")
        sid = session["session_id"]
        text = session["text"]
        if not parsed_only:
            print(f"\n========== 开始处理 {sid} ({idx + 1}/{len(sessions)}) ==========")

        chunks = split_into_chunks(text, lines_per_chunk=lines_per_chunk)
        session_item = {
            "session_id": sid,
            "chunk_count": len(chunks),
            "chunks": []
        }
        session_parsed_items = []

        for cidx, chunk in enumerate(chunks):
            if not parsed_only:
                print(f"\n  [{sid}] --- 处理切片 {cidx + 1}/{len(chunks)} ---")
                print(f"  > 切片内容:\n{chunk}")

            error = None
            if dry_run:
                parsed_data = []
                raw_output = ""
                inference_time = 0.0
            else:
                try:
                    parsed_data, inference_time, raw_output = extractor.extract(chunk, return_raw=True)
                except Exception as exc:
                    error = str(exc)
                    parsed_data = []
                    raw_output = ""
                    inference_time = 0.0
                    if not parsed_only:
                        print(f"  [错误] LLM 调用失败，已跳过该切片: {error}")

            total_llm_time += inference_time

            for item in parsed_data:
                print(json.dumps(item, ensure_ascii=False))
            # if parsed_only:
            #     for item in parsed_data:
            #         print(json.dumps(item, ensure_ascii=False))
            # else:
            #     print("  > [阶段一] LLM 提取:")
            #     for item in parsed_data:
            #         key = item.get("key", "")
            #         term = item.get("term", "")
            #         value = item.get("value", "")
            #         raw = item.get("raw", "")
            #         print(f"    - key={key} | term={term} | value={value} | raw={raw}")

            session_parsed_items.extend(parsed_data)
            validation = validate_four_fields(parsed_data)

            session_item["chunks"].append({
                "chunk_index": cidx + 1,
                "chunk_text": chunk,
                "raw_output": raw_output,
                "parsed_data": parsed_data,
                "validation": validation,
                "inference_time": inference_time,
                "error": error
            })

        results["sessions"].append(session_item)
        parsed_sessions_payload.append(session_parsed_items)

    total_end_time = time.time()
    total_time = total_end_time - total_start_time

    results["performance"] = {
        "total_sessions": len(sessions),
        "total_time": total_time,
        "llm_time": total_llm_time,
        "qps": (len(sessions) / total_time) if total_time > 0 else 0,
        "avg_session_latency": (total_llm_time / len(sessions)) if len(sessions) > 0 else 0
    }

    log_performance(output_dir, exp_name, len(sessions), total_time, total_llm_time)

    parsed_file = _write_parsed_jsonl(output_dir, parsed_sessions_payload)
    if not parsed_only:
        result_file = os.path.join(output_dir, "llm_test_results.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"LLM 测试完成，结果已保存至: {result_file}")

    print(f"解析结果已保存至: {parsed_file}")


def main():
    parser = argparse.ArgumentParser(description="LLM 层独立测试脚本")
    parser.add_argument("--input", default=DEFAULT_INPUT_FILE, help="输入对话文件路径")
    parser.add_argument("--exp-name", default=DEFAULT_EXP_NAME, help="实验名称")
    parser.add_argument("--lines-per-chunk", type=int, default=4, help="每个切片的行数")
    parser.add_argument("--output-dir", default=None, help="输出目录（默认在 output/ 下自动创建）")
    parser.add_argument("--base-url", default=None, help="vLLM API base URL，例如 http://localhost:8000/v1")
    parser.add_argument("--model-name", default=None, help="vLLM served model name，例如 qwen3")
    parser.add_argument("--fallback-dry-run", action="store_true", help="连接失败时自动切换为 dry-run")
    parser.add_argument("--print-raw", action="store_true", help="打印 LLM 原始输出（默认不打印）")
    parser.add_argument("--dry-run", action="store_true", help="不调用 LLM，仅走流程")
    parser.add_argument("--parsed-only", action="store_true", default=False, help="仅输出 parsed_data 并写入 jsonl")
    parser.add_argument("--full-output", action="store_true", help="输出完整调试信息与结果 JSON")
    args = parser.parse_args()

    parsed_only = args.parsed_only and not args.full_output

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or os.path.join(base_dir, "output", f"{args.exp_name}_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    run_llm_test(
        input_file=args.input,
        output_dir=output_dir,
        exp_name=args.exp_name,
        lines_per_chunk=args.lines_per_chunk,
        dry_run=args.dry_run,
        base_url=args.base_url,
        model_name=args.model_name,
        fallback_dry_run=args.fallback_dry_run,
        print_raw=args.print_raw,
        parsed_only=parsed_only
    )


if __name__ == "__main__":
    main()
