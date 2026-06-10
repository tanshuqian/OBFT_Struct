import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False


def _as_number(value: Any) -> Tuple[bool, float]:
    if isinstance(value, (int, float)):
        return True, float(value)
    if isinstance(value, str):
        match = _NUMBER_RE.search(value)
        if match:
            return True, float(match.group(0))
    return False, 0.0


def _normalize_string(value: str) -> str:
    return value.strip()


def _same_value(a: Any, b: Any) -> Tuple[bool, bool]:
    if _is_empty(a) and _is_empty(b):
        return True, False
    if isinstance(a, str) and isinstance(b, str):
        na = _normalize_string(a)
        nb = _normalize_string(b)
        if na == nb:
            return True, False
        if na and nb and (na in nb or nb in na):
            return False, True
        return False, False

    a_is_num, a_num = _as_number(a)
    b_is_num, b_num = _as_number(b)
    if a_is_num and b_is_num:
        return abs(a_num - b_num) < 1e-6, False

    return a == b, False


def _flatten_json(data: Any, prefix: str = "") -> Dict[str, Any]:
    items: Dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str) and key.startswith("_comment"):
                continue
            path = f"{prefix}.{key}" if prefix else str(key)
            items.update(_flatten_json(value, path))
    elif isinstance(data, list):
        if not data:
            return {prefix: []} if prefix else {}
        if all(isinstance(item, dict) and "index" in item for item in data):
            for item in data:
                idx = item.get("index")
                path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
                items.update(_flatten_json(item, path))
        else:
            for idx, item in enumerate(data, start=1):
                path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
                items.update(_flatten_json(item, path))
    else:
        if prefix:
            items[prefix] = data
    return items


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_sessions(folder: Path) -> Iterable[Tuple[str, Path]]:
    for path in sorted(folder.glob("session_*.json"), key=lambda p: int(p.stem.split("_")[-1])):
        yield path.stem, path


def compare_sessions(pred_dir: Path, gold_dir: Path) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "pred_dir": str(pred_dir),
        "gold_dir": str(gold_dir),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sessions": {},
        "summary": {},
        "field_counts": {},
    }

    field_counter = Counter()
    summary_counts = Counter()

    for session_id, gold_path in _iter_sessions(gold_dir):
        pred_path = pred_dir / f"{session_id}.json"
        if not pred_path.exists():
            report["sessions"][session_id] = {"missing_pred": True}
            summary_counts["missing_pred"] += 1
            continue

        gold = _load_json(gold_path)
        pred = _load_json(pred_path)

        gold_flat = _flatten_json(gold)
        pred_flat = _flatten_json(pred)

        paths = sorted(set(gold_flat.keys()) | set(pred_flat.keys()))
        missing = []
        extra = []
        mismatch = []
        soft_mismatch = []

        for path in paths:
            g_val = gold_flat.get(path)
            p_val = pred_flat.get(path)

            if _is_empty(g_val) and _is_empty(p_val):
                continue

            if not _is_empty(g_val) and _is_empty(p_val):
                missing.append({"path": path, "gold": g_val, "pred": p_val})
                field_counter[path] += 1
                continue

            if _is_empty(g_val) and not _is_empty(p_val):
                extra.append({"path": path, "gold": g_val, "pred": p_val})
                field_counter[path] += 1
                continue

            same, soft = _same_value(g_val, p_val)
            if not same:
                if soft:
                    soft_mismatch.append({"path": path, "gold": g_val, "pred": p_val})
                else:
                    mismatch.append({"path": path, "gold": g_val, "pred": p_val})
                field_counter[path] += 1

        session_report = {
            "missing": missing,
            "extra": extra,
            "mismatch": mismatch,
            "soft_mismatch": soft_mismatch,
            "counts": {
                "missing": len(missing),
                "extra": len(extra),
                "mismatch": len(mismatch),
                "soft_mismatch": len(soft_mismatch),
            },
        }
        report["sessions"][session_id] = session_report
        summary_counts.update(session_report["counts"])

    report["summary"] = dict(summary_counts)
    report["field_counts"] = dict(field_counter.most_common())
    return report


def write_report(report: Dict[str, Any], output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"compare_report_{stamp}.json"
    txt_path = output_dir / f"compare_report_{stamp}.txt"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("Compare Report")
    lines.append(f"pred_dir: {report['pred_dir']}")
    lines.append(f"gold_dir: {report['gold_dir']}")
    lines.append(f"generated_at: {report['generated_at']}")
    lines.append("")
    lines.append("Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("Top fields")
    for path, count in list(report["field_counts"].items())[:20]:
        lines.append(f"- {path}: {count}")
    lines.append("")

    for session_id, details in report["sessions"].items():
        if details.get("missing_pred"):
            lines.append(f"{session_id}: missing prediction file")
            continue
        counts = details["counts"]
        if sum(counts.values()) == 0:
            continue
        lines.append(f"{session_id}:")
        lines.append(
            f"  missing={counts['missing']} extra={counts['extra']} mismatch={counts['mismatch']} soft={counts['soft_mismatch']}"
        )
        for label in ("missing", "extra", "mismatch", "soft_mismatch"):
            items = details[label][:5]
            for item in items:
                lines.append(f"  - {label}: {item['path']} | gold={item['gold']} | pred={item['pred']}")
        lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare structured medical record outputs with gold standard.")
    parser.add_argument("--pred-dir", type=Path, default=Path("output") / "Stage2_4_After_LLM_20260528_161515")
    parser.add_argument("--gold-dir", type=Path, default=Path("data") / "output" / "standard_medical_record_20")
    parser.add_argument("--out-dir", type=Path, default=Path("output") / "compare_reports")
    args = parser.parse_args()

    report = compare_sessions(args.pred_dir, args.gold_dir)
    json_path, txt_path = write_report(report, args.out_dir)
    print(f"Report written: {json_path}")
    print(f"Report written: {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

