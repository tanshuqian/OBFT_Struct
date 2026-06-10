import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

os.environ.setdefault("OMP_NUM_THREADS", "4")

from llm_extractor import LLMExtractor
from mapping import route_and_transform
from stage2_4_after_llm import PostStructureStage24


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def split_into_sessions(text: str) -> List[str]:
    """按独立的 `end` 标记切分会话；若未检测到标记，则退化为单会话。"""
    sessions: List[str] = []
    current_lines: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() == "end":
            session_text = "\n".join(current_lines).strip()
            if len(session_text) >= 10:
                sessions.append(session_text)
            current_lines = []
        else:
            current_lines.append(raw_line.rstrip())

    tail = "\n".join(current_lines).strip()
    if len(tail) >= 10:
        sessions.append(tail)

    if not sessions:
        fallback = text.strip()
        if fallback:
            sessions.append(fallback)

    return sessions


def parse_input_file(filepath: Path) -> List[dict]:
    """解析原始对话文件，返回 [{session_id, text}, ...]。"""
    content = filepath.read_text(encoding="utf-8")
    sessions = split_into_sessions(content)
    return [
        {"session_id": f"session_{idx}", "text": session_text}
        for idx, session_text in enumerate(sessions, start=1)
    ]


def infer_dov_from_tags(extracted_tags: List[dict]) -> Optional[str]:
    """从抽取结果中尽量识别就诊日期，用于日期标准化。"""
    preferred_keys = {"就诊日期", "访视日期", "检查日期", "日期"}
    for tag in extracted_tags:
        key = str(tag.get("key", "")).strip()
        value = tag.get("value")
        if key in preferred_keys and value:
            return str(value)
    return None


def log_performance(output_dir: Path, total_sessions: int, total_time: float, llm_time: float) -> None:
    qps = total_sessions / total_time if total_time > 0 else 0
    log_content = f"""========================================
性能评估日志 | 实验: MainStruct_{datetime.now().strftime("%Y%m%d_%H%M%S")}
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
    perf_log_path = output_dir / "performance.log"
    perf_log_path.write_text(log_content, encoding="utf-8")
    print(f"\n📊 性能日志已写入 {perf_log_path}")


class MainStructEngine(PostStructureStage24):
    """LLM 抽取 + 规则映射 + 状态合并 的总编排器。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        print_raw: bool = False,
        lines_per_chunk: int = 4,
    ):
        super().__init__()
        self.llm = LLMExtractor(base_url=base_url, model_name=model_name, print_raw=print_raw)
        self.lines_per_chunk = max(1, int(lines_per_chunk))

    def split_into_chunks(self, text: str) -> List[str]:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        chunks: List[str] = []
        for i in range(0, len(lines), self.lines_per_chunk):
            chunks.append("\n".join(lines[i:i + self.lines_per_chunk]))
        return chunks

    def process_raw_session(self, session_id: str, full_text: str) -> float:
        current_state = self.state_buffer[session_id]
        chunks = self.split_into_chunks(full_text)
        total_llm_time = 0.0

        for idx, chunk in enumerate(chunks):
            print(f"\n  [{session_id}] --- 处理切片 {idx + 1}/{len(chunks)} ---")
            print(f"  > 切片内容:\n{chunk}")

            extracted_tags, inference_time = self.llm.extract(chunk)
            total_llm_time += inference_time

            print("  > [阶段一] LLM 提取:")
            for item in extracted_tags:
                print(f"    - {json.dumps(item, ensure_ascii=False)}")

            if current_state.dov is None:
                inferred_dov = infer_dov_from_tags(extracted_tags)
                if inferred_dov:
                    current_state.dov = inferred_dov
                    print(f"  > [辅助] 推断到就诊日期 dov = {current_state.dov}")

            # route_and_transform 负责“怎么改”
            patch_dict = route_and_transform(extracted_tags, current_state.dov)
            print(f"  > [阶段二] 路由补丁: {json.dumps(patch_dict, ensure_ascii=False, default=str)}")

            # _apply_patch 负责把补丁写入状态机
            print(f"  > [阶段三] 状态机日志:")
            self._apply_patch(current_state, patch_dict)

        return total_llm_time


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM extraction + structured record workflow.")
    repo_root = get_repo_root()
    default_input = repo_root / "data" / "input" / "dialog_head5.txt"
    default_output = repo_root / "output" / f"MainStruct_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    parser.add_argument("--input", default=str(default_input), help="Path to raw dialog text file.")
    parser.add_argument("--output-dir", default=str(default_output), help="Directory for structured JSON outputs.")
    parser.add_argument("--dov", default=None, help="Visit date (YYYY-MM-DD) used for date normalization.")
    parser.add_argument("--lines-per-chunk", type=int, default=4, help="Number of non-empty lines per chunk.")
    parser.add_argument("--base-url", default=None, help="vLLM base URL, default reads VLLM_BASE_URL or localhost.")
    parser.add_argument("--model-name", default=None, help="Model name, default reads VLLM_MODEL_NAME or qwen3.")
    parser.add_argument("--print-raw", action="store_true", help="Print raw LLM responses for debugging.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = (repo_root / input_path).resolve()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = (repo_root / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"[错误] 输入文件不存在: {input_path}")
        return 1

    sessions = parse_input_file(input_path)
    if not sessions:
        print(f"[错误] 未从输入文件解析到有效会话: {input_path}")
        return 1

    engine = MainStructEngine(
        base_url=args.base_url,
        model_name=args.model_name,
        print_raw=args.print_raw,
        lines_per_chunk=args.lines_per_chunk,
    )

    if not engine.llm.ping():
        print("[警告] vLLM 服务未通过 ping 检查，后续抽取可能失败。")

    total_start_time = time.time()
    total_llm_time = 0.0

    for idx, session in enumerate(sessions, start=1):
        sid = session["session_id"]
        text = session["text"]
        print(f"\n========== 开始处理 {sid} ({idx}/{len(sessions)}) ==========")

        engine.init_session(sid, args.dov)
        llm_time = engine.process_raw_session(sid, text)
        total_llm_time += llm_time

        final_state = engine.state_buffer[sid].to_output_dict()
        output_file = output_dir / f"{sid}.json"
        output_file.write_text(
            json.dumps(final_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"✅ {sid} 结构化完成，已保存至: {output_file}")

    total_end_time = time.time()
    log_performance(output_dir, len(sessions), total_end_time - total_start_time, total_llm_time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

