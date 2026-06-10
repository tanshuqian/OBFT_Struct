import argparse
from pathlib import Path

from compare_structured_records import compare_sessions, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run comparison and write reports.")
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
