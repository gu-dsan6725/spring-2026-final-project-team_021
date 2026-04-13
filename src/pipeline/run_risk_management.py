"""
Run the risk management layer on Portfolio Judge outputs.

For each available week this script:
  1. Reads the Portfolio Judge report and debate transcript for that week.
  2. Applies rule-based portfolio constraints (minimum holdings / defensive
     mode, single-position cap, sector concentration cap).
  3. Calls an LLM to produce a plain-English risk commentary from the transcript.
  4. Saves a JSON risk report to outputs/risk_management/{date}.json.

Usage examples
--------------
# Run on all available weeks:
python -m src.pipeline.run_risk_management

# Filter by date range (typical range: 2025-08-03 to yesterday):
python -m src.pipeline.run_risk_management --start-date 2025-08-03 --end-date 2026-04-09

# Override thresholds:
python -m src.pipeline.run_risk_management \\
    --max-single-pct 55 --max-sector-pct 55
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path

from src.agents.risk_manager import RiskManager


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_JUDGE_DIR      = "outputs/portfolio_judge"
DEFAULT_TRANSCRIPT_DIR = "outputs/debate_stage/transcript"
DEFAULT_OUTPUT_DIR     = "outputs/risk_management"


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(data: dict, path: Path) -> None:
    os.makedirs(path.parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _available_weeks(judge_dir: str) -> list[str]:
    base = _resolve(judge_dir)
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.json"))


def _filter_weeks(
    weeks: list[str],
    start_date: str | None,
    end_date: str | None,
) -> list[str]:
    if start_date:
        weeks = [w for w in weeks if w >= start_date]
    if end_date:
        weeks = [w for w in weeks if w <= end_date]
    return weeks


def run_for_week(
    week_end_date: str,
    judge_dir: str,
    transcript_dir: str,
    output_dir: str,
    manager: RiskManager,
) -> None:
    judge_path      = _resolve(judge_dir)      / f"{week_end_date}.json"
    transcript_path = _resolve(transcript_dir) / f"{week_end_date}.json"
    output_path     = _resolve(output_dir)     / f"{week_end_date}.json"

    if not judge_path.exists():
        raise FileNotFoundError(f"Portfolio Judge report not found: {judge_path}")
    if not transcript_path.exists():
        raise FileNotFoundError(f"Transcript not found: {transcript_path}")

    judge_report = _load_json(judge_path)
    transcript   = _load_json(transcript_path)

    print(f"\n=== RISK MANAGEMENT: {week_end_date} ===")
    report = manager.apply(judge_report=judge_report, transcript=transcript)

    _save_json(report.to_dict(), output_path)

    # Console summary
    print(f"  Defensive mode : {report.defensive_mode}")
    if report.rules_triggered:
        for rule in report.rules_triggered:
            print(f"  Rule triggered : {rule}")
    else:
        print("  Rules triggered: none")
    print("  Adjusted portfolio:")
    for ticker, pct in sorted(
        report.adjusted_allocations.items(), key=lambda x: -x[1]
    ):
        marker = " *" if abs(pct - report.original_allocations.get(ticker, pct)) > 0.01 else ""
        print(f"    {ticker:8s} {pct:6.2f}%{marker}")
    print(f"  Risk report saved: outputs/risk_management/{week_end_date}.json")


def parse_args() -> argparse.Namespace:
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    parser = argparse.ArgumentParser(
        description="Apply risk management rules to Portfolio Judge outputs."
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Only process weeks on or after this date (YYYY-MM-DD). "
             "Suggested default: 2025-08-03.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help=f"Only process weeks on or before this date (YYYY-MM-DD). "
             f"Suggested default: yesterday ({yesterday}).",
    )
    parser.add_argument(
        "--judge-dir", type=str, default=DEFAULT_JUDGE_DIR,
        help=f"Directory containing Portfolio Judge JSON files (default: {DEFAULT_JUDGE_DIR}).",
    )
    parser.add_argument(
        "--transcript-dir", type=str, default=DEFAULT_TRANSCRIPT_DIR,
        help="Directory containing transcript JSON files.",
    )
    parser.add_argument(
        "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR,
        help="Directory where risk report JSON files will be saved.",
    )
    parser.add_argument(
        "--max-single-pct", type=float, default=55.0,
        help="Maximum single-ticker allocation in percent (default: 55.0).",
    )
    parser.add_argument(
        "--max-sector-pct", type=float, default=55.0,
        help="Maximum sector allocation in percent (default: 55.0).",
    )
    parser.add_argument(
        "--min-holdings", type=int, default=3,
        help="Minimum non-zero positions before defensive mode activates (default: 3).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    manager = RiskManager(
        max_single_pct=args.max_single_pct,
        max_sector_pct=args.max_sector_pct,
        min_holdings=args.min_holdings,
    )

    weeks = _available_weeks(args.judge_dir)
    if not weeks:
        raise FileNotFoundError(
            f"No Portfolio Judge JSON files found under {args.judge_dir}."
        )
    weeks = _filter_weeks(weeks, args.start_date, args.end_date)
    if not weeks:
        raise ValueError(
            f"No weeks found in range [{args.start_date}, {args.end_date}]. "
            "Check --start-date and --end-date."
        )

    for week in weeks:
        run_for_week(
            week_end_date=week,
            judge_dir=args.judge_dir,
            transcript_dir=args.transcript_dir,
            output_dir=args.output_dir,
            manager=manager,
        )


if __name__ == "__main__":
    main()
