from __future__ import annotations

from typing import Any

from core.config import PAPER_SIGNAL_PROFILE_PRESETS, PaperSignalConfig
from paper_trading.models import PaperSignal
from scoring.models import ScoreResult


CONFIDENCE_RANK = {"Low": 0, "Medium": 1, "High": 2}


class PaperSignalBuilder:
    """Converts deterministic research scores into configurable simulated-only paper signals."""

    def __init__(
        self,
        signal_config: PaperSignalConfig | None = None,
        default_risk_pct: float = 0.25,
    ) -> None:
        self.signal_config = signal_config or _default_signal_config()
        self.default_risk_pct = default_risk_pct

    def build_signal(self, score: ScoreResult | dict[str, Any], latest_price: float | None = None) -> PaperSignal:
        normalized = _normalize_score(score)
        asset = normalized["asset"]
        total_score = normalized["total_score"]
        bias = normalized["bias"]
        confidence = normalized["confidence"]
        data_completeness = normalized["data_completeness"]
        reasons: list[str] = [
            (
                f"{asset} paper signal evaluated under profile={self.signal_config.profile}, "
                f"score={total_score}, bias={bias}, confidence={confidence}, "
                f"data_completeness={data_completeness}%."
            )
        ]
        warnings: list[str] = ["PAPER TRADE candidate only; no real order capability is used."]
        if self.signal_config.profile == "exploratory" or self.signal_config.exploratory_mode:
            warnings.append("Exploratory paper-signal tuning is enabled. This is experimental and simulated-only.")

        threshold_context = _threshold_context(self.signal_config, asset)
        candidate_direction = _candidate_direction(
            total_score=total_score,
            bias=bias,
            allow_neutral_bias=self.signal_config.allow_neutral_bias,
            long_threshold=threshold_context["long_threshold"],
            short_threshold=threshold_context["short_threshold"],
        )

        review_reasons: list[dict[str, str]] = []
        if candidate_direction is None:
            review_reasons.extend(
                _no_trade_score_reasons(
                    total_score=total_score,
                    bias=bias,
                    allow_neutral_bias=self.signal_config.allow_neutral_bias,
                    long_threshold=threshold_context["long_threshold"],
                    short_threshold=threshold_context["short_threshold"],
                )
            )
            reasons.append("No paper trade: score and bias thresholds were not met for this profile.")
            return self._no_trade(asset, normalized, reasons, warnings, review_reasons)

        if _confidence_value(confidence) < _confidence_value(self.signal_config.min_confidence):
            review_reasons.append(
                _reason(
                    "CONFIDENCE_TOO_LOW",
                    f"Confidence {confidence} is below the minimum {self.signal_config.min_confidence}.",
                )
            )
            reasons.append(f"No paper trade: confidence is below {self.signal_config.min_confidence}.")
            return self._no_trade(asset, normalized, reasons, warnings, review_reasons)

        if data_completeness < threshold_context["min_data_completeness"]:
            review_reasons.append(
                _reason(
                    "DATA_COMPLETENESS_TOO_LOW",
                    f"Data completeness {data_completeness}% is below the minimum {threshold_context['min_data_completeness']}%.",
                )
            )
            reasons.append(
                f"No paper trade: data completeness is below {threshold_context['min_data_completeness']}%."
            )
            return self._no_trade(asset, normalized, reasons, warnings, review_reasons)

        signal = self._trade_signal(
            asset=asset,
            direction=candidate_direction,
            score=normalized,
            latest_price=latest_price,
            reasons=[
                *reasons,
                (
                    f"{candidate_direction.title()} paper candidate passed profile thresholds "
                    f"({threshold_context['label']} long={threshold_context['long_threshold']}, "
                    f"short={threshold_context['short_threshold']})."
                ),
            ],
            warnings=warnings,
        )
        return PaperSignal(
            asset=signal.asset,
            direction=signal.direction,
            signal_source=signal.signal_source,
            score=signal.score,
            bias=signal.bias,
            confidence=signal.confidence,
            data_completeness=signal.data_completeness,
            intended_entry=signal.intended_entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            risk_pct=signal.risk_pct,
            reasons=signal.reasons,
            warnings=signal.warnings,
            active_profile=self.signal_config.profile,
            review_reasons=[],
        )

    def _trade_signal(
        self,
        asset: str,
        direction: str,
        score: dict[str, Any],
        latest_price: float | None,
        reasons: list[str],
        warnings: list[str],
    ) -> PaperSignal:
        if latest_price is None:
            reasons.append("No latest persisted price is available; risk engine must reject this signal.")
            return PaperSignal(
                asset=asset,
                direction=direction,
                signal_source=f"paper_signal_{self.signal_config.profile}",
                score=score["total_score"],
                bias=score["bias"],
                confidence=score["confidence"],
                data_completeness=score["data_completeness"],
                risk_pct=self.default_risk_pct,
                reasons=reasons,
                warnings=warnings,
                active_profile=self.signal_config.profile,
            )

        if direction == "LONG":
            stop_loss = latest_price * 0.98
            take_profit = latest_price * 1.04
        else:
            stop_loss = latest_price * 1.02
            take_profit = latest_price * 0.96

        return PaperSignal(
            asset=asset,
            direction=direction,
            signal_source=f"paper_signal_{self.signal_config.profile}",
            score=score["total_score"],
            bias=score["bias"],
            confidence=score["confidence"],
            data_completeness=score["data_completeness"],
            intended_entry=latest_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_pct=self.default_risk_pct,
            reasons=reasons,
            warnings=warnings,
            active_profile=self.signal_config.profile,
        )

    def _no_trade(
        self,
        asset: str,
        score: dict[str, Any],
        reasons: list[str],
        warnings: list[str],
        review_reasons: list[dict[str, str]],
    ) -> PaperSignal:
        return PaperSignal(
            asset=asset,
            direction="NO_TRADE",
            signal_source=f"paper_signal_{self.signal_config.profile}",
            score=score["total_score"],
            bias=score["bias"],
            confidence=score["confidence"],
            data_completeness=score["data_completeness"],
            risk_pct=0.0,
            reasons=reasons,
            warnings=warnings,
            active_profile=self.signal_config.profile,
            review_reasons=review_reasons,
        )


def _normalize_score(score: ScoreResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(score, ScoreResult):
        return {
            "asset": score.asset,
            "total_score": int(score.total_score),
            "bias": score.bias,
            "confidence": score.confidence,
            "data_completeness": int(score.data_completeness),
        }

    return {
        "asset": str(score.get("asset", "UNKNOWN")),
        "total_score": int(score.get("total_score", score.get("score", 0))),
        "bias": str(score.get("bias", "Neutral")),
        "confidence": str(score.get("confidence", "Low")),
        "data_completeness": int(score.get("data_completeness", 0)),
    }


def _threshold_context(signal_config: PaperSignalConfig, asset: str) -> dict[str, int | str]:
    if asset == "BTC":
        return {
            "label": "BTC",
            "long_threshold": signal_config.btc_long_score_threshold,
            "short_threshold": signal_config.btc_short_score_threshold,
            "min_data_completeness": signal_config.min_btc_data_completeness,
        }
    return {
        "label": "Gold",
        "long_threshold": signal_config.gold_long_score_threshold,
        "short_threshold": signal_config.gold_short_score_threshold,
        "min_data_completeness": signal_config.min_gold_data_completeness,
    }


def _candidate_direction(
    total_score: int,
    bias: str,
    allow_neutral_bias: bool,
    long_threshold: int,
    short_threshold: int,
) -> str | None:
    long_bias_ok = bias == "Bullish" or (allow_neutral_bias and bias == "Neutral")
    short_bias_ok = bias == "Bearish" or (allow_neutral_bias and bias == "Neutral")

    if long_bias_ok and total_score >= long_threshold:
        return "LONG"
    if short_bias_ok and total_score <= short_threshold:
        return "SHORT"
    return None


def _no_trade_score_reasons(
    total_score: int,
    bias: str,
    allow_neutral_bias: bool,
    long_threshold: int,
    short_threshold: int,
) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if bias not in {"Bullish", "Bearish"} and not (allow_neutral_bias and bias == "Neutral"):
        reasons.append(
            _reason(
                "BIAS_NOT_ALLOWED",
                f"Bias {bias} is not allowed for paper signal generation under the active profile.",
            )
        )
    elif bias == "Neutral" and not allow_neutral_bias:
        reasons.append(
            _reason(
                "BIAS_NOT_ALLOWED",
                "Neutral bias is disabled for the active paper-signal profile.",
            )
        )

    if total_score < long_threshold:
        reasons.append(
            _reason(
                "SCORE_BELOW_LONG_THRESHOLD",
                f"Score {total_score} is below the long threshold {long_threshold}.",
            )
        )
    if total_score > short_threshold:
        reasons.append(
            _reason(
                "SCORE_ABOVE_SHORT_THRESHOLD",
                f"Score {total_score} is above the short threshold {short_threshold}.",
            )
        )

    if not reasons:
        reasons.append(
            _reason(
                "BIAS_NOT_ALLOWED",
                "The active score, bias, and profile combination did not produce a paper trade candidate.",
            )
        )
    return reasons


def _confidence_value(value: str) -> int:
    return CONFIDENCE_RANK.get(value, -1)


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _default_signal_config() -> PaperSignalConfig:
    preset = PAPER_SIGNAL_PROFILE_PRESETS["conservative"]
    return PaperSignalConfig(
        profile="conservative",
        btc_long_score_threshold=int(preset["btc_long_score_threshold"]),
        btc_short_score_threshold=int(preset["btc_short_score_threshold"]),
        gold_long_score_threshold=int(preset["gold_long_score_threshold"]),
        gold_short_score_threshold=int(preset["gold_short_score_threshold"]),
        min_confidence=str(preset["min_confidence"]),
        min_btc_data_completeness=int(preset["min_btc_data_completeness"]),
        min_gold_data_completeness=int(preset["min_gold_data_completeness"]),
        allow_neutral_bias=bool(preset["allow_neutral_bias"]),
        exploratory_mode=bool(preset["exploratory_mode"]),
    )
