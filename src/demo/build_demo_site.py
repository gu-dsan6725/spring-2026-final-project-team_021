"""
Build a static demo website for exploring DebateTrader outputs.

The generated page is self-contained and can be opened directly in a browser.
It reads historical debate-stage outputs from `outputs/` and embeds the data
into a searchable HTML page with client-side filtering.

Usage
-----
python -m src.demo.build_demo_site
python -m src.demo.build_demo_site --output outputs/demo_site/index.html
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from statistics import mean


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "demo_site" / "index.html"
DEFAULT_PAGES_DIR = PROJECT_ROOT / "docs"
JUDGE_DIR = PROJECT_ROOT / "outputs" / "debate_stage" / "judge"
BULL_DIR = PROJECT_ROOT / "outputs" / "debate_stage" / "bull"
BEAR_DIR = PROJECT_ROOT / "outputs" / "debate_stage" / "bear"
BACKTEST_RESULTS_PATH = PROJECT_ROOT / "outputs" / "backtest" / "results.json"
BACKTEST_CHART_SOURCE_PATH = PROJECT_ROOT / "outputs" / "backtest" / "chart.html"
BACKTEST_CHART_RELATIVE_PATH = "../backtest/chart.html"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_history_records() -> tuple[list[dict], list[dict]]:
    records: list[dict] = []
    weekly_rollups: list[dict] = []

    judge_paths = sorted(JUDGE_DIR.glob("*.json"))
    for judge_path in judge_paths:
        week_end_date = judge_path.stem
        bull_path = BULL_DIR / f"{week_end_date}.json"
        bear_path = BEAR_DIR / f"{week_end_date}.json"
        if not bull_path.exists() or not bear_path.exists():
            continue

        judge_report = _load_json(judge_path)
        bull_report = _load_json(bull_path)
        bear_report = _load_json(bear_path)

        bull_views = {item["ticker"]: item for item in bull_report.get("company_views", [])}
        bear_views = {item["ticker"]: item for item in bear_report.get("company_views", [])}
        holdings = list(judge_report.get("holdings", []))

        signal_counts = {"bullish": 0, "bearish": 0, "neutral": 0}
        top_long = None
        for holding in holdings:
            signal = str(holding.get("signal", "neutral"))
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
            if top_long is None or _safe_float(holding.get("suggested_position_pct")) > _safe_float(
                top_long.get("suggested_position_pct")
            ):
                top_long = holding

            ticker = str(holding.get("ticker", ""))
            bull_view = bull_views.get(ticker, {})
            bear_view = bear_views.get(ticker, {})

            record = {
                "id": f"{week_end_date}-{ticker}",
                "week_end_date": week_end_date,
                "input_data_date": str(holding.get("input_data_date", week_end_date)),
                "ticker": ticker,
                "signal": signal,
                "confidence": round(_safe_float(holding.get("confidence")), 2),
                "suggested_position_pct": round(_safe_float(holding.get("suggested_position_pct")), 2),
                "summary": str(holding.get("summary", "")),
                "portfolio_summary": str(judge_report.get("portfolio_summary", "")),
                "rationale": [str(item) for item in holding.get("rationale", [])],
                "dissenting_points": [str(item) for item in holding.get("dissenting_points", [])],
                "risk_flags": [str(item) for item in holding.get("risk_flags", [])],
                "source_report_dates": dict(holding.get("source_report_dates", {})),
                "score_breakdown": dict(holding.get("score_breakdown", {})),
                "bull_thesis": str(bull_view.get("thesis", "")),
                "bull_confidence": round(_safe_float(bull_view.get("confidence")), 2),
                "bull_reasons": [str(item) for item in bull_view.get("reasons", [])],
                "bull_counterpoints": [str(item) for item in bull_view.get("counterpoints", [])],
                "bear_thesis": str(bear_view.get("thesis", "")),
                "bear_confidence": round(_safe_float(bear_view.get("confidence")), 2),
                "bear_reasons": [str(item) for item in bear_view.get("reasons", [])],
                "bear_counterpoints": [str(item) for item in bear_view.get("counterpoints", [])],
            }
            records.append(record)

        weekly_rollups.append(
            {
                "week_end_date": week_end_date,
                "portfolio_summary": str(judge_report.get("portfolio_summary", "")),
                "bullish_count": signal_counts.get("bullish", 0),
                "bearish_count": signal_counts.get("bearish", 0),
                "neutral_count": signal_counts.get("neutral", 0),
                "cash_pct": round(_safe_float(judge_report.get("cash_pct")), 2),
                "top_long_ticker": str(top_long.get("ticker", "")) if top_long else "",
                "top_long_weight": round(_safe_float(top_long.get("suggested_position_pct")), 2) if top_long else 0.0,
            }
        )

    records.sort(key=lambda item: (item["week_end_date"], item["ticker"]), reverse=True)
    weekly_rollups.sort(key=lambda item: item["week_end_date"], reverse=True)
    return records, weekly_rollups


def _build_backtest_summary() -> dict:
    if not BACKTEST_RESULTS_PATH.exists():
        return {}

    payload = _load_json(BACKTEST_RESULTS_PATH)
    strategy_metrics = dict(payload.get("strategy", {}).get("metrics", {}))
    benchmark_metrics = dict(payload.get("benchmark_60_40", {}).get("metrics", {}))
    periods = list(payload.get("strategy", {}).get("periods", []))

    return {
        "strategy_metrics": strategy_metrics,
        "benchmark_metrics": benchmark_metrics,
        "date_range": {
            "start": str(periods[0].get("entry_date", "")) if periods else "",
            "end": str(periods[-1].get("exit_date", "")) if periods else "",
        },
    }


def _build_site_payload() -> dict:
    records, weekly_rollups = _build_history_records()
    tickers = sorted({record["ticker"] for record in records})
    signals = ["bullish", "neutral", "bearish"]
    latest_week = weekly_rollups[0]["week_end_date"] if weekly_rollups else ""
    avg_confidence = round(mean(record["confidence"] for record in records), 2) if records else 0.0

    return {
        "generated_from": "outputs/debate_stage",
        "backtest_chart_path": BACKTEST_CHART_RELATIVE_PATH,
        "stats": {
            "record_count": len(records),
            "week_count": len(weekly_rollups),
            "ticker_count": len(tickers),
            "latest_week": latest_week,
            "avg_confidence": avg_confidence,
        },
        "tickers": tickers,
        "signals": signals,
        "records": records,
        "weekly_rollups": weekly_rollups,
        "backtest": _build_backtest_summary(),
    }


def _resolve_output_path(output_arg: str | None, publish_dir_arg: str | None) -> Path:
    if publish_dir_arg:
        publish_dir = Path(publish_dir_arg)
        if not publish_dir.is_absolute():
            publish_dir = PROJECT_ROOT / publish_dir
        return publish_dir / "index.html"

    if output_arg is None:
        return DEFAULT_OUTPUT_PATH

    output_path = Path(output_arg)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    return output_path


def _publish_backtest_chart(output_path: Path) -> str:
    target_dir = output_path.parent / "backtest"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_chart_path = target_dir / "chart.html"
    shutil.copyfile(BACKTEST_CHART_SOURCE_PATH, target_chart_path)
    return "./backtest/chart.html"


def _write_nojekyll(output_path: Path) -> None:
    nojekyll_path = output_path.parent / ".nojekyll"
    nojekyll_path.write_text("", encoding="utf-8")


def _html_template(site_payload: dict) -> str:
    embedded = json.dumps(site_payload, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DebateTrader Demo Explorer</title>
  <style>
    :root {{
      --bg: #f6f0e8;
      --panel: rgba(255, 252, 247, 0.92);
      --ink: #182126;
      --muted: #5a6772;
      --line: rgba(24, 33, 38, 0.12);
      --bull: #197a52;
      --bear: #b24d2a;
      --neutral: #7d6b2d;
      --accent: #0d5f73;
      --shadow: 0 18px 50px rgba(24, 33, 38, 0.12);
      --radius: 22px;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(13, 95, 115, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(178, 77, 42, 0.14), transparent 24%),
        linear-gradient(160deg, #efe4d2 0%, #f9f5ef 46%, #e9eef0 100%);
      min-height: 100vh;
    }}

    .shell {{
      width: min(1220px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 44px;
    }}

    .hero {{
      display: grid;
      grid-template-columns: 1.35fr 0.9fr;
      gap: 18px;
      margin-bottom: 18px;
    }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}

    .hero-main {{
      padding: 28px;
    }}

    .eyebrow {{
      font-size: 12px;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 10px;
    }}

    h1 {{
      margin: 0 0 12px;
      font-size: clamp(32px, 4vw, 56px);
      line-height: 0.95;
      font-weight: 700;
    }}

    .hero-copy {{
      font-size: 17px;
      line-height: 1.6;
      color: var(--muted);
      max-width: 58ch;
      margin: 0;
    }}

    .hero-side {{
      padding: 22px;
      display: grid;
      gap: 14px;
    }}

    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}

    .wide-panel {{
      padding: 20px;
      margin-bottom: 18px;
    }}

    .metric-card {{
      padding: 18px;
      min-height: 118px;
    }}

    .metric-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
    }}

    .metric-value {{
      font-size: 34px;
      line-height: 1;
      margin: 14px 0 6px;
    }}

    .metric-note {{
      font-size: 14px;
      color: var(--muted);
      line-height: 1.45;
    }}

    .filters {{
      padding: 20px;
      display: grid;
      grid-template-columns: 1.15fr repeat(3, minmax(0, 0.7fr)) 0.6fr;
      gap: 12px;
      align-items: end;
      margin-bottom: 18px;
    }}

    label {{
      display: grid;
      gap: 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
    }}

    input, select, button {{
      width: 100%;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.8);
      color: var(--ink);
      border-radius: 14px;
      padding: 12px 14px;
      font-size: 15px;
      font-family: inherit;
    }}

    button {{
      cursor: pointer;
      background: linear-gradient(135deg, #163847, #0d5f73);
      color: white;
      border: none;
    }}

    .content {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 18px;
    }}

    .chart-frame {{
      width: 100%;
      min-height: 620px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.72);
    }}

    .result-list {{
      padding: 10px;
      max-height: 70vh;
      overflow: auto;
    }}

    .result-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      margin-bottom: 12px;
      background: rgba(255,255,255,0.72);
      cursor: pointer;
      transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
    }}

    .result-card:hover,
    .result-card.active {{
      transform: translateY(-2px);
      border-color: rgba(13, 95, 115, 0.45);
      background: rgba(255,255,255,0.94);
    }}

    .result-top {{
      display: flex;
      gap: 12px;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
    }}

    .ticker {{
      font-size: 30px;
      line-height: 1;
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: white;
    }}

    .badge.bullish {{ background: var(--bull); }}
    .badge.bearish {{ background: var(--bear); }}
    .badge.neutral {{ background: var(--neutral); }}

    .result-meta {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 14px;
    }}

    .pill {{
      display: inline-block;
      padding: 5px 9px;
      border-radius: 999px;
      background: rgba(24, 33, 38, 0.06);
    }}

    .result-summary {{
      margin: 0;
      line-height: 1.55;
      color: var(--ink);
    }}

    .detail {{
      padding: 22px;
      max-height: 70vh;
      overflow: auto;
    }}

    .detail h2 {{
      margin: 0 0 10px;
      font-size: 36px;
    }}

    .detail-subtitle {{
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.55;
    }}

    .section {{
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }}

    .section-title {{
      margin: 0 0 10px;
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--accent);
    }}

    ul {{
      margin: 0;
      padding-left: 18px;
      line-height: 1.6;
    }}

    .small-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}

    .small-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: rgba(255,255,255,0.66);
    }}

    .timeline {{
      display: grid;
      gap: 10px;
      max-height: 280px;
      overflow: auto;
    }}

    .timeline-item {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      background: rgba(255,255,255,0.66);
    }}

    .empty {{
      padding: 28px;
      text-align: center;
      color: var(--muted);
    }}

    @media (max-width: 980px) {{
      .hero,
      .content {{
        grid-template-columns: 1fr;
      }}

      .metric-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}

      .filters {{
        grid-template-columns: 1fr 1fr;
      }}
    }}

    @media (max-width: 640px) {{
      .shell {{
        width: min(100% - 18px, 100%);
      }}

      .metric-grid,
      .filters,
      .small-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="panel hero-main">
        <div class="eyebrow">DebateTrader Demo Explorer</div>
        <h1>DebateTrader Decision Explorer</h1>
        <p class="hero-copy">
          This page turns historical DebateTrader outputs into a queryable web demo.
          Filter by ticker, week, signal, or keyword to inspect how bull, bear, and judge
          agents argued over each stock and what position the system recommended.
        </p>
      </div>
      <div class="panel hero-side">
        <div>
          <div class="metric-label">Data Source</div>
          <div class="metric-note" id="sourceLabel"></div>
        </div>
        <div>
          <div class="metric-label">Latest Week</div>
          <div class="metric-note" id="latestWeekLabel"></div>
        </div>
        <div>
          <div class="metric-label">Backtest Range</div>
          <div class="metric-note" id="backtestRangeLabel"></div>
        </div>
      </div>
    </section>

    <section class="metric-grid" id="metricGrid"></section>

    <section class="panel wide-panel">
      <div class="section-title">Backtest Chart</div>
      <p class="detail-subtitle">
        The existing backtest visualization from <code>outputs/backtest/chart.html</code>
        is embedded below so the demo page keeps historical debate decisions and
        performance context in one place.
      </p>
      <iframe id="backtestFrame" class="chart-frame" title="DebateTrader backtest chart"></iframe>
    </section>

    <section class="panel filters">
      <label>
        Keyword Search
        <input id="keywordInput" type="text" placeholder="ticker, thesis, rationale, risk..." />
      </label>
      <label>
        Ticker
        <select id="tickerSelect"></select>
      </label>
      <label>
        Signal
        <select id="signalSelect"></select>
      </label>
      <label>
        Week End
        <select id="weekSelect"></select>
      </label>
      <label>
        Reset
        <button id="resetButton" type="button">Clear</button>
      </label>
    </section>

    <section class="content">
      <div class="panel result-list" id="resultList"></div>
      <div class="panel detail" id="detailPanel"></div>
    </section>
  </div>

  <script>
    const SITE_DATA = {embedded};

    const state = {{
      keyword: "",
      ticker: "ALL",
      signal: "ALL",
      week: "ALL",
      activeId: null,
    }};

    const els = {{
      metricGrid: document.getElementById("metricGrid"),
      sourceLabel: document.getElementById("sourceLabel"),
      latestWeekLabel: document.getElementById("latestWeekLabel"),
      backtestRangeLabel: document.getElementById("backtestRangeLabel"),
      backtestFrame: document.getElementById("backtestFrame"),
      keywordInput: document.getElementById("keywordInput"),
      tickerSelect: document.getElementById("tickerSelect"),
      signalSelect: document.getElementById("signalSelect"),
      weekSelect: document.getElementById("weekSelect"),
      resetButton: document.getElementById("resetButton"),
      resultList: document.getElementById("resultList"),
      detailPanel: document.getElementById("detailPanel"),
    }};

    function escapeHtml(value) {{
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }}

    function signalBadge(signal) {{
      return `<span class="badge ${{signal}}">${{escapeHtml(signal)}}</span>`;
    }}

    function listHtml(items) {{
      if (!items || !items.length) return "<div class='metric-note'>No items</div>";
      return `<ul>${{items.map((item) => `<li>${{escapeHtml(item)}}</li>`).join("")}}</ul>`;
    }}

    function sourceDateHtml(dates) {{
      const keys = Object.keys(dates || {{}});
      if (!keys.length) return "<div class='metric-note'>No source dates</div>";
      return keys.map((key) => `<div><strong>${{escapeHtml(key)}}:</strong> ${{escapeHtml(dates[key])}}</div>`).join("");
    }}

    function scoreHtml(scoreBreakdown) {{
      const keys = Object.keys(scoreBreakdown || {{}});
      if (!keys.length) return "<div class='metric-note'>No score breakdown</div>";
      return keys.map((key) => {{
        const value = Number(scoreBreakdown[key]);
        const display = Number.isFinite(value) ? value.toFixed(3) : escapeHtml(scoreBreakdown[key]);
        return `<div><strong>${{escapeHtml(key)}}:</strong> ${{display}}</div>`;
      }}).join("");
    }}

    function metricCard(label, value, note) {{
      return `
        <div class="panel metric-card">
          <div class="metric-label">${{escapeHtml(label)}}</div>
          <div class="metric-value">${{escapeHtml(value)}}</div>
          <div class="metric-note">${{escapeHtml(note)}}</div>
        </div>
      `;
    }}

    function buildMetrics() {{
      const stats = SITE_DATA.stats || {{}};
      const strategyMetrics = SITE_DATA.backtest?.strategy_metrics || {{}};
      const benchmarkMetrics = SITE_DATA.backtest?.benchmark_metrics || {{}};

      els.metricGrid.innerHTML = [
        metricCard("Decision Records", stats.record_count || 0, `${{stats.week_count || 0}} weekly batches across ${{stats.ticker_count || 0}} tickers`),
        metricCard("Average Confidence", stats.avg_confidence || 0, "Mean judge confidence across all ticker-week decisions"),
        metricCard("Strategy Return", `${{Number(strategyMetrics.total_return_pct || 0).toFixed(2)}}%`, "Backtest total return"),
        metricCard("60/40 Return", `${{Number(benchmarkMetrics.total_return_pct || 0).toFixed(2)}}%`, "Reference benchmark return"),
      ].join("");

      els.sourceLabel.textContent = SITE_DATA.generated_from || "";
      els.latestWeekLabel.textContent = stats.latest_week || "";
      els.backtestFrame.src = SITE_DATA.backtest_chart_path || "";
      const range = SITE_DATA.backtest?.date_range || {{}};
      els.backtestRangeLabel.textContent = range.start && range.end ? `${{range.start}} -> ${{range.end}}` : "Not available";
    }}

    function fillSelect(selectEl, values, placeholder) {{
      selectEl.innerHTML = [`<option value="ALL">${{placeholder}}</option>`]
        .concat(values.map((value) => `<option value="${{escapeHtml(value)}}">${{escapeHtml(value)}}</option>`))
        .join("");
    }}

    function buildFilters() {{
      fillSelect(els.tickerSelect, SITE_DATA.tickers || [], "All tickers");
      fillSelect(els.signalSelect, SITE_DATA.signals || [], "All signals");
      fillSelect(els.weekSelect, (SITE_DATA.weekly_rollups || []).map((item) => item.week_end_date), "All weeks");
    }}

    function recordText(record) {{
      return [
        record.ticker,
        record.week_end_date,
        record.signal,
        record.summary,
        record.bull_thesis,
        record.bear_thesis,
        ...(record.rationale || []),
        ...(record.risk_flags || []),
        ...(record.bull_reasons || []),
        ...(record.bear_reasons || []),
      ].join(" ").toLowerCase();
    }}

    function filteredRecords() {{
      const keyword = state.keyword.trim().toLowerCase();
      return (SITE_DATA.records || []).filter((record) => {{
        if (state.ticker !== "ALL" && record.ticker !== state.ticker) return false;
        if (state.signal !== "ALL" && record.signal !== state.signal) return false;
        if (state.week !== "ALL" && record.week_end_date !== state.week) return false;
        if (keyword && !recordText(record).includes(keyword)) return false;
        return true;
      }});
    }}

    function renderList(records) {{
      if (!records.length) {{
        els.resultList.innerHTML = `<div class="empty">No records match the current filters.</div>`;
        return;
      }}

      if (!state.activeId || !records.some((record) => record.id === state.activeId)) {{
        state.activeId = records[0].id;
      }}

      els.resultList.innerHTML = records.map((record) => {{
        const activeClass = record.id === state.activeId ? "active" : "";
        return `
          <article class="result-card ${{activeClass}}" data-id="${{escapeHtml(record.id)}}">
            <div class="result-top">
              <div>
                <div class="ticker">${{escapeHtml(record.ticker)}}</div>
              </div>
              <div>${{signalBadge(record.signal)}}</div>
            </div>
            <div class="result-meta">
              <span class="pill">week ${{escapeHtml(record.week_end_date)}}</span>
              <span class="pill">confidence ${{Number(record.confidence).toFixed(2)}}</span>
              <span class="pill">position ${{Number(record.suggested_position_pct).toFixed(2)}}%</span>
            </div>
            <p class="result-summary">${{escapeHtml(record.summary)}}</p>
          </article>
        `;
      }}).join("");

      els.resultList.querySelectorAll(".result-card").forEach((node) => {{
        node.addEventListener("click", () => {{
          state.activeId = node.dataset.id;
          render();
        }});
      }});
    }}

    function renderDetail(record) {{
      if (!record) {{
        els.detailPanel.innerHTML = `<div class="empty">Select a decision to inspect the debate.</div>`;
        return;
      }}

      const weeklyContext = (SITE_DATA.weekly_rollups || []).find((item) => item.week_end_date === record.week_end_date);

      els.detailPanel.innerHTML = `
        <div>
          <div class="result-top">
            <div>
              <h2>${{escapeHtml(record.ticker)}}</h2>
              <p class="detail-subtitle">${{escapeHtml(record.summary)}}</p>
            </div>
            <div>${{signalBadge(record.signal)}}</div>
          </div>

          <div class="small-grid">
            <div class="small-card">
              <div class="metric-label">Judge Confidence</div>
              <div class="metric-value">${{Number(record.confidence).toFixed(2)}}</div>
              <div class="metric-note">Suggested position: ${{Number(record.suggested_position_pct).toFixed(2)}}%</div>
            </div>
            <div class="small-card">
              <div class="metric-label">Week Context</div>
              <div class="metric-value">${{escapeHtml(record.week_end_date)}}</div>
              <div class="metric-note">${{escapeHtml(record.portfolio_summary || weeklyContext?.portfolio_summary || "")}}</div>
            </div>
          </div>

          <div class="section">
            <div class="section-title">Bull Case</div>
            <p class="detail-subtitle">${{escapeHtml(record.bull_thesis)}}</p>
            ${{listHtml(record.bull_reasons)}}
          </div>

          <div class="section">
            <div class="section-title">Bear Case</div>
            <p class="detail-subtitle">${{escapeHtml(record.bear_thesis)}}</p>
            ${{listHtml(record.bear_reasons)}}
          </div>

          <div class="section">
            <div class="section-title">Judge Rationale</div>
            ${{listHtml(record.rationale)}}
          </div>

          <div class="section">
            <div class="section-title">Dissenting Points</div>
            ${{listHtml(record.dissenting_points)}}
          </div>

          <div class="section">
            <div class="section-title">Risk Flags</div>
            ${{listHtml(record.risk_flags)}}
          </div>

          <div class="section small-grid">
            <div class="small-card">
              <div class="section-title">Source Report Dates</div>
              <div class="metric-note">${{sourceDateHtml(record.source_report_dates)}}</div>
            </div>
            <div class="small-card">
              <div class="section-title">Score Breakdown</div>
              <div class="metric-note">${{scoreHtml(record.score_breakdown)}}</div>
            </div>
          </div>

          <div class="section">
            <div class="section-title">Weekly Timeline</div>
            <div class="timeline">
              ${{(SITE_DATA.weekly_rollups || []).slice(0, 12).map((item) => `
                <div class="timeline-item">
                  <strong>${{escapeHtml(item.week_end_date)}}</strong><br>
                  bullish ${{item.bullish_count}} | neutral ${{item.neutral_count}} | bearish ${{item.bearish_count}}<br>
                  top long: ${{escapeHtml(item.top_long_ticker || "n/a")}} (${{Number(item.top_long_weight || 0).toFixed(2)}}%)
                </div>
              `).join("")}}
            </div>
          </div>
        </div>
      `;
    }}

    function render() {{
      const records = filteredRecords();
      renderList(records);
      const activeRecord = records.find((record) => record.id === state.activeId) || records[0] || null;
      renderDetail(activeRecord);
    }}

    function bindEvents() {{
      els.keywordInput.addEventListener("input", (event) => {{
        state.keyword = event.target.value || "";
        render();
      }});

      els.tickerSelect.addEventListener("change", (event) => {{
        state.ticker = event.target.value;
        render();
      }});

      els.signalSelect.addEventListener("change", (event) => {{
        state.signal = event.target.value;
        render();
      }});

      els.weekSelect.addEventListener("change", (event) => {{
        state.week = event.target.value;
        render();
      }});

      els.resetButton.addEventListener("click", () => {{
        state.keyword = "";
        state.ticker = "ALL";
        state.signal = "ALL";
        state.week = "ALL";
        state.activeId = null;
        els.keywordInput.value = "";
        els.tickerSelect.value = "ALL";
        els.signalSelect.value = "ALL";
        els.weekSelect.value = "ALL";
        render();
      }});
    }}

    buildMetrics();
    buildFilters();
    bindEvents();
    render();
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a static DebateTrader demo site.")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output HTML path. Ignored when --publish-dir is set.",
    )
    parser.add_argument(
        "--publish-dir",
        type=str,
        default=None,
        help="Directory for GitHub Pages output, e.g. docs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = _resolve_output_path(args.output, args.publish_dir)
    site_payload = _build_site_payload()
    if args.publish_dir:
        site_payload["backtest_chart_path"] = _publish_backtest_chart(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_html_template(site_payload), encoding="utf-8")
    if args.publish_dir:
        _write_nojekyll(output_path)
    print(f"Demo site written to {output_path}")


if __name__ == "__main__":
    main()
