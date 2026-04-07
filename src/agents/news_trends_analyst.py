"""
News Trends Analyst Agent

Summary
-------
This module implements the News Trends Analyst agent for DebateTrader.

Responsibilities
----------------
- Receive a cleaned news/macro snapshot for a stock
- Evaluate recent company-news tone only
- Produce a structured JSON-friendly analysis report
"""

from __future__ import annotations

from src.schemas.analyst_output import AnalystOutput


class NewsTrendsAnalyst:
    """Rule-based news trends analyst agent."""

    def analyze(self, snapshot: dict) -> AnalystOutput:
        ticker = snapshot["ticker"]
        analysis_date = snapshot["analysis_date"]
        news = snapshot["news_macro_features"]["news_summary"]
        trends = snapshot["news_macro_features"].get("trends_summary", {})

        bullish_factors: list[str] = []
        bearish_factors: list[str] = []
        risk_flags: list[str] = []

        bullish_score = 0
        bearish_score = 0

        article_count = news.get("article_count")
        raw_article_count = news.get("raw_article_count")
        relevant_article_count = news.get("relevant_article_count")
        relevance_ratio = news.get("relevance_ratio")
        positive_articles = news.get("positive_articles")
        negative_articles = news.get("negative_articles")
        avg_sentiment_score = news.get("avg_sentiment_score")
        uncertainty_articles = news.get("uncertainty_articles")
        litigious_articles = news.get("litigious_articles")
        avg_uncertainty_hits = news.get("avg_uncertainty_hits")
        has_trends_data = trends.get("has_trends_data")
        current_week_avg = trends.get("current_week_avg")
        previous_week_avg = trends.get("previous_week_avg")
        wow_change = trends.get("wow_change")
        latest_search_interest = trends.get("latest_search_interest")
        current_week_peak = trends.get("current_week_peak")

        if article_count == 0:
            risk_flags.append("No recent company news available")
        else:
            directional_total = positive_articles + negative_articles
            if directional_total > 0:
                positive_share = positive_articles / directional_total
                negative_share = negative_articles / directional_total
                if positive_share >= 0.55:
                    bullish_score += 1
                    bullish_factors.append("Recent company news flow is majority positive.")
                elif negative_share >= 0.55:
                    bearish_score += 1
                    bearish_factors.append("Recent company news flow is majority negative.")

            if avg_sentiment_score is not None:
                if avg_sentiment_score > 0.25:
                    bullish_score += 1
                    bullish_factors.append("Average LM news sentiment is modestly positive.")
                elif avg_sentiment_score < -0.25:
                    bearish_score += 1
                    bearish_factors.append("Average LM news sentiment is modestly negative.")

            if litigious_articles is not None and litigious_articles > 0:
                risk_flags.append("Litigious language appears in recent news")

        trend_score = 0
        if has_trends_data:
            if wow_change is not None:
                if wow_change >= 0.15:
                    trend_score = 1
                    bullish_factors.append(
                        f"Google Trends search interest is up {wow_change:.0%} week-over-week."
                    )
                elif wow_change <= -0.15:
                    trend_score = -1
                    bearish_factors.append(
                        f"Google Trends search interest is down {abs(wow_change):.0%} week-over-week."
                    )

            if current_week_peak is not None and current_week_peak >= 80:
                risk_flags.append("Retail attention spike may indicate crowded positioning")

        # Relevance-based risk flags are temporarily disabled.
        # The current heuristic relies on headline/summary text only, while
        # some news items may mention the company mainly in the full article
        # body or attached video content.
        #
        # if raw_article_count and relevant_article_count is not None:
        #     if relevant_article_count == 0:
        #         risk_flags.append("Recent news may be weakly company-specific")
        #     elif relevance_ratio is not None and relevance_ratio < 0.4:
        #         risk_flags.append("Low estimated news relevance ratio")

        news_score_diff = bullish_score - bearish_score
        news_component = max(-1.0, min(1.0, news_score_diff / 2.0))
        trend_component = float(trend_score)
        combined_score = 0.8 * news_component + 0.2 * trend_component

        if combined_score >= 0.35:
            signal = "bullish"
        elif combined_score <= -0.35:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(0.85, 0.50 + abs(combined_score) * 0.25)
        if article_count and avg_uncertainty_hits is not None and avg_uncertainty_hits >= 0.5:
            confidence = max(0.5, confidence - 0.04)

        if signal == "bullish":
            summary = "Recent news trends are broadly supportive, with more bullish than bearish evidence."
        elif signal == "bearish":
            summary = "Recent news trends lean cautious, with more bearish than bullish evidence."
        else:
            summary = "Recent news trends are mixed, without a strong directional edge."

        return AnalystOutput(
            agent_name="NewsTrendsAnalyst",
            ticker=ticker,
            analysis_date=analysis_date,
            signal=signal,
            confidence=round(confidence, 2),
            summary=summary,
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            risk_flags=sorted(set(risk_flags)),
            key_metrics_used={
                "article_count": article_count,
                "raw_article_count": raw_article_count,
                "relevant_article_count": relevant_article_count,
                "relevance_ratio": relevance_ratio,
                "positive_articles": positive_articles,
                "negative_articles": negative_articles,
                "avg_sentiment_score": avg_sentiment_score,
                "uncertainty_articles": uncertainty_articles,
                "litigious_articles": litigious_articles,
                "avg_uncertainty_hits": avg_uncertainty_hits,
                "has_trends_data": has_trends_data,
                "current_week_avg": current_week_avg,
                "previous_week_avg": previous_week_avg,
                "wow_change": wow_change,
                "latest_search_interest": latest_search_interest,
                "current_week_peak": current_week_peak,
                "news_score_diff": news_score_diff,
                "trend_score": trend_score,
                "combined_score": round(combined_score, 4),
            },
        )
