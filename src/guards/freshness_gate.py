# -*- coding: utf-8 -*-
"""
Financial data freshness gate for AI-assisted investment reports.

This module is intentionally dependency-light and can be used by CLI tasks,
GitHub Actions, WebUI/API handlers, or future agent workflows.

Core principle:
    No timestamp -> no trade.
    Stale data -> downgrade recommendation authority.
    LLM output must never upgrade the permission granted by this gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional


class FreshnessLevel(str, Enum):
    """Financial data freshness level."""

    L0 = "L0"  # unusable / missing timestamps
    L1 = "L1"  # stale background-only data
    L2 = "L2"  # daily / delayed reference data
    L3 = "L3"  # intraday auxiliary data
    L4 = "L4"  # trading-grade, timestamped data


class TradePermission(str, Enum):
    """Maximum trading authority allowed by data quality."""

    T0 = "T0"  # trading prohibited
    T1 = "T1"  # watch only
    T2 = "T2"  # small limit-only / low-buy only
    T3 = "T3"  # normal advice allowed, no aggressive sizing
    T4 = "T4"  # order-level advice allowed, still with risk checks


@dataclass(frozen=True)
class FreshnessPolicy:
    """Thresholds used to classify market data freshness."""

    l4_max_age_minutes: int = 15
    l3_max_age_minutes: int = 60
    l2_max_age_hours: int = 36
    high_volatility_symbols: frozenset[str] = frozenset()
    high_volatility_keywords: tuple[str, ...] = (
        "chip",
        "semiconductor",
        "ai",
        "oil",
        "crude",
        "leveraged",
        "inverse",
        "芯片",
        "半导体",
        "人工智能",
        "原油",
        "杠杆",
        "反向",
    )


DEFAULT_POLICY = FreshnessPolicy()


@dataclass
class DataAuditResult:
    symbol: str
    market: str = "unknown"
    source_name: str = "unknown"
    report_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    price_timestamp: Optional[datetime] = None
    volume_timestamp: Optional[datetime] = None
    turnover_timestamp: Optional[datetime] = None
    fund_flow_timestamp: Optional[datetime] = None
    news_timestamp: Optional[datetime] = None
    filing_timestamp: Optional[datetime] = None
    nav_timestamp: Optional[datetime] = None
    iopv_timestamp: Optional[datetime] = None
    position_timestamp: Optional[datetime] = None
    freshness_level: FreshnessLevel = FreshnessLevel.L0
    trade_permission: TradePermission = TradePermission.T0
    allow_buy: bool = False
    allow_sell: bool = False
    allow_overnight: bool = False
    allow_limit_order: bool = False
    missing_fields: list[str] = field(default_factory=list)
    stale_fields: list[str] = field(default_factory=list)
    conflict_fields: list[str] = field(default_factory=list)
    high_volatility_flag: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        def iso(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if isinstance(value, datetime) else None

        return {
            "symbol": self.symbol,
            "market": self.market,
            "source_name": self.source_name,
            "report_time": iso(self.report_time),
            "price_timestamp": iso(self.price_timestamp),
            "volume_timestamp": iso(self.volume_timestamp),
            "turnover_timestamp": iso(self.turnover_timestamp),
            "fund_flow_timestamp": iso(self.fund_flow_timestamp),
            "news_timestamp": iso(self.news_timestamp),
            "filing_timestamp": iso(self.filing_timestamp),
            "nav_timestamp": iso(self.nav_timestamp),
            "iopv_timestamp": iso(self.iopv_timestamp),
            "position_timestamp": iso(self.position_timestamp),
            "freshness_level": self.freshness_level.value,
            "trade_permission": self.trade_permission.value,
            "allow_buy": self.allow_buy,
            "allow_sell": self.allow_sell,
            "allow_overnight": self.allow_overnight,
            "allow_limit_order": self.allow_limit_order,
            "missing_fields": list(self.missing_fields),
            "stale_fields": list(self.stale_fields),
            "conflict_fields": list(self.conflict_fields),
            "high_volatility_flag": self.high_volatility_flag,
            "reason": self.reason,
        }

    def to_markdown(self) -> str:
        data = self.to_dict()
        rows = [
            ("标的", data["symbol"]),
            ("市场", data["market"]),
            ("数据源", data["source_name"]),
            ("报告时间", data["report_time"]),
            ("价格时间戳", data["price_timestamp"] or "缺失"),
            ("成交量/成交额时间戳", data["volume_timestamp"] or "缺失"),
            ("换手/量比时间戳", data["turnover_timestamp"] or "缺失"),
            ("资金流时间戳", data["fund_flow_timestamp"] or "缺失"),
            ("新闻时间戳", data["news_timestamp"] or "缺失"),
            ("公告/财报时间戳", data["filing_timestamp"] or "缺失"),
            ("NAV时间戳", data["nav_timestamp"] or "缺失"),
            ("IOPV时间戳", data["iopv_timestamp"] or "缺失"),
            ("用户仓位时间戳", data["position_timestamp"] or "未接入"),
            ("缺失项", ", ".join(data["missing_fields"]) or "无"),
            ("过期项", ", ".join(data["stale_fields"]) or "无"),
            ("冲突项", ", ".join(data["conflict_fields"]) or "无"),
            ("高波动资产", "是" if data["high_volatility_flag"] else "否"),
            ("数据新鲜度", data["freshness_level"]),
            ("交易权限", data["trade_permission"]),
            ("允许买入", "是" if data["allow_buy"] else "否"),
            ("允许卖出", "是" if data["allow_sell"] else "否"),
            ("允许隔夜", "是" if data["allow_overnight"] else "否"),
            ("允许限价单", "是" if data["allow_limit_order"] else "否"),
            ("降级原因", data["reason"]),
        ]
        body = "\n".join(f"| {k} | {v} |" for k, v in rows)
        return "\n".join([
            "## 数据审计",
            "",
            "| 项目 | 结果 |",
            "|---|---|",
            body,
        ])


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            # Common fallback: 2026-05-31 14:30:00
            try:
                dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _age(now: datetime, ts: Optional[datetime]) -> Optional[timedelta]:
    if ts is None:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return now - ts


def _is_high_volatility(symbol: str, market: str, description: str, policy: FreshnessPolicy) -> bool:
    key = symbol.upper().strip()
    if key in policy.high_volatility_symbols:
        return True
    text = f"{symbol} {market} {description}".lower()
    return any(keyword.lower() in text for keyword in policy.high_volatility_keywords)


def _downgrade_permission(permission: TradePermission) -> TradePermission:
    order = [TradePermission.T0, TradePermission.T1, TradePermission.T2, TradePermission.T3, TradePermission.T4]
    idx = order.index(permission)
    return order[max(0, idx - 1)]


def audit_market_data(
    symbol: str,
    *,
    market: str = "unknown",
    source_name: str = "unknown",
    now: Optional[datetime] = None,
    price_timestamp: Any = None,
    volume_timestamp: Any = None,
    turnover_timestamp: Any = None,
    fund_flow_timestamp: Any = None,
    news_timestamp: Any = None,
    filing_timestamp: Any = None,
    nav_timestamp: Any = None,
    iopv_timestamp: Any = None,
    position_timestamp: Any = None,
    description: str = "",
    conflict_fields: Optional[Iterable[str]] = None,
    policy: FreshnessPolicy = DEFAULT_POLICY,
) -> DataAuditResult:
    """Audit financial data freshness and return maximum allowed trading authority."""

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    timestamps = {
        "price_timestamp": _parse_datetime(price_timestamp),
        "volume_timestamp": _parse_datetime(volume_timestamp),
        "turnover_timestamp": _parse_datetime(turnover_timestamp),
        "fund_flow_timestamp": _parse_datetime(fund_flow_timestamp),
        "news_timestamp": _parse_datetime(news_timestamp),
        "filing_timestamp": _parse_datetime(filing_timestamp),
        "nav_timestamp": _parse_datetime(nav_timestamp),
        "iopv_timestamp": _parse_datetime(iopv_timestamp),
        "position_timestamp": _parse_datetime(position_timestamp),
    }

    missing_fields: list[str] = []
    stale_fields: list[str] = []
    conflicts = list(conflict_fields or [])

    # Hard requirements for any trade-related statement.
    for required in ("price_timestamp", "volume_timestamp"):
        if timestamps[required] is None:
            missing_fields.append(required)

    high_volatility = _is_high_volatility(symbol, market, description, policy)

    if missing_fields:
        return DataAuditResult(
            symbol=symbol,
            market=market,
            source_name=source_name,
            report_time=now,
            **timestamps,
            freshness_level=FreshnessLevel.L0,
            trade_permission=TradePermission.T0,
            allow_buy=False,
            allow_sell=False,
            allow_overnight=False,
            allow_limit_order=False,
            missing_fields=missing_fields,
            stale_fields=stale_fields,
            conflict_fields=conflicts,
            high_volatility_flag=high_volatility,
            reason="缺少价格或成交量/成交额时间戳；禁止交易建议，只允许补数据与观察。",
        )

    price_age = _age(now, timestamps["price_timestamp"])
    volume_age = _age(now, timestamps["volume_timestamp"])
    max_core_age = max(price_age or timedelta.max, volume_age or timedelta.max)

    if max_core_age <= timedelta(minutes=policy.l4_max_age_minutes):
        level = FreshnessLevel.L4
        permission = TradePermission.T4
        reason = "价格与成交量/成交额为15分钟内数据，可进入订单级建议，但仍需风控与仓位审计。"
    elif max_core_age <= timedelta(minutes=policy.l3_max_age_minutes):
        level = FreshnessLevel.L3
        permission = TradePermission.T3
        reason = "价格与成交量/成交额为小时级数据，可输出正常交易判断，但不得激进加仓。"
    elif max_core_age <= timedelta(hours=policy.l2_max_age_hours):
        level = FreshnessLevel.L2
        permission = TradePermission.T2
        reason = "核心行情为日级/延迟数据，只允许观察、小仓、低吸、限价与严格止损，不允许追高。"
    else:
        level = FreshnessLevel.L1
        permission = TradePermission.T1
        reason = "核心行情过旧，只能作为背景研究，不得形成买入、加仓、重仓或隔夜建议。"

    # Track optional stale fields without hard-failing the audit.
    optional_limits = {
        "turnover_timestamp": timedelta(hours=policy.l2_max_age_hours),
        "fund_flow_timestamp": timedelta(hours=policy.l2_max_age_hours),
        "news_timestamp": timedelta(days=7),
        "filing_timestamp": timedelta(days=120),
        "nav_timestamp": timedelta(hours=policy.l2_max_age_hours),
        "iopv_timestamp": timedelta(minutes=policy.l3_max_age_minutes),
        "position_timestamp": timedelta(hours=24),
    }
    for field_name, max_age in optional_limits.items():
        ts_age = _age(now, timestamps[field_name])
        if ts_age is not None and ts_age > max_age:
            stale_fields.append(field_name)

    if conflicts:
        permission = min(permission, TradePermission.T1, key=lambda x: [p.value for p in TradePermission].index(x.value))
        level = FreshnessLevel.L1
        reason = f"存在数据冲突字段 {conflicts}；交易权限降至T1，只能观察。"

    if high_volatility:
        downgraded = _downgrade_permission(permission)
        if downgraded != permission:
            permission = downgraded
            reason += " 高波动方向触发额外降级一档。"
            level = min(level, FreshnessLevel.L3, key=lambda x: [p.value for p in FreshnessLevel].index(x.value))

    allow_buy = permission in {TradePermission.T3, TradePermission.T4}
    allow_sell = permission in {TradePermission.T2, TradePermission.T3, TradePermission.T4}
    allow_overnight = permission == TradePermission.T4 and not high_volatility
    allow_limit_order = permission in {TradePermission.T2, TradePermission.T3, TradePermission.T4}

    return DataAuditResult(
        symbol=symbol,
        market=market,
        source_name=source_name,
        report_time=now,
        **timestamps,
        freshness_level=level,
        trade_permission=permission,
        allow_buy=allow_buy,
        allow_sell=allow_sell,
        allow_overnight=allow_overnight,
        allow_limit_order=allow_limit_order,
        missing_fields=missing_fields,
        stale_fields=stale_fields,
        conflict_fields=conflicts,
        high_volatility_flag=high_volatility,
        reason=reason,
    )


def enforce_recommendation_guard(audit: DataAuditResult, raw_advice: str) -> str:
    """Return a guarded advice string that cannot exceed audited permission."""

    prefix = audit.to_markdown()
    permission = audit.trade_permission

    if permission in {TradePermission.T0, TradePermission.T1}:
        guarded = (
            "\n\n## 强制交易结论\n\n"
            "- 当前禁止买入、加仓、重仓、追高、隔夜。\n"
            "- 只允许观察、补充数据、等待下一次有效时间戳。\n"
            f"- 原因：{audit.reason}\n"
        )
        return prefix + guarded

    if permission == TradePermission.T2:
        guarded = (
            "\n\n## 强制交易结论\n\n"
            "- 当前最多允许小仓、低吸、限价单与严格止损。\n"
            "- 禁止追高、禁止重仓、禁止把旧新闻当作实时资金流。\n"
            f"- 原因：{audit.reason}\n\n"
            "## 原始分析草稿（已降级，仅供参考）\n\n"
            f"{raw_advice.strip()}\n"
        )
        return prefix + guarded

    guarded = (
        "\n\n## 交易权限说明\n\n"
        f"- 当前权限：{permission.value}。允许输出交易建议，但必须附带失效条件、止损条件和仓位约束。\n"
        f"- 数据审计原因：{audit.reason}\n\n"
        "## 分析正文\n\n"
        f"{raw_advice.strip()}\n"
    )
    return prefix + guarded


def audit_from_mapping(symbol: str, payload: Mapping[str, Any], **kwargs: Any) -> DataAuditResult:
    """Convenience adapter for dict-like market data payloads."""

    return audit_market_data(
        symbol,
        market=str(payload.get("market") or kwargs.pop("market", "unknown")),
        source_name=str(payload.get("source") or payload.get("source_name") or kwargs.pop("source_name", "unknown")),
        price_timestamp=payload.get("price_timestamp") or payload.get("quote_time") or payload.get("timestamp"),
        volume_timestamp=payload.get("volume_timestamp") or payload.get("amount_timestamp") or payload.get("quote_time") or payload.get("timestamp"),
        turnover_timestamp=payload.get("turnover_timestamp") or payload.get("quote_time"),
        fund_flow_timestamp=payload.get("fund_flow_timestamp"),
        news_timestamp=payload.get("news_timestamp"),
        filing_timestamp=payload.get("filing_timestamp") or payload.get("announcement_timestamp"),
        nav_timestamp=payload.get("nav_timestamp"),
        iopv_timestamp=payload.get("iopv_timestamp"),
        position_timestamp=payload.get("position_timestamp"),
        description=str(payload.get("name") or payload.get("description") or ""),
        conflict_fields=payload.get("conflict_fields") or [],
        **kwargs,
    )
