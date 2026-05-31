# -*- coding: utf-8 -*-
"""
14:30 Tail-risk and overnight-position decision task.

This is a non-invasive user task entrypoint. It does not replace the upstream
DSA pipeline. It gives shajindi a dedicated guard-first report that can be run
from Cursor, local terminal, or GitHub Actions.

Usage:
    python src/user_tasks/task_1430_overnight_risk.py --stocks 600519,hk00700,AAPL
    python src/user_tasks/task_1430_overnight_risk.py --stocks 600519,hk00700,AAPL --output reports/task_1430.md
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Allow direct execution from repository root without installing the package.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.guards.freshness_gate import DataAuditResult, TradePermission, audit_from_mapping, audit_market_data


@dataclass
class Task1430Config:
    stocks: List[str]
    output: Optional[Path] = None
    source: str = "manual_or_project_data"
    report_time: datetime = datetime.now(timezone.utc)
    position_file: Optional[Path] = None


def _split_stocks(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _infer_market(symbol: str) -> str:
    text = symbol.strip().lower()
    if text.startswith("hk"):
        return "HK"
    if text.isdigit() and len(text) == 6:
        return "CN-A"
    if text.endswith(".sz") or text.endswith(".ss") or text.endswith(".sh"):
        return "CN-A"
    return "US-or-unknown"


def _load_positions(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _placeholder_payload(symbol: str, source: str) -> Dict[str, Any]:
    """Return an explicit no-timestamp payload.

    This intentionally produces T0 until real data adapters pass timestamps.
    It prevents the task from pretending it has live market data.
    """

    return {
        "symbol": symbol,
        "market": _infer_market(symbol),
        "source": source,
        "price_timestamp": None,
        "volume_timestamp": None,
        "fund_flow_timestamp": None,
        "news_timestamp": None,
        "filing_timestamp": None,
        "name": symbol,
    }


def build_stock_audit(symbol: str, config: Task1430Config, positions: Dict[str, Any]) -> DataAuditResult:
    payload = _placeholder_payload(symbol, config.source)
    position_payload = positions.get(symbol) or positions.get(symbol.upper()) or positions.get(symbol.lower())
    if isinstance(position_payload, dict):
        payload["position_timestamp"] = position_payload.get("timestamp") or position_payload.get("position_timestamp")
    return audit_from_mapping(symbol, payload, now=config.report_time)


def _permission_rank(permission: TradePermission) -> int:
    order = [TradePermission.T0, TradePermission.T1, TradePermission.T2, TradePermission.T3, TradePermission.T4]
    return order.index(permission)


def _portfolio_permission(audits: Iterable[DataAuditResult]) -> TradePermission:
    audits = list(audits)
    if not audits:
        return TradePermission.T0
    return min((audit.trade_permission for audit in audits), key=_permission_rank)


def _action_for_audit(audit: DataAuditResult) -> str:
    if audit.trade_permission in {TradePermission.T0, TradePermission.T1}:
        return "禁止买入/加仓/隔夜；只允许观察和补充实时数据。"
    if audit.trade_permission == TradePermission.T2:
        return "最多小仓低吸或减仓；只允许限价单，禁止追高和重仓。"
    if audit.trade_permission == TradePermission.T3:
        return "允许正常交易判断，但不允许激进隔夜；必须有止损和失效条件。"
    return "允许进入订单级判断；仍需仓位、流动性、公告和风险审批。"


def render_report(config: Task1430Config, audits: List[DataAuditResult]) -> str:
    permission = _portfolio_permission(audits)
    allow_any_buy = any(a.allow_buy for a in audits)
    allow_any_sell = any(a.allow_sell for a in audits)
    allow_overnight = all(a.allow_overnight for a in audits) and bool(audits)

    lines: List[str] = []
    lines.append("# 14:30 尾盘交易与隔夜风险决议")
    lines.append("")
    lines.append(f"- 报告时间：{config.report_time.isoformat()}")
    lines.append(f"- 股票池：{', '.join(config.stocks) if config.stocks else '未提供'}")
    lines.append(f"- 组合级交易权限：{permission.value}")
    lines.append(f"- 是否允许买入：{'是' if allow_any_buy else '否'}")
    lines.append(f"- 是否允许卖出/减仓：{'是' if allow_any_sell else '否'}")
    lines.append(f"- 是否允许隔夜：{'是' if allow_overnight else '否'}")
    lines.append("")

    lines.append("## 交易员速读版")
    lines.append("")
    if permission in {TradePermission.T0, TradePermission.T1}:
        lines.append("当前数据审计未通过。禁止买入、加仓、重仓、追高和新增隔夜；只能观察、补数据或处理已有风险敞口。")
    elif permission == TradePermission.T2:
        lines.append("当前只允许防守型操作：小仓、低吸、限价、严格止损；不得追高，不得主动扩大隔夜风险。")
    elif permission == TradePermission.T3:
        lines.append("当前允许正常判断，但隔夜资格仍需逐标的审批；高波动方向自动降级。")
    else:
        lines.append("当前数据达到订单级判断门槛；仍需结合实际仓位、现金、流动性和公告风险执行。")
    lines.append("")

    lines.append("## A股/港股权重决策")
    lines.append("")
    lines.append("- 未接入用户实时仓位和可用现金前，不给个性化仓位比例。")
    lines.append("- 默认战略观察权重仍按 A股50% / 港股50%，但今日是否调仓必须由数据审计决定。")
    lines.append("- 公司70% + ETF/基金30%的框架保留；未通过T3/T4前，不执行新增买入。")
    lines.append("")

    lines.append("## 唯一买入/卖出机会审批")
    lines.append("")
    lines.append(f"- 今日唯一买入机会：{'可进入候选审批' if allow_any_buy else '放弃/禁止使用'}")
    lines.append(f"- 今日唯一卖出机会：{'可用于风险减仓或止损' if allow_any_sell else '仅观察，除非用户手动提供实时仓位与价格'}")
    lines.append("- 14:30任务核心不是抢先手，而是审批隔夜资格；数据不完整时宁可错过，不可用旧数据开仓。")
    lines.append("")

    lines.append("## 标的级数据审计与动作")
    lines.append("")
    lines.append("| 标的 | 市场 | 数据源 | 新鲜度 | 权限 | 买入 | 卖出 | 隔夜 | 强制动作 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for audit in audits:
        lines.append(
            f"| {audit.symbol} | {audit.market} | {audit.source_name} | "
            f"{audit.freshness_level.value} | {audit.trade_permission.value} | "
            f"{'是' if audit.allow_buy else '否'} | "
            f"{'是' if audit.allow_sell else '否'} | "
            f"{'是' if audit.allow_overnight else '否'} | {_action_for_audit(audit)} |"
        )
    lines.append("")

    for audit in audits:
        lines.append(audit.to_markdown())
        lines.append("")

    lines.append("## 禁止交易清单")
    lines.append("")
    blocked = [a for a in audits if a.trade_permission in {TradePermission.T0, TradePermission.T1}]
    if blocked:
        for audit in blocked:
            lines.append(f"- {audit.symbol}：{audit.reason}")
    else:
        lines.append("- 暂无T0/T1标的，但仍需检查真实仓位、公告、流动性和盘面结构。")
    lines.append("")

    lines.append("## 失效条件")
    lines.append("")
    lines.append("- 任一核心数据时间戳缺失或冲突，交易权限立即降为T0/T1。")
    lines.append("- 无资金流时间戳时，不得声称主力流入或流出。")
    lines.append("- 无成交额/成交量时间戳时，不得声称放量突破或缩量回踩。")
    lines.append("- 无ETF净值/IOPV时，不得判断ETF/LOF溢折价。")
    lines.append("- 无用户真实仓位时，不得输出个性化仓位比例。")
    lines.append("- 芯片、半导体、AI、原油、杠杆/反向ETF自动采用更严格阈值。")
    lines.append("")

    lines.append("## 下一步接入点")
    lines.append("")
    lines.append("1. 将 daily_stock_analysis 的实时行情结果传入 freshness_gate。")
    lines.append("2. 将 AkShare/Tushare/yfinance/OpenBB 的数据时间戳标准化。")
    lines.append("3. 将用户真实仓位保存为 JSON 或数据库表，并传入 position_timestamp。")
    lines.append("4. 在 GitHub Actions 中新增 14:30 北京时间 cron。")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="14:30 尾盘交易与隔夜风险决议")
    parser.add_argument("--stocks", required=True, help="逗号分隔股票池，如 600519,hk00700,AAPL")
    parser.add_argument("--output", default=None, help="输出 Markdown 文件路径")
    parser.add_argument("--source", default="manual_or_project_data", help="数据源名称")
    parser.add_argument("--position-file", default=None, help="用户仓位 JSON 文件，可选")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Task1430Config(
        stocks=_split_stocks(args.stocks),
        output=Path(args.output) if args.output else None,
        source=args.source,
        report_time=datetime.now(timezone.utc),
        position_file=Path(args.position_file) if args.position_file else None,
    )
    positions = _load_positions(config.position_file)
    audits = [build_stock_audit(symbol, config, positions) for symbol in config.stocks]
    report = render_report(config, audits)

    if config.output:
        config.output.parent.mkdir(parents=True, exist_ok=True)
        config.output.write_text(report, encoding="utf-8")
        print(f"报告已生成: {config.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
