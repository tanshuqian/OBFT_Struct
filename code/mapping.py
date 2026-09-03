import os
import sys
import re

# 动态将 data/res 目录加入 Python 搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
res_dir = os.path.abspath(os.path.join(current_dir, "..", "data", "res"))
if res_dir not in sys.path:
    sys.path.append(res_dir)

from utils import normalize_date, infer_edd_from_gw
from term_dictionary import TERM_REPLACEMENTS
from schemas import StatusDetail
from diagnosis_dic import CATEGORIES_MAPPING
from mapping_dicts import KEY_SYNONYMS
from mapping_dicts import FETUS_FIELD_SYNONYMS
from mapping_dicts import FETAL_POSITION_CN_TO_CODE

# Level 1: 全量静态本体映射
SCHEMA_MAP = {
    # [root] 基础信息与就诊信息
    "会话ID": "root.sessionId",
    "就诊日期": "root.dov",
    "孕周": "root.gwov",
    "年龄": "root.age",
    "预产期年龄": "root.eddAge",
    "BMI": "root.bmi",

    # [OBH] 孕产史核心计数
    "孕次": "root.gravidity",
    "产次": "root.parity",
    # OBH 事件级字段已由 _is_obh_key + _parse_obh_event_entries 统一处理，不再走 SCHEMA_MAP
    "胎数": "obh.fetalcount",
    "分娩医院": "obh.hospital",
    "其他异常情况说明": "obh.exceptionalcase",

    # [HPI] 现病史/本孕相关
    "末次月经": "hpi.lmp",
    "预产期": "hpi.edd",
    "核定预产期": "hpi.sureEdd",
    "受孕方式": "hpi.conceiveMode",
    "受孕方式其他备注": "hpi.conceiveModeNote",
    "主诉": "hpi.chiefcomplaint",
    "现病史备注": "hpi.otherNote",
    "症状": "hpi.otherNote",

    # [PMH] 既往史/疾病史
    "高血压": "pmh.hypertension",
    "糖尿病": "pmh.diabetes",
    "心脏病": "pmh.cardiacDisease",
    "甲状腺": "pmh.thyroidDisease",
    "药物过敏史": "pmh.allergyDrug",
    "食物过敏史": "pmh.allergyFood",
    "其他过敏史": "pmh.allergyOther",
    "输血史": "pmh.transfusionHistory",
    "手术史": "pmh.operationHistory",
    "其他既往史": "pmh.otherNote",

    # [FH] 家族史
    "家族高血压": "fh.hypertension",
    "家族糖尿病": "fh.diabetes",
    "家族出生缺陷": "fh.birthdefects",
    "家族畸形": "fh.birthdefects",
    "遗传病史": "fh.heritableDisease",
    "遗传性疾病": "fh.heritableDisease",
    "家族史补充": "fh.otherNote",

    # [Additional History] 月经及婚育史
    "月经初潮": "additional_medical_history.menarche",
    "月经周期": "additional_medical_history.menstrualCycle",
    "月经经期": "additional_medical_history.menstrualPeriod",
    "月经量": "additional_medical_history.menstrualVolume",
    "痛经": "additional_medical_history.dysmenorrhea",
    "婚姻状况": "additional_medical_history.maritalStatus",
    "婚龄": "additional_medical_history.maritalYears",
    "近亲婚配": "additional_medical_history.nearRelation",

    # [Personal History] 个人史
    "吸烟史": "personal_history.smoke",
    "饮酒史": "personal_history.alcohol",
    "有害物质接触": "personal_history.hazardoussubstances",
    "放射性接触": "personal_history.radioactivity",
    "孕期用药史": "personal_history.medicine",
    "其他个人史": "personal_history.otherNote",
    "个人史补充": "personal_history.otherNote",

    # [Physical Exam] 体格检查（数值）
    "收缩压": "physicalExamination.systolic",
    "舒张压": "physicalExamination.diastolic",
    "身高": "physicalExamination.preheight",
    "孕前体重": "physicalExamination.preweight",
    # [Physical Exam] 体格检查（系统）
    "脉搏": "physicalExamination.pulse",
    "心率": "physicalExamination.heartrate",
    "体重": "physicalExamination.weight",
    "皮肤": "physicalExamination.skin",
    "甲状腺触诊": "physicalExamination.thyroid",
    "乳房": "physicalExamination.breast",
    "呼吸系统": "physicalExamination.respiratory",
    "啰音": "physicalExamination.rales",
    "心律": "physicalExamination.heartrhythm",
    "杂音": "physicalExamination.murmurs",
    "肝脏": "physicalExamination.liver",
    "脾脏": "physicalExamination.spleen",
    "脊柱": "physicalExamination.spine",
    "生理反射": "physicalExamination.physiologicalreflection",
    "病理反射": "physicalExamination.pathologicalreflection",
    "水肿": "physicalExamination.edema",
    "体格检查备注": "physicalExamination.otherNote",

    # [Gynecological Exam] 产科/妇科检查
    "腹围": "gynecologicalExamination.waistHip",
    "妇科检查备注": "gynecologicalExamination.otherNote",

    # [Advice] 医嘱/预约
        "医嘱": "advice.prescription",
        "处方": "advice.prescription",
        "检查开立": "advice.exam",
        "随访周期": "advice.appointmentCycle",
        "预约类型": "advice.appointmentType",
        "预约具体日期": "advice.appointmentDate",
        "预约时段": "advice.appointmentPeriod",
        "建议复诊日期": "advice.visitDate",
        "接诊医生": "advice.doctorName",
        "复诊周期": "advice.appointmentCycle",
        "预约日期": "advice.appointmentDate",
        "复诊日期": "advice.visitDate",
        "医生姓名": "advice.doctorName"
}


def _expand_schema_map(schema_map: dict) -> dict:
    expanded = dict(schema_map)
    for path, aliases in KEY_SYNONYMS.items():
        for alias in aliases:
            expanded[alias] = path
    return expanded


SCHEMA_MAP_EXPANDED = _expand_schema_map(SCHEMA_MAP)

# 未命中 SCHEMA_MAP 时的兜底路由：按 CATEGORIES_MAPPING 判定领域 + 记录到 *Note
CATEGORY_TO_NODE = {
    '1. 核心孕产指标 (OBH)': ('hpi', 'otherNote'),
    '2. 现病史 (HPI)': ('hpi', 'otherNote'),
    '3. 既往史 (PMH)': ('pmh', 'otherNote'),
    '4. 月经及婚育史 (Additional History)': ('additional_medical_history', 'otherNote'),
    '5a. 个人史 (Personal)': ('personal_history', 'otherNote'),
    '5b. 家族史 (Family)': ('fh', 'otherNote'),
    '5. 个人史与家族史 (Personal & Family)': ('personal_history', 'otherNote'),
    '6. 全身体格检查 (Physical Exam)': ('physicalExamination', 'otherNote'),
    '7. 产科/妇科专科检查 (Gynecological Exam)': ('gynecologicalExamination', 'otherNote')
}


def find_domain_by_dict(key: str) -> tuple:
    for category, keywords in CATEGORIES_MAPPING.items():
        for kw in keywords:
            if kw in key:
                if category == '5. 个人史与家族史 (Personal & Family)':
                    if any(token in key for token in ("家族", "父", "母", "兄", "弟", "姐", "妹")):
                        return ('fh', 'otherNote')
                    return ('personal_history', 'otherNote')
                return CATEGORY_TO_NODE.get(category, ('hpi', 'otherNote'))
    return ('hpi', 'otherNote')


def _strip_patient_prefix(text: str) -> str:
    if not text:
        return text
    if text.startswith("患者"):
        return text[2:]
    return text


def _format_details_family(value_text: str, term_text: str) -> str:
    negative_vals = ("否认", "无", "没有", "未见", "不", "否")
    clean_term = _strip_patient_prefix(term_text or "")

    def _add_shi(text: str) -> str:
        return text if text.endswith("史") else f"{text}史"

    def _normalize_family_text(text: str) -> str:
        if not text:
            return text
        normalized = text
        normalized = normalized.replace("家族糖尿病病史", "家族糖尿病史")
        # 保留"家族高血压病史"以对齐标准
        normalized = normalized.replace("家族高血压史", "家族高血压病史")
        return normalized

    if not clean_term and value_text:
        return value_text
    if not clean_term:
        return clean_term

    if any(n in value_text for n in negative_vals):
        if clean_term.startswith(negative_vals) or "否认" in clean_term:
            return _normalize_family_text(clean_term)
        cleaned_inner = clean_term
        for neg in negative_vals:
            cleaned_inner = cleaned_inner.replace(neg, "")
        return _normalize_family_text(f"否认{_add_shi(cleaned_inner)}")

    if value_text in ("存在", "有", "患", "确诊"):
        if value_text in clean_term:
            return _normalize_family_text(_add_shi(clean_term) if "家族" in clean_term else clean_term)
        return _normalize_family_text(clean_term)

    if value_text and clean_term:
        if value_text in clean_term:
            return _normalize_family_text(_add_shi(clean_term) if "家族" in clean_term else clean_term)
        return _normalize_family_text(f"{value_text}{clean_term}")

    return _normalize_family_text(clean_term)


def _clean_complaint_text(text: str) -> str:
    if not text:
        return text
    cleaned = text
    cleaned = re.sub(r"^(患者本次就诊主要诉求|患者本次就诊为|患者本次就诊|患者出现|患者)", "", cleaned)
    cleaned = cleaned.lstrip("，：:；; ")
    return cleaned


def _normalize_advice_text(text: str) -> str:
    if not text:
        return text
    cleaned = re.sub(r"^(医嘱予|医嘱考虑|医嘱建议|医嘱)", "", text)
    cleaned = re.sub(r"^考虑", "", cleaned)
    return cleaned.strip()


def _normalize_medical_terms(text: str) -> str:
    if not text:
        return text
    normalized = text
    for src, dst in TERM_REPLACEMENTS:
        normalized = normalized.replace(src, dst)
    return normalized


def _normalize_patch_notes(patch_data: dict) -> None:
    note_paths = (
        ("hpi", "otherNote"),
        ("pmh", "otherNote"),
        ("fh", "otherNote"),
        ("physicalExamination", "otherNote"),
        ("gynecologicalExamination", "otherNote"),
        ("additional_medical_history", "otherNote"),
        ("personal_history", "otherNote"),
    )
    for domain, field in note_paths:
        if domain not in patch_data or field not in patch_data[domain]:
            continue
        value = patch_data[domain][field]
        if isinstance(value, list):
            patch_data[domain][field] = [_normalize_medical_terms(item) for item in value]
        elif isinstance(value, str):
            patch_data[domain][field] = _normalize_medical_terms(value)


def _infer_pmh_reason(key: str, val: str, term_text: str) -> str:
    text = f"{key} {val} {term_text}"
    if "甲减" in text:
        return "甲状腺功能减退"
    if "甲状腺" in text:
        return "甲状腺疾病"
    if "高血压" in text:
        return "高血压"
    if "糖尿病" in text:
        return "糖尿病"
    if "贫血" in text:
        return "贫血"
    if "心脏" in text:
        return "心脏病"
    return ""


def _format_medication(val: str, term_text: str, reason: str) -> str:
    if "|" in str(val):
        return str(val)
    if reason and reason not in str(val) and reason not in str(term_text):
        return f"{val}|{reason}"
    return str(val)


def _format_details_patient(value_text: str, term_text: str) -> str:
    """生成患者描述 details，消除双重否定，统一添加"史"后缀。

    例：
      - "否认" + "药物过敏"     → "患者否认药物过敏史"
      - "否认" + "药物过敏史"   → "患者否认药物过敏史"（不重复加"史"）
      - "否认" + "药物不过敏"   → "患者否认药物过敏史"（消除双重否定）
      - "有"   + "青霉素过敏"   → "患者有青霉素过敏"
      - "存在" + "患者孕期高血压病史" → "患者存在妊娠期高血压疾病史"（去重"患者"前缀）
    """
    negative_vals = ("否认", "无", "没有", "未见", "不", "否")
    # 双重否定检测：value含否定词 且 term_text含否定词(如"不过敏"、"无水肿")
    val_is_neg = any(n in value_text for n in negative_vals)
    term_is_neg = any(n in term_text for n in negative_vals) if term_text else False

    # 去除 term_text 中冗余的"患者"前缀（LLM_Truth 格式常见）
    clean_term = term_text
    if term_text and term_text.startswith("患者"):
        clean_term = term_text[2:]

    def _add_shi(text: str) -> str:
        """添加"史"后缀（不重复）"""
        return text if text.endswith("史") else f"{text}史"

    if clean_term and value_text:
        if val_is_neg and term_is_neg:
            # 双重否定 → 去掉term中的否定，保留value的否定
            cleaned_inner = clean_term
            for neg in negative_vals:
                cleaned_inner = cleaned_inner.replace(neg, "")
            return f"患者{value_text}{_add_shi(cleaned_inner)}"
        if val_is_neg:
            return f"患者{value_text}{_add_shi(clean_term)}"
        # 肯定词去重：value 是 "存在"/"有" 等且 term 已含该词时，不重复拼接
        positive_vals = ("存在", "有", "患", "确诊")
        if any(value_text == pv for pv in positive_vals) and value_text in clean_term:
            return f"患者{_add_shi(clean_term)}"
        # 如果 value_text 的内容已包含在 term 中，优先使用 term
        if value_text in clean_term:
            return f"患者{_add_shi(clean_term)}"
        # 非否定：value + term（去掉冗余"患者"前缀后拼接）
        return f"患者{value_text}{clean_term}"
    if clean_term:
        if term_is_neg:
            cleaned_inner = clean_term
            for neg in negative_vals:
                cleaned_inner = cleaned_inner.replace(neg, "")
            return f"患者无{_add_shi(cleaned_inner)}"
        return f"患者{clean_term}"
    return f"患者{value_text}"


def _format_details_value_term(value_text: str, term_text: str) -> str:
    # 去除 term_text 中冗余的"患者"前缀
    clean_term = term_text
    if term_text and term_text.startswith("患者"):
        clean_term = term_text[2:]

    if not clean_term and value_text:
        return value_text
    if clean_term and value_text:
        negative_terms = ("否认", "无", "没有", "未见", "未", "不", "否", "排除")
        if any(term in value_text for term in negative_terms):
            if "水肿" in clean_term:
                # "否认"+"双下肢无水肿" → "双下肢无水肿"
                # "否认"+"否认双下肢水肿" → "双下肢无水肿"
                result = clean_term
                # 去掉 term 中的否定词
                for neg in negative_terms:
                    result = result.replace(neg, "")
                # 如果去掉否定后变成了肯定（如"双下肢水肿"），加上"无"
                if "无水肿" not in result and "水肿" in result:
                    result = result.replace("水肿", "无水肿")
                return result
            return f"无{clean_term}"
        return f"{value_text}{clean_term}"
    return clean_term or value_text


def _build_status_detail(val: str, term_text: str, key: str, domain: str, field: str) -> StatusDetail:
    text = f"{val} {term_text}".strip()
    negative_terms = ["否认", "无", "没有", "未见", "未", "不", "否", "排除"]
    positive_terms = ["有", "患", "确诊", "阳性", "存在", "提示"]
    is_negative = any(term in text for term in negative_terms)
    is_positive = any(term in text for term in positive_terms)
    status = 0 if is_negative else (1 if is_positive or term_text or val else 1)

    base_term = term_text or key
    # BUG 16: term_text 为通用否定词（"无"）时，用 key 替代，避免生成 "患者否认无"
    if base_term in ("无", "没有", "否") and key:
        base_term = key
    if domain in ("pmh", "personal_history"):
        details = _format_details_patient(val, base_term)
    elif domain == "fh":
        details = _format_details_family(val, base_term)
    elif domain == "physicalExamination" and field == "edema":
        details = _format_details_value_term(val, base_term)
    else:
        details = base_term or str(val)

    if domain == "personal_history" and field == "hazardoussubstances":
        if status == 0:
            details = "患者否认有害化学物质接触史"
        else:
            details = details.replace("接触有毒化学物质", "有害化学物质接触")
            details = details.replace("接触有毒物质", "有害化学物质接触")
            details = details.replace("接触过化学品", "有害化学物质接触")
    if domain == "personal_history" and field == "radioactivity":
        if status == 0:
            details = "患者否认放射性物质接触史"
        else:
            details = details.replace("接触放射物质", "放射性物质接触")
            details = details.replace("接触过放射线", "放射性物质接触")
            details = details.replace("接触放射线", "放射性物质接触")
    if domain == "pmh" and status == 0 and field in ("cardiacDisease", "hypertension", "diabetes", "operationHistory"):
        cleaned = details
        cleaned = cleaned.replace("既往", "").replace("本次妊娠期", "").replace("孕期", "")
        cleaned = cleaned.replace("病病史", "病史")
        if field == "operationHistory":
            cleaned = cleaned.replace("手术史", "手术史")
        elif field == "cardiacDisease":
            cleaned = cleaned.replace("心脏病", "心脏病")
        elif field == "hypertension":
            cleaned = cleaned.replace("高血压", "高血压")
        elif field == "diabetes":
            if "妊娠期糖尿病" in cleaned:
                cleaned = cleaned.replace("糖尿病及妊娠期糖尿病", "糖尿病及妊娠期糖尿病")
                cleaned = cleaned.replace("糖尿病病史", "糖尿病史")
        details = cleaned

    return StatusDetail(status=status, details=_normalize_medical_terms(details))


def _status_from_value(val: str, term_text: str, key: str, domain: str, field: str) -> StatusDetail:
    return _build_status_detail(val, term_text, key, domain, field)


def _parse_number(value: str) -> float:
    digits = ''.join(ch for ch in str(value) if ch.isdigit() or ch == '.')
    if digits.count('.') > 1:
        digits = digits.replace('.', '', digits.count('.') - 1)
    return float(digits) if digits else None


def _parse_int_or_range(value: str) -> int | None:
    """解析整数，支持范围值取平均（如 '28-30' → 29, '5-7天' → 6）"""
    text = str(value).replace("天", "").replace("岁", "").replace("年", "").strip()
    range_match = re.match(r'(\d+)\s*[-~—]\s*(\d+)', text)
    if range_match:
        lo, hi = int(range_match.group(1)), int(range_match.group(2))
        return (lo + hi) // 2
    number = _parse_number(text)
    return int(number) if number is not None else None


def _parse_fetal_count(val: str, term_text: str) -> int | None:
    """胎数类型校验+转换："第一胎"→1、"双胎/双胞胎"→2、纯数字直转；无法解析返回 None。"""
    text = f"{term_text or ''} {val or ''}"
    cn_map = {"一": 1, "单": 1, "双": 2, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
    for cn, num in cn_map.items():
        if f"{cn}胎" in text or f"{cn}胞胎" in text or f"{cn}个宝宝" in text or f"{cn}个胎儿" in text:
            return num
    number = _parse_number(str(val))
    if number is not None:
        n = int(number)
        return n if 1 <= n <= 10 else None
    return None


def _resolve_fetus_index(key: str, fallback_index: int) -> int:
    """根据关键词中的'左/右'确定胎儿索引"""
    if "左" in key:
        return 1
    if "右" in key:
        return 2
    return fallback_index


def _update_fetus_exam(patch_data: dict, index: int, updates: dict):
    current = patch_data["fetusExam"].get(index, {"index": index})
    current.update(updates)
    patch_data["fetusExam"][index] = current


def _match_fetus_field(key: str) -> str:
    for field, terms in FETUS_FIELD_SYNONYMS.items():
        if any(term in key for term in terms):
            return field
    return ""


def _normalize_gwov(value: str) -> str | None:
    """规范化孕周格式为 '周数+天数'（如 '37+4', '42+0'），去除中文"""
    if not value:
        return None
    text = str(value).strip()

    # 先提取中文格式 "36周2天" / "37周加2天" → 周数+天数
    cn_match = re.match(r'(\d+)\s*周\s*(?:加\s*)?(\d+)\s*天?', text)
    if cn_match:
        weeks = int(cn_match.group(1))
        days = int(cn_match.group(2))
        return f"{weeks}+{days}"

    # 纯中文格式 "42周" → "42+0"
    cn_week_only = re.match(r'(\d+)\s*周$', text)
    if cn_week_only:
        weeks = int(cn_week_only.group(1))
        return f"{weeks}+0"

    # 去除中文后再匹配 W+D 格式
    text_clean = text.replace("周", "").replace("天", "").replace("加", "+").strip()
    # 匹配 W+D 格式（如 "37+4" 或 "37 + 4"）
    match = re.match(r'(\d+)\s*\+\s*(\d+)', text_clean)
    if match:
        weeks = int(match.group(1))
        days = int(match.group(2))
        return f"{weeks}+{days}"
    # 纯数字视为周数（如 "37" → "37+0"）
    match = re.match(r'(\d+)$', text_clean)
    if match:
        weeks = int(match.group(1))
        # 纯数字≤40视为周数，>40可能是异常合并值，直接返回原文
        if weeks <= 45:
            return f"{weeks}+0"
    return str(value)


def _append_text(existing: str, incoming: str) -> str:
    if not existing:
        return incoming
    if incoming and incoming not in existing:
        return f"{existing}；{incoming}"
    return existing


def _has_status(patch_data: dict, domain: str, field: str) -> bool:
    """检查某字段是否已被设置过非默认值（非-1）"""
    existing = patch_data.get(domain, {}).get(field)
    if existing is None:
        return False
    if isinstance(existing, StatusDetail):
        return existing.status != -1
    return True


def _apply_status_with_note(patch_data: dict, domain: str, field: str, status_detail: StatusDetail):
    patch_data[domain][field] = status_detail
    # Do not auto-fill note fields; only set *Note when an explicit note is provided.


def _update_obh_child(patch_data: dict, updates: dict):
    current = patch_data["obh"].get("children")
    if not current:
        patch_data["obh"]["children"] = [updates]
        return
    if isinstance(current, list) and current:
        merged = dict(current[0])
        merged.update(updates)
        current[0] = merged


def _contains_any(text: str, terms: tuple) -> bool:
    return any(term in text for term in terms)


def _is_negated(text: str) -> bool:
    negative_terms = ("否认", "无", "没有", "未见", "未", "不", "否", "排除")
    return _contains_any(text, negative_terms)


def _is_current_context(text: str) -> bool:
    current_terms = ("现", "目前", "现在", "孕期", "妊娠期", "这次", "本次", "本孕", "服药", "用药", "在吃", "一直吃", "长期")
    past_terms = ("既往", "既往史", "以前", "曾", "史")
    if _contains_any(text, past_terms):
        return False
    return _contains_any(text, current_terms)


def _format_hpi_condition_note(label: str, detail: str) -> str:
    detail = _normalize_medical_terms(detail)
    if not detail:
        return label
    if label in detail:
        return detail
    return f"{label}：{detail}"


KEY_ALIAS_OVERRIDES = {
    "接触有害化学物质或放射线": "有害物质接触",
    "接触有害物质": "有害物质接触",
    "接触有害物质史": "有害物质接触",
    "接触放射线": "放射性接触",
    "放射线接触": "放射性接触",
}


# OBH 事件关键词：用于判定是否需要按"每次提及一条"生成孕产史记录
OBH_EVENT_TERMS = (
    "顺产", "阴道分娩", "剖宫产", "流产", "人工流产", "药物流产", "引产", "死胎", "早产", "足月",
    "产钳", "负压", "臀位", "产后出血", "产褥热", "清宫", "刮宫", "生化"
)

OBH_CONTEXT_KEY_TERMS = (
    "孕产史", "产史", "孕史", "妊娠史", "生育史", "分娩史",
    "孕次", "产次", "顺产史", "剖宫产史", "流产史",
    "流产方式", "分娩方式", "孕产时间"
)


def _is_obh_key(key: str) -> bool:
    if not key:
        return False
    return any(term in key for term in OBH_CONTEXT_KEY_TERMS) or any(term in key for term in OBH_EVENT_TERMS)


def _extract_year_month(text: str) -> tuple[str | None, str | None]:
    # 规则：提取到的年/月统一转为字符串，避免 OBHEntry(year/month) 类型校验失败
    if not text:
        return None, None
    year_match = re.search(r"(19|20)\d{2}", text)
    month_match = re.search(r"(\d{1,2})月", text)
    year = year_match.group(0) if year_match else None
    month = month_match.group(1) if month_match else None
    return year, month


def _extract_event_count(text: str, val: str) -> int:
    # 次数解析：优先 value；再看"x次/一次/两次"等，避免把年份误识别成次数
    number = _parse_number(val)
    if number is not None:
        count = int(number)
        # 年份保护：如果 value 是 4 位年份数字（如 "2018年"），不应当作次数
        if count > 100:
            return 1
        return count if count > 0 else 0

    if not text:
        return 1

    digit_count = re.search(r"(\d+)\s*次", text)
    if digit_count:
        c = int(digit_count.group(1))
        if c > 100:
            return 1
        return c

    cn_count_map = {
        "一次": 1,
        "两次": 2,
        "二次": 2,
        "三次": 3,
        "四次": 4,
        "五次": 5,
    }
    # 避免"第X次"这种序数词被误识别为次数（如"第四次妊娠"≠4次）
    ordinal_match = re.search(r'第[一二三四五六七八九十\d]+次', text)
    for token, count in cn_count_map.items():
        # 如果token出现在"第X次"语境中，跳过
        if token in text:
            if ordinal_match and f"第{token}" in text:
                continue
            return count

    return 1


def _new_obh_entry(index: int, exceptionalcase: str, year: str | None, month: str | None) -> dict:
    # 规则：先生成空表，再按事件字段填值（符合"先生成列表，再填表"的写入方式）
    return {
        "gravidityindex": index,
        "year": year,
        "month": month,
        "vaginalDelivery": None,
        "cesareanSection": None,
        "naturalAbortion": None,
        "medicalAbortion": None,
        "surgicalAbortion": None,
        "currettageAbortion": None,
        "currettage": None,
        "biochemicalAbortion": None,
        "inducedLabor": None,
        "fetusdeath": None,
        "preterm": None,
        "term": None,
        "forceps": None,
        "vacuumAssisted": None,
        "breechMidwifery": None,
        "hemorrhage": None,
        "puerperalFever": None,
        "fetalcount": 1,
        "hospital": None,
        "exceptionalcase": exceptionalcase,
        "children": []
    }


def _detect_obh_event_field(text: str) -> str:
    # 事件字段识别：按最具体词优先，避免"人工流产"被"流产"提前命中
    if "人工流产" in text:
        return "surgicalAbortion"
    if "药物流产" in text:
        return "medicalAbortion"
    if "剖宫产" in text:
        return "cesareanSection"
    if "阴道分娩" in text or "顺产" in text:
        return "vaginalDelivery"
    if "引产" in text:
        return "inducedLabor"
    if "死胎" in text:
        return "fetusdeath"
    if "早产" in text:
        return "preterm"
    if "足月" in text:
        return "term"
    if "产钳" in text:
        return "forceps"
    if "负压" in text or "吸引" in text:
        return "vacuumAssisted"
    if "臀位" in text:
        return "breechMidwifery"
    if "产后出血" in text:
        return "hemorrhage"
    if "产褥热" in text:
        return "puerperalFever"
    if "清宫" in text:
        return "currettage"
    if "刮宫" in text:
        return "currettageAbortion"
    if "生化" in text:
        return "biochemicalAbortion"
    if "流产" in text:
        # 未指明方式时，默认记为自然流产
        return "naturalAbortion"
    return ""


def _parse_obh_event_entries(key: str, term_text: str, val: str, raw: str, start_index: int) -> tuple[list[dict], int]:
    # 规则：每出现一次事件先生成一条 OBH 记录，index 自增（先生成列表，再填表）
    source_text = _normalize_medical_terms(f"{key} {term_text} {raw}")
    if not _contains_any(source_text, OBH_EVENT_TERMS):
        return [], start_index

    # 规则：term_text 含"次数"等计数型描述时，不创建事件条目（如"患者既往剖宫产次数" value="1"）
    # 仅当 key 为"分娩方式"且 term 描述的是某种方式的次数（而非事件本身）时适用
    if key == "分娩方式" and _contains_any(source_text, ("次数",)) and re.match(r'^\d+$', str(val).strip()):
        return [], start_index

    # 规则：否定或显式 0 次不生成条目（如"没有流产过""流产次数=0"）
    if _is_negated(source_text) or str(val).strip() in ("0", "0次", "零"):
        return [], start_index

    # 规则：按分号分段，保证一条事实内的多事件独立成条
    segments = [seg.strip() for seg in re.split(r"[；;]", source_text) if seg.strip()]
    if not segments:
        return [], start_index

    entries: list[dict] = []
    next_index = start_index

    for segment in segments:
        field = _detect_obh_event_field(segment)
        if not field:
            continue

        # 规则：优先使用 value 或文本次数，确保"流产次数=2"拆成 2 条
        # 多段时 val 是总数（如"孕4"），不应作为每段的事件次数；单段时 val 可表示该事件次数
        if len(segments) > 1:
            count = _extract_event_count(segment, "")
        else:
            count = _extract_event_count(segment, str(val))
        if count <= 0:
            continue

        year, month = _extract_year_month(segment)
        exceptionalcase = raw or term_text or key
        if len(segments) > 1:
            exceptionalcase = segment

        # 规则：先生成空表，再逐条填值，确保每次提及独立成条
        for _ in range(count):
            entry = _new_obh_entry(next_index, exceptionalcase, year, month)
            entry[field] = 1

            # 规则：出现"第一胎/第二胎/一个宝宝"等语义时，显式写 fetalcount=1
            if _contains_any(segment, ("第一胎", "第二胎", "第三胎", "第四胎", "一胎", "一个宝宝")):
                entry["fetalcount"] = 1

            # 规则：18 三体记录到 children.sequelaNote
            if _contains_any(segment, ("18三体", "三体综合征")):
                entry["children"].append({"sequelaNote": "胎儿18三体综合征"})

            entries.append(entry)
            next_index += 1

    return entries, next_index


def _parse_obh_entries_from_text(text: str) -> list[dict]:
    if not text:
        return []
    if "年" not in text:
        return []
    if not any(token in text for token in ("第一胎", "第二胎", "第三胎", "顺产", "阴道分娩", "剖宫产", "人工流产", "流产")):
        return []
    entries = []
    for idx, part in enumerate([p.strip() for p in text.split("；") if p.strip()], start=1):
        if "年" not in part:
            continue
        entry = {
            "gravidityindex": idx,
            "exceptionalcase": part,
            "fetalcount": 1
        }
        if "阴道分娩" in part or "顺产" in part:
            entry["vaginalDelivery"] = 1
        if "剖宫产" in part:
            entry["cesareanSection"] = 1
        if "人工流产" in part:
            entry["surgicalAbortion"] = 1
        elif "流产" in part:
            entry["naturalAbortion"] = 1
        year_digits = "".join(ch for ch in part if ch.isdigit())
        if len(year_digits) >= 4:
            # 规则：OBHEntry.year 定义为字符串，避免 pydantic 校验失败
            entry["year"] = year_digits[:4]
        entries.append(entry)
    return entries


def route_and_transform(extracted_tags: list, dov: str) -> dict:
    # 规则映射主入口：
    # 1) 初始化 patch_data
    # 2) 特殊规则优先（过敏/糖尿病/贫血/甲状腺/胎心与胎儿字段/OBH 文字解析）
    # 3) SCHEMA_MAP 精确映射
    # 4) CATEGORY_TO_NODE 兜底路由到 *Note
    # 5) 字段类型转换与 StatusDetail 生成
    patch_data = {
        "root": {}, "obh": {}, "hpi": {}, "pmh": {}, "fh": {},
        "physicalExamination": {}, "gynecologicalExamination": {},
        "additional_medical_history": {}, "personal_history": {},
        "fetusExam": {}, "advice": {}, "obh_entries": []
    }

    dynamic_fetus_idx = 1

    list_fields = set()
    # 字段类型规则：数值/日期/状态类字段，便于集中调整
    int_fields = {
        "gravidity", "parity",
        "age", "eddAge", "systolic", "diastolic", "systolic2", "diastolic2",
        "systolic3", "diastolic3", "pulse", "heartrate", "fetalHeartRate",
        "menarche", "menstrualCycle", "menstrualPeriod", "maritalYears",
        "appointmentCycle"
    }
    float_fields = {"preheight", "preweight", "weight", "bmi", "fundalHeight", "waistHip"}
    date_fields = {"edd", "sureEdd", "lmp", "appointmentDate", "visitDate"}
    status_fields = {
        ("pmh", "hypertension"), ("pmh", "diabetes"), ("pmh", "cardiacDisease"),
        ("pmh", "thyroidDisease"),
        ("pmh", "operationHistory"), ("pmh", "allergyDrug"), ("pmh", "allergyFood"),
        ("pmh", "allergyOther"), ("pmh", "transfusionHistory"),
        ("fh", "hypertension"), ("fh", "diabetes"), ("fh", "birthdefects"),
        ("fh", "heritableDisease"),
        ("personal_history", "smoke"), ("personal_history", "alcohol"),
        ("personal_history", "hazardoussubstances"), ("personal_history", "radioactivity"),
        ("additional_medical_history", "dysmenorrhea"), ("additional_medical_history", "nearRelation"),
        ("physicalExamination", "skin"), ("physicalExamination", "thyroid"),
        ("physicalExamination", "breast"), ("physicalExamination", "respiratory"),
        ("physicalExamination", "rales"), ("physicalExamination", "heartrhythm"),
        ("physicalExamination", "murmurs"), ("physicalExamination", "liver"),
        ("physicalExamination", "spleen"), ("physicalExamination", "spine"),
        ("physicalExamination", "physiologicalreflection"), ("physicalExamination", "pathologicalreflection"),
        ("physicalExamination", "edema"),
    }

    last_pmh_reason = ""
    # OBH 事件索引：事件级写入时按生成顺序自增
    obh_index = 1

    for tag in extracted_tags:
        key = tag.get("key", "").replace('\ue000', '')
        val = tag.get("value", "")
        term_text = tag.get("term", "")
        raw_text = tag.get("raw", "")

        key = _normalize_medical_terms(key)
        if isinstance(val, str):
            val = _normalize_medical_terms(val)
        if isinstance(term_text, str):
            term_text = _normalize_medical_terms(term_text)
        if isinstance(raw_text, str):
            raw_text = _normalize_medical_terms(raw_text)

        if key == "个人史" and term_text:
            key = term_text

        if key == "既往史" and term_text:
            key = term_text

        pre_alias_key = key
        key = KEY_ALIAS_OVERRIDES.get(key, key)

        normalized_text = _normalize_medical_terms(f"{key} {term_text} {val}")

        # 规则分块：器官体征/水肿兜底
        edema_text = f"{key} {term_text} {raw_text}"
        if "水肿" in edema_text and key in ("器官体征", "体征", "水肿", "双下肢水肿"):
            if not _has_status(patch_data, "physicalExamination", "edema"):
                sd = _status_from_value(val, term_text or "水肿", key, "physicalExamination", "edema")
                _apply_status_with_note(patch_data, "physicalExamination", "edema", sd)
            continue

        # 规则分块：胎儿体重估计 → 体格检查备注
        if key in ("新生儿情况", "胎儿体重估计") or "胎儿体重估计" in str(term_text) or "预估胎儿体重" in str(term_text):
            note_val = val or term_text or raw_text
            if note_val:
                note_text = str(note_val)
                if "胎儿体重" not in note_text:
                    note_text = f"预估胎儿体重{note_text}"
                patch_data["physicalExamination"]["otherNote"] = _append_text(
                    patch_data["physicalExamination"].get("otherNote"), note_text)
            continue

        # 规则分块：有害物质+放射性合并项拆分（"接触有害化学物质或放射线"需同时设置两个字段）
        if pre_alias_key == "接触有害化学物质或放射线":
            sd_haz = _status_from_value(val, "有害物质接触", pre_alias_key, "personal_history", "hazardoussubstances")
            _apply_status_with_note(patch_data, "personal_history", "hazardoussubstances", sd_haz)
            sd_rad = _status_from_value(val, "放射性接触", pre_alias_key, "personal_history", "radioactivity")
            _apply_status_with_note(patch_data, "personal_history", "radioactivity", sd_rad)
            continue

        # 规则分块：孕产史胎儿体重写入 OBH child
        if key == "胎儿体重" and "孕产史" in str(term_text):
            weight_value = val or raw_text or term_text
            _update_obh_child(patch_data, {"neonateWeight": str(weight_value)})
            continue

        # 规则分块：孕产时间 → 仅为最新 OBH 条目补充 year/month，不创建新条目
        if key == "孕产时间":
            year, month = _extract_year_month(f"{term_text} {val} {raw_text}")
            if year and patch_data["obh_entries"]:
                last_entry = patch_data["obh_entries"][-1]
                if not last_entry.get("year"):
                    last_entry["year"] = year
                if month and not last_entry.get("month"):
                    last_entry["month"] = month
            continue

        # 规则分块：OBH 事件级写入（每次提及独立成条）
        if _is_obh_key(key):
            # 孕次/产次/流产次数等计数型 key 优先走 SCHEMA_MAP，不从 raw 中提取事件
            _count_only_keys = ("孕次", "产次", "流产次数")
            if key in _count_only_keys and key in SCHEMA_MAP_EXPANDED:
                pass  # 落入 SCHEMA_MAP 处理
            else:
                event_entries, obh_index = _parse_obh_event_entries(key, term_text, str(val), raw_text, obh_index)
                if event_entries:
                    patch_data["obh_entries"].extend(event_entries)
                    continue
                # 仅当 key 没有 SCHEMA_MAP 下游映射时才消费（如"流产次数=0"），
                # 否则让"孕次"/"产次"等落入 SCHEMA_MAP
                if key not in SCHEMA_MAP_EXPANDED:
                    continue

        # 规则分块：OBH 文本补充解析（保留原有兼容逻辑）
        obh_entries = _parse_obh_entries_from_text(term_text)
        if obh_entries:
            patch_data["obh_entries"].extend(obh_entries)
            continue

        # 规则分块：过敏相关直接写入 pmh 的 StatusDetail
        # 核心规则：
        #   - 通用否认过敏（"过敏史=否认"）→ 联动设置 allergyDrug/allergyFood/allergyOther 全部=0
        #   - 单项过敏（药物/食物）→ 仅设置对应项，不联动其余（保持-1表示未询问）
        if "过敏" in key or "过敏" in term_text:
            is_negated_allergy = _is_negated(normalized_text)
            if "药" in key or "药" in term_text:
                _apply_status_with_note(
                    patch_data, "pmh", "allergyDrug",
                    _build_status_detail(val, term_text, key, "pmh", "allergyDrug")
                )
            elif "食" in key or "食" in term_text:
                _apply_status_with_note(
                    patch_data, "pmh", "allergyFood",
                    _build_status_detail(val, term_text, key, "pmh", "allergyFood")
                )
            elif is_negated_allergy:
                # 通用否认过敏 → 同时否认药物过敏、食物过敏和其他过敏
                _apply_status_with_note(patch_data, "pmh", "allergyDrug",
                    StatusDetail(status=0, details="患者否认药物过敏史"))
                _apply_status_with_note(patch_data, "pmh", "allergyFood",
                    StatusDetail(status=0, details="患者否认食物过敏史"))
                _apply_status_with_note(patch_data, "pmh", "allergyOther",
                    StatusDetail(status=0, details="患者否认其他过敏史"))
            else:
                # 通用确认过敏（非药物/食物）→ 写入allergyOther
                _apply_status_with_note(
                    patch_data, "pmh", "allergyOther",
                    _build_status_detail(val, term_text, key, "pmh", "allergyOther")
                )
            continue

        # 规则分块：糖尿病/GDM
        # 核心规则：pmh.diabetes 仅记录孕前糖尿病；GDM（妊娠期糖尿病）一律写入 hpi.otherNote
        # 产科联动：否认"糖尿病"或"妊娠期糖尿病"任一项时，语义上两者都否认
        is_gdm_context = ("妊娠期糖尿病" in str(val) or "妊娠期糖尿病" in str(term_text)
                          or "GDM" in str(val) or "GDM" in str(term_text))
        if key == "糖尿病" and is_gdm_context:
            if _is_negated(normalized_text):
                # 否认GDM → 如果diabetes已被设置且含"糖尿病及妊娠期糖尿病"，保留现有值
                # 否则产科联动：否认GDM等同于同时否认孕前糖尿病
                existing = patch_data.get("pmh", {}).get("diabetes")
                if isinstance(existing, StatusDetail) and existing.status == 0 and "糖尿病及妊娠期糖尿病" in (existing.details or ""):
                    pass  # 已由SCHEMA_MAP联动设置，保留
                else:
                    _apply_status_with_note(patch_data, "pmh", "diabetes",
                        StatusDetail(status=0, details="患者否认糖尿病及妊娠期糖尿病史"))
            else:
                # 确诊GDM → 写入hpi.otherNote，同时标记pmh.diabetes=0（否认孕前糖尿病）
                note = _format_hpi_condition_note("妊娠期糖尿病", str(term_text or val))
                patch_data["hpi"]["otherNote"] = _append_text(patch_data["hpi"].get("otherNote"), note)
                _apply_status_with_note(patch_data, "pmh", "diabetes",
                    StatusDetail(status=0, details="患者否认孕前糖尿病史"))
            continue
        if key == "妊娠期糖尿病" or key == "GDM":
            if _is_negated(normalized_text):
                # 否认GDM → 产科联动：同时否认孕前糖尿病
                existing = patch_data.get("pmh", {}).get("diabetes")
                if isinstance(existing, StatusDetail) and existing.status == 0 and "糖尿病及妊娠期糖尿病" in (existing.details or ""):
                    pass  # 已设置，保留
                else:
                    _apply_status_with_note(patch_data, "pmh", "diabetes",
                        StatusDetail(status=0, details="患者否认糖尿病及妊娠期糖尿病史"))
            else:
                note = _format_hpi_condition_note("妊娠期糖尿病", str(term_text or val))
                patch_data["hpi"]["otherNote"] = _append_text(patch_data["hpi"].get("otherNote"), note)
                _apply_status_with_note(patch_data, "pmh", "diabetes",
                    StatusDetail(status=0, details="患者否认孕前糖尿病史"))
            continue

        blood_sugar_terms = ("妊娠期糖尿病", "GDM", "高血糖", "血糖高", "血糖异常")
        if _contains_any(normalized_text, blood_sugar_terms) and _is_negated(normalized_text):
            _apply_status_with_note(
                patch_data,
                "pmh",
                "diabetes",
                _status_from_value("否认", term_text or "妊娠期糖尿病", key, "pmh", "diabetes")
            )
            continue
        if _contains_any(normalized_text, blood_sugar_terms):
            note = _format_hpi_condition_note("妊娠期糖尿病", str(term_text or val))
            patch_data["hpi"]["otherNote"] = _append_text(patch_data["hpi"].get("otherNote"), note)
            _apply_status_with_note(patch_data, "pmh", "diabetes",
                _status_from_value("否认", "孕前糖尿病", key, "pmh", "diabetes"))
            continue

        # 规则分块：贫血（仅写入 HPI 备注）
        anemia_terms = ("贫血",)
        if _contains_any(normalized_text, anemia_terms) and not _is_negated(normalized_text):
            detail = term_text or key
            if val and val not in ("存在", "否认"):
                detail = f"{detail}（{val}）"
            patch_data["hpi"]["otherNote"] = _append_text(patch_data["hpi"].get("otherNote"), detail)
            continue

        # 规则分块：甲状腺（孕期优先 HPI，否则写 PMH 备注）
        thyroid_terms = ("甲状腺", "甲减", "甲亢", "甲状腺疾病", "甲状腺功能减退", "甲状腺功能亢进")
        if _contains_any(normalized_text, thyroid_terms) and _is_current_context(normalized_text) and not _is_negated(normalized_text):
            if "甲减" in normalized_text or "甲状腺功能减退" in normalized_text:
                label = "甲状腺功能减退"
            elif "甲亢" in normalized_text or "甲状腺功能亢进" in normalized_text:
                label = "甲状腺功能亢进"
            else:
                label = "甲状腺疾病"
            note = _format_hpi_condition_note(label, str(term_text or val))
            patch_data["hpi"]["otherNote"] = _append_text(patch_data["hpi"].get("otherNote"), note)
            continue
        if _contains_any(normalized_text, thyroid_terms) and not _is_negated(normalized_text):
            _apply_status_with_note(
                patch_data, "pmh", "thyroidDisease",
                _status_from_value(val, term_text or "甲状腺疾病", key, "pmh", "thyroidDisease")
            )
            continue

        if not _is_negated(normalized_text):
            inferred_reason = _infer_pmh_reason(key, str(val), str(term_text))
            if inferred_reason:
                last_pmh_reason = inferred_reason

        if "未提及" in str(val) or "未提供" in str(val):
            continue

        # [特殊规则] 胎心
        if "胎心" in key:
            index = _resolve_fetus_index(key, dynamic_fetus_idx)
            # 尝试从 val 中提取数值心率
            try:
                val_int = int(''.join(filter(str.isdigit, str(val))))
                if val_int < 60:  # 合理心率范围外视为定性描述
                    raise ValueError
                _update_fetus_exam(patch_data, index, {"fetalHeartRate": val_int})
                if "左" not in key and "右" not in key:
                    dynamic_fetus_idx += 1
            except (ValueError, TypeError):
                # 定性胎心（如"正常"）不建胎儿条目，保留至现病史备注，避免事实丢失
                note = str(term_text or "")
                if note and note not in ("存在", "正常", "未见异常", "无异常"):
                    patch_data["hpi"]["otherNote"] = _append_text(
                        patch_data["hpi"].get("otherNote"), note)
            continue

        # [特殊规则] 胎儿结构字段
        fetus_field = _match_fetus_field(key)
        if fetus_field:
            index = _resolve_fetus_index(key, 1)
            # 通用描述词黑名单：term_text 含这些时不应作为具体值
            _generic_terms = ("本次妊娠", "情况", "患者", "如", "检查", "存在", "正常", "胎位正", "胎位正常", "位置很正")

            if fetus_field == "fetalPosition":
                # 尝试从 val 提取专业缩写代码
                fp_code = None
                fp_code_match = re.search(r'\b([LR](?:Sc|O|S|M)(?:A|P|T))\b', str(val), re.IGNORECASE)
                if fp_code_match:
                    fp_code = fp_code_match.group(1).upper()
                # 从中文推算缩写
                if not fp_code:
                    for cn_name, code in FETAL_POSITION_CN_TO_CODE.items():
                        if cn_name in str(val) or cn_name in str(term_text) or cn_name in str(raw_text):
                            fp_code = code
                            break
                updates = {}
                if fp_code:
                    updates["fetalPosition"] = fp_code
                # 确定 position 中文值：排除通用描述
                cn_pos = None
                for source in [str(val), str(term_text), str(raw_text)]:
                    for cn_name in FETAL_POSITION_CN_TO_CODE:
                        if cn_name in source:
                            cn_pos = cn_name + "位"
                            break
                    if cn_pos:
                        break
                # term_text 非通用描述时优先使用
                if not cn_pos and term_text and not any(t in term_text for t in _generic_terms):
                    cn_pos = term_text
                if cn_pos:
                    updates["position"] = cn_pos
                elif not fp_code:
                    if str(val) not in _generic_terms:
                        updates["fetalPosition"] = val
                _update_fetus_exam(patch_data, index, updates)
            elif fetus_field == "position":
                # 尝试从 raw_text / val 提取专业缩写代码
                fp_code = None
                fp_code_match = re.search(r'\b([LR](?:Sc|O|S|M)(?:A|P|T))\b',
                                          f"{val} {raw_text}", re.IGNORECASE)
                if fp_code_match:
                    fp_code = fp_code_match.group(1).upper()
                # 从中文推算缩写
                if not fp_code:
                    for cn_name, code in FETAL_POSITION_CN_TO_CODE.items():
                        if cn_name in str(term_text) or cn_name in str(val) or cn_name in str(raw_text):
                            fp_code = code
                            break
                updates = {}
                if fp_code:
                    updates["fetalPosition"] = fp_code
                # 确定 position 中文值：排除通用描述
                pos_val = None
                for source in [str(val), str(term_text), str(raw_text)]:
                    for cn_name in FETAL_POSITION_CN_TO_CODE:
                        if cn_name in source:
                            pos_val = cn_name + "位"
                            break
                    if pos_val:
                        break
                # term_text 非通用描述时也可用
                if not pos_val and term_text and not any(t in term_text for t in _generic_terms):
                    pos_val = term_text
                if pos_val and pos_val not in ("存在", "有"):
                    updates["position"] = pos_val
                elif not fp_code:
                    if str(val) not in _generic_terms:
                        updates["position"] = val
                _update_fetus_exam(patch_data, index, updates)
            elif fetus_field == "presentation":
                # 确定 presentation 值：排除通用描述
                pres_val = None
                # 先从 val/term_text/raw_text 中提取具体先露类型
                presentation_terms = ("头先露", "臀先露", "肩先露", "足先露", "面先露")
                for source in [str(val), str(term_text), str(raw_text)]:
                    for pt in presentation_terms:
                        if pt in source:
                            pres_val = pt
                            break
                    if pres_val:
                        break
                # term_text 非通用描述时也可用
                if not pres_val and term_text and not any(t in term_text for t in _generic_terms):
                    pres_val = term_text
                if pres_val:
                    _update_fetus_exam(patch_data, index, {"presentation": pres_val})
                else:
                    _update_fetus_exam(patch_data, index, {fetus_field: val})
            else:
                _update_fetus_exam(patch_data, index, {fetus_field: val})
            continue

        # [SCHEMA_MAP] 精确字段映射
        path = SCHEMA_MAP_EXPANDED.get(key)

        if not path:
            # [兜底路由] 未命中映射时按分类写入 *Note
            domain, field = find_domain_by_dict(key)
            if field not in patch_data[domain]:
                if field in list_fields:
                    patch_data[domain][field] = []
                else:
                    patch_data[domain][field] = ""
            display_key = term_text or key
            if field in list_fields:
                patch_data[domain][field].append(display_key)
            else:
                # *Note 只保留 term（term 已内嵌全部描述与状态），去除冗余的 value
                if _is_negated(str(val)) and term_text and not _is_negated(str(term_text)):
                    display_key = f"否认{display_key}"
                patch_data[domain][field] = _append_text(patch_data[domain].get(field), str(display_key))
            continue

        parts = path.split(".")
        if len(parts) == 1:
            domain, field = "root", parts[0]
        else:
            domain, field = parts[0], parts[-1]

        # [特殊规则] 胎数 fetalcount：类型校验+转换，防止字符串写入 int 字段导致序列化报错
        if field == "fetalcount":
            count = _parse_fetal_count(val, term_text)
            if count is not None:
                patch_data[domain][field] = count
            continue

        # [列表字段] 追加到 list_fields
        if field in list_fields:
            if field not in patch_data[domain]:
                patch_data[domain][field] = []
            if field == "medication":
                val = _format_medication(val, term_text, last_pmh_reason)
            patch_data[domain][field].append(f"{val} ({term_text or key})")
            continue

        # [数值字段] int/float/date
        if field in int_fields:
            number = _parse_int_or_range(val)
            if number is not None:
                patch_data[domain][field] = number
            elif domain == "additional_medical_history" and field == "menstrualCycle":
                # 定性描述（如"规律"）写入 otherNote，而非丢弃
                text = term_text or val
                if text:
                    norm_text = "月经规律" if ("月经周期规律" in str(text) or "月经规律" in str(text) or "月经周期规则" in str(text)) else str(text)
                    patch_data[domain]["otherNote"] = _append_text(
                        patch_data[domain].get("otherNote"), norm_text)
            continue

        if field in float_fields:
            number = _parse_number(val)
            if number is not None:
                patch_data[domain][field] = float(number)
            continue

        if field in date_fields:
            patch_data[domain][field] = normalize_date(val, dov)
            continue

        # [状态字段] StatusDetail
        if (domain, field) in status_fields:
            _apply_status_with_note(patch_data, domain, field, _status_from_value(val, term_text, key, domain, field))
            # 联动规则1：产科问卷中"接触有害化学物质或放射线"是合并问题，
            # 否认有害物质时也应联动否认放射性接触
            if domain == "personal_history" and field == "hazardoussubstances":
                sd = patch_data.get("personal_history", {}).get("hazardoussubstances")
                if isinstance(sd, StatusDetail) and sd.status == 0:
                    _apply_status_with_note(patch_data, "personal_history", "radioactivity",
                        StatusDetail(status=0, details="患者否认放射性接触"))
            # 联动规则2：产科场景否认"糖尿病"时，联动合并为"糖尿病及妊娠期糖尿病"
            if domain == "pmh" and field == "diabetes":
                sd = patch_data.get("pmh", {}).get("diabetes")
                if isinstance(sd, StatusDetail) and sd.status == 0:
                    det = sd.details or ""
                    if "妊娠期糖尿病" not in det and "孕前" not in det:
                        # 通用"否认糖尿病史" → 产科联动合并为"糖尿病及妊娠期糖尿病"
                        if "糖尿病史" in det:
                            sd.details = det.replace("糖尿病史", "糖尿病及妊娠期糖尿病史")
                        elif "糖尿病" in det:
                            sd.details = det.replace("糖尿病", "糖尿病及妊娠期糖尿病", 1)
            continue

        # [文本字段] root/hpi/advice/others 的通用格式
        def _format_value_term(value_text: str, term_value: str) -> str:
            if term_value and any(token in term_value for token in ("拟行", "嘱", "建议")):
                return _normalize_advice_text(term_value)
            if term_value and value_text in ("执行", "尽快执行"):
                return _normalize_advice_text(term_value)
            if value_text and term_value:
                return _normalize_advice_text(f"{value_text}{term_value}")
            return _normalize_advice_text(value_text or term_value)

        def _pick_value(value_text: str, term_value: str) -> str:
            if value_text in ("存在", "否认", "未提及", "执行", "尽快执行") and term_value:
                return term_value
            return value_text

        if domain == "root":
            if field == "gwov":
                # 孕周保护：已有数字型孕周时，不覆盖为描述性文本
                existing_gwov = patch_data["root"].get("gwov")
                picked = _pick_value(val, term_text)
                if existing_gwov:
                    # 已有孕周，只有新值是数字型时才覆盖
                    new_normalized = _normalize_gwov(picked)
                    if new_normalized and re.match(r'\d+\+\d+', new_normalized):
                        patch_data["root"]["gwov"] = picked
                    # 否则保留原有孕周，描述性信息写入 hpi.otherNote
                    else:
                        note_text = term_text or val
                        if note_text and note_text not in ("存在",):
                            patch_data["hpi"]["otherNote"] = _append_text(
                                patch_data["hpi"].get("otherNote"), str(note_text))
                else:
                    patch_data["root"]["gwov"] = picked
            else:
                patch_data["root"][field] = _pick_value(val, term_text)
        else:
            if field == "chiefcomplaint":
                # 规则：月经规律不属于主诉，应映射到月经史 otherNote
                is_menstrual_regular = ("月经规律" in str(term_text) or "月经规律" in str(val)
                                        or "月经规律性" in str(term_text) or "月经规律性" in str(val))
                if is_menstrual_regular:
                    patch_data.setdefault("additional_medical_history", {})["otherNote"] = _append_text(
                        patch_data.get("additional_medical_history", {}).get("otherNote"), "月经规律")
                    # 不写入chiefcomplaint
                else:
                    # BUG 5: 主诉用 term+value 共同描述事实
                    # BUG 4: 多个主诉用 _append_text 拼接，不覆盖
                    if not term_text or term_text == key:
                        complaint = val
                    elif val in ("存在", "否认", "未提及"):
                        complaint = term_text
                    elif val == term_text:
                        complaint = val
                    else:
                        complaint = f"{term_text}{val}"
                    complaint = _clean_complaint_text(str(complaint))
                    if complaint:
                        # 过滤 LLM 误标的值占位符噪音（"存在""否认"等不应作为主诉）
                        _noise = {"存在", "无", "有", "是", "否认", "疼痛", "不适", "症状", "未提及"}
                        if complaint.strip() not in _noise:
                            patch_data[domain][field] = _append_text(patch_data[domain].get(field), complaint)
            elif domain == "gynecologicalExamination" and field in ("fundalHeight", "waistHip"):
                number = _parse_number(val)
                patch_data[domain][field] = float(number) if number is not None else None
            elif field in ("prescription", "exam"):
                patch_data[domain][field] = _append_text(patch_data[domain].get(field), _format_value_term(val, term_text))
            elif field == "otherNote":
                # *Note 只保留 term（term 已内嵌全部描述与状态），去除冗余的 value
                display = str(term_text or key)
                # 仅当 value 为否定且 term 未含否定语义时，前置"否认"防止语义反转
                if _is_negated(str(val)) and term_text and not _is_negated(str(term_text)):
                    display = f"否认{display}"
                patch_data[domain][field] = _append_text(patch_data[domain].get(field), display)
            elif domain == "personal_history" and field == "medicine":
                incoming = _status_from_value(val, term_text or key, key, domain, field)
                existing = patch_data[domain].get(field)
                if isinstance(existing, StatusDetail) and incoming.details:
                    merged = _append_text(existing.details, incoming.details)
                    patch_data[domain][field] = StatusDetail(status=incoming.status, details=merged)
                else:
                    patch_data[domain][field] = incoming
            else:
                patch_data[domain][field] = _pick_value(val, term_text)

    # 规则分块：OBH entries 合并输出
    if patch_data["obh_entries"]:
        patch_data["obh"]["entries"] = patch_data["obh_entries"]
    patch_data.pop("obh_entries", None)

    gwov_val = patch_data["root"].get("gwov")
    if gwov_val:
        gwov_normalized = _normalize_gwov(gwov_val)
        if gwov_normalized != gwov_val:
            patch_data["root"]["gwov"] = gwov_normalized
            gwov_val = gwov_normalized
    extracted_edd = patch_data["hpi"].get("edd")

    # 不再自动由孕周推算预产期：原文未提及预产期时，edd 应为 null 而非凭空推算
    # 注：infer_edd_from_gw 仅用于交叉校验，不用于生成新数据

    # 规则分块：过敏兜底（药物/食物均否认时补齐其他过敏）
    allergy_drug = patch_data["pmh"].get("allergyDrug")
    allergy_food = patch_data["pmh"].get("allergyFood")
    allergy_other = patch_data["pmh"].get("allergyOther")
    if isinstance(allergy_drug, StatusDetail) and isinstance(allergy_food, StatusDetail):
        if allergy_drug.status == 0 and allergy_food.status == 0 and not isinstance(allergy_other, StatusDetail):
            patch_data["pmh"]["allergyOther"] = StatusDetail(status=0, details="患者否认其他过敏史")

    # 规则分块：脉搏/心率互补
    pulse_val = patch_data["physicalExamination"].get("pulse")
    heartrate_val = patch_data["physicalExamination"].get("heartrate")
    if pulse_val and not heartrate_val:
        patch_data["physicalExamination"]["heartrate"] = pulse_val
    elif heartrate_val and not pulse_val:
        patch_data["physicalExamination"]["pulse"] = heartrate_val

    _normalize_patch_notes(patch_data)

    return patch_data

