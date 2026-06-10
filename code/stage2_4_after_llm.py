import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List

from mapping import route_and_transform
from schemas import MedicalRecordState, StatusDetail, OBHChild, FetusExam


class PostStructureStage24:
    def __init__(self) -> None:
        self.state_buffer = {}

    def init_session(self, session_id: str, dov: str = None) -> None:
        if session_id not in self.state_buffer:
            self.state_buffer[session_id] = MedicalRecordState(sessionId=session_id, dov=dov)

    def process_session(self, session_id: str, extracted_tags: List[dict]) -> None:
        current_state = self.state_buffer[session_id]
        # 规则映射入口：具体分块规则见 mapping.py -> SCHEMA_MAP / CATEGORY_TO_NODE / route_and_transform
        patch_dict = route_and_transform(extracted_tags, current_state.dov)
        self._apply_patch(current_state, patch_dict)

    def _apply_patch(self, state: MedicalRecordState, patch: dict) -> None:
        def _append_text(existing: str, incoming: str) -> str:
            if not incoming:
                return existing
            if not existing:
                return incoming
            if incoming in existing:
                return existing
            return f"{existing}；{incoming}"

        def _merge_status_detail(existing: StatusDetail, incoming: StatusDetail) -> StatusDetail:
            if existing is None:
                return incoming
            if incoming is None:
                return existing
            if existing.status == 1 and incoming.status in (0, -1):
                return existing
            if existing.status == 0 and incoming.status == 1:
                return incoming
            if existing.status == -1:
                return incoming
            if incoming.status == existing.status and incoming.details:
                merged_details = _append_text(existing.details, incoming.details)
                return StatusDetail(status=existing.status, details=merged_details)
            return incoming

        gravidity_val = patch.get("root", {}).get("gravidity", state.gravidity)
        obh_entries = None
        if isinstance(patch.get("obh"), dict) and "entries" in patch["obh"]:
            obh_entries = patch["obh"].pop("entries")
        has_obh_entries = bool(obh_entries)

        if gravidity_val is None or gravidity_val < 2:
            if not has_obh_entries:
                state.obh = []

        if has_obh_entries:
            from schemas import OBHEntry
            state.obh = [OBHEntry(**entry) for entry in obh_entries]

        for domain in [
            "obh", "hpi", "pmh", "additional_medical_history", "personal_history",
            "fh", "physicalExamination", "gynecologicalExamination", "advice"
        ]:
            if domain == "obh" and (gravidity_val is None or gravidity_val < 2) and not has_obh_entries:
                continue
            if domain in patch and patch[domain]:
                domain_model = getattr(state, domain)
                if domain == "obh" and isinstance(domain_model, list):
                    if not domain_model:
                        from schemas import OBHEntry
                        domain_model.append(OBHEntry())
                    domain_model = domain_model[0]
                for field, value in patch[domain].items():
                    if value is not None and value != []:
                        try:
                            current_value = getattr(domain_model, field)
                            if isinstance(current_value, StatusDetail) and isinstance(value, StatusDetail):
                                merged = _merge_status_detail(current_value, value)
                                setattr(domain_model, field, merged)
                                continue

                            if isinstance(current_value, str) and isinstance(value, str) and field.endswith("Note"):
                                merged = _append_text(current_value, value)
                                setattr(domain_model, field, merged)
                                continue

                            if isinstance(current_value, list):
                                if domain == "obh" and field == "children":
                                    for item in value:
                                        if isinstance(item, OBHChild):
                                            current_value.append(item)
                                        elif isinstance(item, dict):
                                            current_value.append(OBHChild(**item))
                                else:
                                    current_value.extend(value)
                            else:
                                setattr(domain_model, field, value)
                        except Exception as e:
                            msg = e.errors()[0]['msg'] if hasattr(e, 'errors') else str(e)
                            print(f"[blocked] {domain}.{field}: {msg}")

        # OBH 校验：由既往孕产史推导孕次/产次，包含死胎，0 也覆盖
        def _sum_obh_field(entries: list, field: str) -> int:
            total = 0
            for entry in entries:
                val = getattr(entry, field, None)
                if isinstance(val, (int, float)):
                    total += int(val)
            return total

        def _sum_abortion(entries: list) -> int:
            abortion_fields = [
                "naturalAbortion", "medicalAbortion", "surgicalAbortion",
                "currettageAbortion", "currettage", "biochemicalAbortion",
                "inducedLabor", "fetusdeath"
            ]
            return sum(_sum_obh_field(entries, field) for field in abortion_fields)

        def _sum_delivery_modes(entries: list) -> int:
            delivery_fields = [
                "vaginalDelivery", "cesareanSection", "forceps",
                "vacuumAssisted", "breechMidwifery"
            ]
            return sum(_sum_obh_field(entries, field) for field in delivery_fields)

        obh_entries = state.obh if isinstance(state.obh, list) else []
        a_count = _sum_abortion(obh_entries)
        delivery_count = _sum_delivery_modes(obh_entries)

        if obh_entries:
            # 有 OBH 条目时：每个条目代表一次既往妊娠，+1 为当前妊娠
            calc_parity = delivery_count
            calc_gravidity = len(obh_entries) + 1
            # 交叉校验：delivery_count + a_count 应等于 len(obh_entries)
            event_sum = delivery_count + a_count
            if event_sum != len(obh_entries):
                print(f"[OBH校验] ⚠ 事件求和({event_sum}) ≠ 条目数({len(obh_entries)})，"
                      f"可能存在未归类的妊娠条目（delivery={delivery_count}, abortion={a_count}）")
        else:
            # 无 OBH 条目时：保留 LLM 提取的原始值，仅推导 parity=0
            calc_parity = 0
            calc_gravidity = state.gravidity if state.gravidity is not None else 1
            if state.parity is not None:
                calc_gravidity = max(calc_gravidity, state.parity + 1)
            print(f"[OBH校验] 无既往孕产史条目，保留原始孕次={calc_gravidity}")

        if state.gravidity != calc_gravidity:
            print(f"[OBH校验] gravidity {state.gravidity} -> {calc_gravidity}")
        state.gravidity = calc_gravidity

        if state.parity != calc_parity:
            print(f"[OBH校验] parity {state.parity} -> {calc_parity}")
        state.parity = calc_parity

        if "root" in patch and patch["root"]:
            for field, value in patch["root"].items():
                if field in ("gravidity", "parity"):
                    continue
                setattr(state, field, value)

        if "fetusExam" in patch:
            for index, fetus_data in patch["fetusExam"].items():
                if index in state.fetusExam:
                    for k, v in fetus_data.items():
                        setattr(state.fetusExam[index], k, v)
                else:
                    state.fetusExam[index] = FetusExam(**fetus_data)


def _iter_json_arrays(text: str) -> List[list]:
    arrays = []
    buf = []
    depth = 0
    in_string = False
    escape = False

    for ch in text:
        if in_string:
            buf.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            if depth > 0:
                buf.append(ch)
            continue

        if ch == '[':
            depth += 1
            buf.append(ch)
            continue
        if ch == ']':
            if depth > 0:
                buf.append(ch)
            depth -= 1
            if depth == 0 and buf:
                block = ''.join(buf).strip()
                if block:
                    arrays.append(json.loads(block))
                buf = []
            continue

        if depth > 0:
            buf.append(ch)

    return arrays


def load_extracted_blocks(file_path: Path) -> List[list]:
    text = file_path.read_text(encoding="utf-8")
    return [block for block in _iter_json_arrays(text) if block]


def log_performance(output_dir: Path, total_sessions: int, total_time: float) -> None:
    qps = total_sessions / total_time if total_time > 0 else 0
    log_content = f"""========================================
性能评估日志 | 实验: Stage2_4_After_LLM
========================================
测试时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
处理会话总数 (Sessions): {total_sessions}
----------------------------------------
LLM 纯推理总耗时: 0.0000 秒
端到端整体总耗时: {total_time:.4f} 秒
端到端 QPS (Query Per Second): {qps:.4f} sessions/sec
平均单 Session 推理延迟: 0.0000 秒
========================================
"""
    perf_log_path = output_dir / "performance.log"
    perf_log_path.write_text(log_content, encoding="utf-8")
    print(f"\nPerformance log written to {perf_log_path}")


def _load_blocks_from_folder(folder: Path) -> List[tuple]:
    """从文件夹中按文件名排序加载每个 .jsonl 文件，返回 [(文件词干, tags列表), ...]"""
    items = []
    for jsonl_file in sorted(folder.glob("*.jsonl"), key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem):
        text = jsonl_file.read_text(encoding="utf-8").strip()
        # 容错：移除数组末尾最后一个元素后的多余逗号（如 "},\n]" → "}\n]"）
        text = re.sub(r',\s*(\]\s*$)', r'\1', text)
        tags = json.loads(text)
        items.append((jsonl_file.stem, tags))
    return items


def _load_blocks_from_file(file_path: Path) -> List[tuple]:
    """从单文件中加载多个 JSON 数组，返回 [(序号, tags列表), ...]"""
    blocks = load_extracted_blocks(file_path)
    return [(str(idx), tags) for idx, tags in enumerate(blocks, start=1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run stage2-4 mapping on extracted facts.")
    parser.add_argument(
        "--input",
        default=None,
        help="Path to input: a .jsonl file (concatenated JSON arrays) or a folder of per-session .jsonl files."
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for structured results."
    )
    parser.add_argument(
        "--dov",
        default=None,
        help="Visit date (YYYY-MM-DD). If not provided, will be extracted from LLM data or left as null."
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    input_path = Path(args.input) if args.input else repo_root / "data" / "output" / "LLM_Truth_20_2.0"

    # 自动判断输入是文件夹还是单文件
    if input_path.is_dir():
        session_items = _load_blocks_from_folder(input_path)
    else:
        session_items = _load_blocks_from_file(input_path)

    if not session_items:
        print(f"No blocks parsed from {input_path}")
        return 1

    exp_name = "Stage2_4_After_LLM"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else repo_root / "output" / f"{exp_name}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = PostStructureStage24()
    total_start_time = time.time()

    for idx, (stem, tags) in enumerate(session_items, start=1):
        session_id = f"test_session_{stem}"
        # 从LLM提取数据中获取就诊日期；若无则使用命令行传入的dov；都无则为null
        session_dov = args.dov
        if not session_dov:
            for tag in tags:
                if tag.get("key") == "就诊日期":
                    session_dov = tag.get("value")
                    break
        print(f"\n========== Processing {session_id} ({idx}/{len(session_items)}) ==========")
        engine.init_session(session_id, session_dov)
        engine.process_session(session_id, tags)

        final_state = engine.state_buffer[session_id].to_output_dict()
        output_file = output_dir / f"{session_id}.json"
        output_file.write_text(
            json.dumps(final_state, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"Saved: {output_file}")

    total_end_time = time.time()
    log_performance(output_dir, len(session_items), total_end_time - total_start_time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
