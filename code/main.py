import os
os.environ['OMP_NUM_THREADS'] = '4'
import json
import time
from datetime import datetime
from schemas import MedicalRecordState, StatusDetail, OBHChild
from llm_extractor import LLMExtractor
from mapping import route_and_transform

# ===== 路径配置 =====
INPUT_FILE = "/root/autodl-tmp/PostStruct2.0/data/input/dialog_113.txt"
BASE_DIR = "/root/autodl-tmp/PostStruct2.0"
EXP_NAME = "Qwen3-14B-fp8_Struct_Ultimate"
EXP_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", f"{EXP_NAME}_{EXP_TIMESTAMP}")
PERF_LOG_FILE = os.path.join(OUTPUT_DIR, "performance.log")


class PostStructureEngine:
    def __init__(self):
        self.llm = LLMExtractor()
        self.state_buffer = {}

    def init_session(self, session_id: str, dov: str):
        if session_id not in self.state_buffer:
            self.state_buffer[session_id] = MedicalRecordState(sessionId=session_id, dov=dov)

    # 调大 Chunk size，避免医生问话和患者回答被割裂到两个切片中
    def split_into_chunks(self, text: str, lines_per_chunk: int = 4) -> list:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        chunks = []
        for i in range(0, len(lines), lines_per_chunk):
            chunks.append("\n".join(lines[i:i + lines_per_chunk]))
        return chunks

    def process_session(self, session_id: str, full_text: str) -> float:
        current_state = self.state_buffer[session_id]
        chunks = self.split_into_chunks(full_text)
        total_llm_time = 0.0

        for idx, chunk in enumerate(chunks):
            print(f"\n  [{session_id}] --- 处理切片 {idx + 1}/{len(chunks)} ---")
            print(f"  > 切片内容:\n{chunk}")

            # 1. 抽取 (感知)
            extracted_tags, inference_time = self.llm.extract(chunk)
            total_llm_time += inference_time
            print("  > [阶段一] LLM 提取:")
            for item in extracted_tags:
                print(f"    - {json.dumps(item, ensure_ascii=False)}")

            # 2. 路由 (映射)
            patch_dict = route_and_transform(extracted_tags, current_state.dov)
            print(f"  > [阶段二] 路由补丁: {json.dumps(patch_dict, ensure_ascii=False, default=str)}")

            # 3. 校验与更新
            print(f"  > [阶段三] 状态机日志:")
            self._apply_patch(current_state, patch_dict)

        return total_llm_time

    def _apply_patch(self, state: MedicalRecordState, patch: dict):
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
        if gravidity_val is None or gravidity_val < 2:
            state.obh = []

        obh_entries = None
        if isinstance(patch.get("obh"), dict) and "entries" in patch["obh"]:
            obh_entries = patch["obh"].pop("entries")

        if obh_entries and gravidity_val is not None and gravidity_val >= 2:
            from schemas import OBHEntry
            state.obh = [OBHEntry(**entry) for entry in obh_entries]

        # 1. 更新带有层级的模块
        for domain in [
            "obh", "hpi", "pmh", "additional_medical_history", "personal_history",
            "fh", "physicalExamination", "gynecologicalExamination", "advice"
        ]:
            if domain == "obh" and (gravidity_val is None or gravidity_val < 2):
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
                                print(f"    [更新] {domain}.{field} = {merged}")
                                continue

                            if isinstance(current_value, str) and isinstance(value, str) and field.endswith("Note"):
                                merged = _append_text(current_value, value)
                                setattr(domain_model, field, merged)
                                print(f"    [更新] {domain}.{field} = {merged}")
                                continue

                            # 列表类型的合并
                            if isinstance(current_value, list):
                                if domain == "obh" and field == "children":
                                    for item in value:
                                        if isinstance(item, OBHChild):
                                            current_value.append(item)
                                        elif isinstance(item, dict):
                                            current_value.append(OBHChild(**item))
                                    print(f"    [追加] {domain}.{field} += {value}")
                                else:
                                    current_value.extend(value)
                                    print(f"    [追加] {domain}.{field} += {value}")
                            else:
                                setattr(domain_model, field, value)
                                print(f"    [更新] {domain}.{field} = {value}")
                        except Exception as e:
                            msg = e.errors()[0]['msg'] if hasattr(e, 'errors') else str(e)
                            print(f"    [拦截] {domain}.{field} 赋值拦截: {msg}")

        # 2. 更新根级别的字段
        if "root" in patch and patch["root"]:
            for field, value in patch["root"].items():
                setattr(state, field, value)
                print(f"    [更新] 根属性 {field} = {value}")

        # 3. 更新多胎数组
        if "fetusExam" in patch:
            for index, fetus_data in patch["fetusExam"].items():
                if index in state.fetusExam:
                    for k, v in fetus_data.items():
                        setattr(state.fetusExam[index], k, v)
                    print(f"    [更新] 胎儿(Index={index}) 数据 = {fetus_data}")
                else:
                    from schemas import FetusExam
                    state.fetusExam[index] = FetusExam(**fetus_data)
                    print(f"    [新增] 胎儿(Index={index}) 数据 = {fetus_data}")

def parse_input_file(filepath: str):
    """过滤掉空文本的严格文件解析"""
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


def log_performance(total_sessions: int, total_time: float, llm_time: float):
    """写入独立的性能日志文件"""
    qps = total_sessions / total_time if total_time > 0 else 0
    log_content = f"""========================================
性能评估日志 | 实验: {EXP_NAME}_{EXP_TIMESTAMP}
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
    with open(PERF_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(log_content)
    print(f"\n📊 性能日志已写入 {PERF_LOG_FILE}")


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sessions = parse_input_file(INPUT_FILE)
    mock_dov = None

    total_start_time = time.time()
    total_llm_time = 0.0

    engine = PostStructureEngine()

    for idx, session in enumerate(sessions):
        sid = session['session_id']
        text = session['text']
        print(f"\n========== 开始处理 {sid} ({idx + 1}/{len(sessions)}) ==========")

        engine.init_session(sid, mock_dov)

        llm_time = engine.process_session(sid, text)
        total_llm_time += llm_time

        final_state = engine.state_buffer[sid].to_output_dict()

        output_file = os.path.join(OUTPUT_DIR, f"{sid}.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_state, f, ensure_ascii=False, indent=2)

        print(f"✅ {sid} 结构化完成，已保存至: {output_file}")

    total_end_time = time.time()

    log_performance(len(sessions), total_end_time - total_start_time, total_llm_time)