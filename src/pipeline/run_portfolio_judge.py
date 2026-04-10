"""
Run the Portfolio Judge on existing debate stage transcript outputs.

The Portfolio Judge receives the full debate transcripts for all tickers
simultaneously and produces a conviction-differentiated portfolio allocation,
unlike the per-stock JudgeAgent whose outputs are mechanically normalized.

Reads  : outputs/debate_stage/transcript/{YYYY-MM-DD}.json
Writes : outputs/portfolio_judge/{YYYY-MM-DD}.json

Usage
-----
# All available weeks:
    python -m src.pipeline.run_portfolio_judge

# Filter by date range (typical range: 2025-08-03 to yesterday):
    python -m src.pipeline.run_portfolio_judge --start-date 2025-08-03 --end-date 2026-04-09

# Custom directories:
    python -m src.pipeline.run_portfolio_judge \\
        --transcript-dir outputs/debate_stage/transcript \\
        --output-dir outputs/portfolio_judge
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import time
from pathlib import Path
from typing import Any

from src.agents.portfolio_judge import PortfolioJudge

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TRANSCRIPT_DIR = "outputs/debate_stage/transcript"
DEFAULT_OUTPUT_DIR = "outputs/portfolio_judge"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

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


def _available_weeks(transcript_dir: str) -> list[str]:
    base = _resolve(transcript_dir)
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


# ---------------------------------------------------------------------------
# Per-week runner
# ---------------------------------------------------------------------------

def run_for_week(
    week_end_date: str,
    transcript_dir: str,
    output_dir: str,
    agent: PortfolioJudge,
) -> None:
    transcript_path = _resolve(transcript_dir) / f"{week_end_date}.json"
    output_path = _resolve(output_dir) / f"{week_end_date}.json"

    if not transcript_path.exists():
        raise FileNotFoundError(f"Transcript not found: {transcript_path}")

    print(f"\n=== PORTFOLIO JUDGE: {week_end_date} ===")

    transcript = _load_json(transcript_path)
    tickers: list[str] = transcript.get("tickers", [])
    per_ticker_transcripts: list[dict[str, Any]] = transcript.get("per_ticker_transcript", [])

    result = agent.allocate(per_ticker_transcripts)

    total_allocated = round(
        sum(d["weight_pct"] for d in result["holdings"].values()), 2
    )

    output: dict[str, Any] = {
        "week_end_date": week_end_date,
        "agent_name": agent.agent_name,
        "tickers": tickers,
        "portfolio_rationale": result["portfolio_rationale"],
        "ranking": result["ranking"],
        "holdings": result["holdings"],
        "total_allocated_pct": total_allocated,
    }

    _save_json(output, output_path)

    # ------------------------------------------------------------------
    # Console summary
    # ------------------------------------------------------------------
    rationale = result["portfolio_rationale"]
    print(f"  Rationale : {rationale[:100]}{'...' if len(rationale) > 100 else ''}")
    print(f"  Ranking   : {' > '.join(result['ranking'])}")
    print("  Allocation:")
    for ticker, data in sorted(
        result["holdings"].items(), key=lambda x: -x[1]["weight_pct"]
    ):
        w = data["weight_pct"]
        weight_str = f"{w:5.1f}%" if w > 0 else "  ---"
        reason_preview = data["reason"][:60]
        print(f"    {ticker:8s} {weight_str}  {reason_preview}")
    print(f"  Total: {total_allocated:.1f}%")
    print(f"  Saved : outputs/portfolio_judge/{week_end_date}.json")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    parser = argparse.ArgumentParser(
        description="Run Portfolio Judge on existing debate stage transcripts."
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
        "--transcript-dir",
        type=str,
        default=DEFAULT_TRANSCRIPT_DIR,
        help=f"Directory containing transcript JSON files (default: {DEFAULT_TRANSCRIPT_DIR}).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory where portfolio judge outputs will be saved (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=15.0,
        help="Seconds to wait between weeks to respect the API rate limit (default: 15).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    agent = PortfolioJudge()

    weeks = _available_weeks(args.transcript_dir)
    if not weeks:
        raise FileNotFoundError(
            f"No transcript JSON files found under {args.transcript_dir}."
        )

    weeks = _filter_weeks(weeks, args.start_date, args.end_date)
    if not weeks:
        raise ValueError(
            f"No weeks found in range [{args.start_date}, {args.end_date}]. "
            "Check --start-date and --end-date."
        )

    print(f"\n=== Portfolio Judge — {len(weeks)} week(s), delay={args.delay}s ===")
    for i, week in enumerate(weeks):
        run_for_week(
            week_end_date=week,
            transcript_dir=args.transcript_dir,
            output_dir=args.output_dir,
            agent=agent,
        )
        if i < len(weeks) - 1:
            print(f"  Waiting {args.delay}s before next week ...")
            time.sleep(args.delay)
    print("\nDone.")


if __name__ == "__main__":
    main()
