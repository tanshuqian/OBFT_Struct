# Tools

## Compare structured records

This compares post-structured outputs with the gold standard records and writes JSON/TXT reports.

Run from the repo root:

```bash
python tools\run_compare.py
```

Optional arguments:

```bash
python tools\run_compare.py --pred-dir output\Stage2_4_After_LLM_20260528_161515 --gold-dir data\output\standard_medical_record_20 --out-dir output\compare_reports
```
