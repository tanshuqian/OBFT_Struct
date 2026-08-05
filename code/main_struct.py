import argparse
import json
import os
import re
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
    """解析原始对话文件，返回 [{session_id, text}, ...]。
    支持两种模式：
    - 目录模式：每个 .txt 文件视为一个独立会话（适配 0728dialog 格式）
    - 单文件模式：按 end 标记切分多个会话（原有行为）
    """
    if filepath.is_dir():
        return _parse_dialog_directory(filepath)

    content = filepath.read_text(encoding="utf-8")
    sessions = split_into_sessions(content)
    return [
        {"session_id": f"session_{idx}", "text": session_text}
        for idx, session_text in enumerate(sessions, start=1)
    ]


def _parse_dialog_directory(dirpath: Path) -> List[dict]:
    """解析 0728dialog 格式目录，每个 .txt 文件作为一个独立会话。"""
    sessions: List[dict] = []
    for txt_file in sorted(dirpath.glob("*.txt")):
        session = _parse_single_dialog_file(txt_file)
        if session:
            sessions.append(session)
    return sessions


def _parse_chinese_date(date_str: str) -> Optional[str]:
    """将中文日期字符串（如 "2026年7月28日 14:36:27"）转为 ISO 格式 "2026-07-28"。"""
    m = re.match(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", date_str)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


def _parse_single_dialog_file(filepath: Path) -> Optional[dict]:
    """解析单个 0728dialog 格式的对话文件。

    文件头部包含元数据（录音名、时间、主题、参会人），之后为对话内容。
    跳过头部，提取录音名称作为 session_id、对话文本作为 text，
    并从头部时间行中提取就诊日期 (dov)。
    """
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()

    # 第一行是录音名称（如 "标准录音 1"），用作 session_id
    recording_name = lines[0].strip() if lines else filepath.stem

    # 从头部时间行提取就诊日期，用于后续日期标准化
    extracted_dov: Optional[str] = None
    for line in lines[:6]:  # 头部元数据在前 6 行内
        stripped = line.strip()
        if stripped.startswith("时间:") or stripped.startswith("时间："):
            date_str = stripped[3:].strip()  # 去掉 "时间:" / "时间：" 前缀
            extracted_dov = _parse_chinese_date(date_str)
            if extracted_dov:
                break

    # 找到第一个 "讲话人" 行 —— 从这里开始才是对话内容
    dialog_start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("讲话人"):
            dialog_start = i
            break

    if dialog_start == 0:
        print(f"  [跳过] 未在 {filepath.name} 中找到对话内容（无'讲话人'标记）")
        return None

    dialog_lines = [line.rstrip() for line in lines[dialog_start:]]
    dialog_text = "\n".join(dialog_lines).strip()

    if not dialog_text:
        print(f"  [跳过] {filepath.name} 对话内容为空")
        return None

    result: dict = {"session_id": recording_name, "text": dialog_text}
    if extracted_dov:
        result["dov"] = extracted_dov
        print(f"  [头部] 从 {filepath.name} 提取到就诊日期: {extracted_dov}")
    return result


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

        # 会话级别兜底：所有切片处理完后，若仍无主诉则填充默认值
        if not current_state.hpi.chiefcomplaint:
            current_state.hpi.chiefcomplaint = "无不适，常规产检"
            print(f"  > [兜底] 无主诉信息，设为默认值")

        return total_llm_time


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM extraction + structured record workflow.")
    repo_root = get_repo_root()
    default_input = repo_root / "data" / "input" / "0728dialog"
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

        engine.init_session(sid, args.dov or session.get("dov"))
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

