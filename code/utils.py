import re
from datetime import datetime, timedelta


def normalize_date(date_str: str, dov_str: str = None) -> str:
    """日期归一化：优先保留原始年份，避免用当前日期篡改历史年份

    规则：
    1. "2022年2月12号" → "2022-02-12" (保留原始年份)
    2. "1月6号"         → "01-06"       (无年份时仅保留月-日，不猜测)
    3. "2026-01-06"     → "2026-01-06"  (已是标准格式，直接返回)
    """
    if not date_str:
        return None
    # 已经是 YYYY-MM-DD 标准格式 → 直接返回
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    try:
        # 优先匹配带年份的中文日期 "2022年2月12号"
        year_match = re.search(r'(\d{4})年', date_str)
        month_day_match = re.search(r'(\d{1,2})月(\d{1,2})[日号]?', date_str)
        if month_day_match:
            month = int(month_day_match.group(1))
            day = int(month_day_match.group(2))
            if year_match:
                # 有明确年份 → 使用原始年份
                year = int(year_match.group(1))
                return f"{year}-{month:02d}-{day:02d}"
            else:
                # 无年份 → 仅返回月-日，不使用dov年份填充
                return f"{month:02d}-{day:02d}"
    except Exception:
        pass
    return str(date_str)


def infer_edd_from_gw(gw_str: str, dov_str: str) -> str:
    """根据孕周 (如 '37+4', '30周', '32周+') 和就诊日期推算预产期 (EDD)"""
    try:
        # 优先匹配规范化格式 "W+D"，兼容旧格式 "W周+D" / "W周"
        match = re.match(r'(\d+)\+(\d+)', str(gw_str))
        if match:
            weeks = int(match.group(1))
            days = int(match.group(2))
        else:
            match = re.search(r'(\d+)周(?:\+(\d+))?', str(gw_str))
            if match:
                weeks = int(match.group(1))
                days = int(match.group(2)) if match.group(2) else 0
            else:
                return None

        dov_date = datetime.strptime(dov_str, "%Y-%m-%d")
        # 预产期是 40周 (280天)。剩余天数 = 280 - (已孕周数 * 7 + 零头天数)
        remaining_days = 280 - (weeks * 7 + days)
        edd_date = dov_date + timedelta(days=remaining_days)
        return edd_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"  [孕周推算预产期失败]: {e}")
    return None


def clean_json_string(raw_str: str) -> str:
    """强力清洗：去除大模型经常吐出的 Unicode 幽灵字符及 Markdown 标记"""
    # 清理 vLLM 可能产出的脏 Token 和占位符
    cleaned = raw_str.replace('\ue000', '').replace('\u200b', '').replace('\ufffd', '')
    cleaned = re.sub(r'```json', '', cleaned)
    cleaned = re.sub(r'```', '', cleaned)
    return cleaned.strip()