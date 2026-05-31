# Shajindi Finance OS Quickstart

本文件用于把 `daily_stock_analysis` 先改造成“数据新鲜度审计 + 14:30尾盘隔夜风险决议”的最小可运行版本。

## 1. 当前新增文件

```text
src/guards/freshness_gate.py
src/user_tasks/task_1430_overnight_risk.py
docs/shajindi_finance_os_quickstart.md
```

## 2. 核心原则

- 无价格时间戳：禁止交易建议。
- 无成交量/成交额时间戳：禁止判断放量、缩量、突破、回踩。
- 无资金流时间戳：禁止判断主力流入/流出。
- 无ETF净值/IOPV：禁止判断ETF/LOF溢折价。
- 无用户真实仓位：禁止输出个性化仓位比例。
- T0/T1：只观察，禁止买入、加仓、重仓、追高、隔夜。
- T2：最多小仓、低吸、限价、严格止损，禁止追高。
- T3/T4：才允许正常交易建议，但必须有失效条件。

## 3. 在 Cursor 里拉取最新代码

```bash
git pull origin main
```

如果本地还没有项目：

```bash
cd ~/Desktop
git clone https://github.com/shajindi-gif/daily_stock_analysis.git
cd daily_stock_analysis
```

## 4. 创建环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 5. 运行 14:30 尾盘隔夜风险决议

当前版本是“防错优先”的外挂任务。因为还没有接入实时行情适配器，所以默认会输出 T0，防止旧数据触发交易。

```bash
python src/user_tasks/task_1430_overnight_risk.py --stocks 600519,hk00700,AAPL,NVDA,VOO
```

输出到 Markdown：

```bash
python src/user_tasks/task_1430_overnight_risk.py \
  --stocks 600519,hk00700,AAPL,NVDA,VOO \
  --output reports/task_1430_latest.md
```

## 6. 可选：接入用户仓位文件

新建：

```bash
mkdir -p data/user
cat > data/user/positions.json <<'JSON'
{
  "600519": {
    "shares": 0,
    "cost": 0,
    "timestamp": "2026-05-31T06:30:00+08:00"
  },
  "hk00700": {
    "shares": 0,
    "cost": 0,
    "timestamp": "2026-05-31T06:30:00+08:00"
  }
}
JSON
```

运行：

```bash
python src/user_tasks/task_1430_overnight_risk.py \
  --stocks 600519,hk00700,AAPL,NVDA,VOO \
  --position-file data/user/positions.json \
  --output reports/task_1430_latest.md
```

## 7. 下一步接入真实数据

下一阶段不要直接改 LLM prompt，而要先把现有 pipeline 的行情数据统一转为下面字段：

```python
payload = {
    "symbol": "600519",
    "market": "CN-A",
    "source": "akshare_or_existing_fetcher",
    "price_timestamp": "2026-05-31T14:25:00+08:00",
    "volume_timestamp": "2026-05-31T14:25:00+08:00",
    "fund_flow_timestamp": "2026-05-31T14:20:00+08:00",
    "news_timestamp": "2026-05-31T13:50:00+08:00",
    "filing_timestamp": "2026-05-30T22:00:00+08:00",
    "position_timestamp": "2026-05-31T13:40:00+08:00",
}
```

然后调用：

```python
from src.guards.freshness_gate import audit_from_mapping

audit = audit_from_mapping("600519", payload)
print(audit.to_markdown())
```

## 8. 推荐 Cursor Agent 提示词

```text
请阅读 src/guards/freshness_gate.py 和 src/user_tasks/task_1430_overnight_risk.py。
下一步目标：把 daily_stock_analysis 现有实时行情获取结果转换为 freshness_gate 所需 payload，并在每只股票报告开头插入 audit.to_markdown()。
要求：不要大规模重构；只做最小侵入式接入；若无法取得某个时间戳，必须显式传 None，让权限自动降级，不允许编造时间戳。
```

## 9. 失败回滚

查看最近提交：

```bash
git log --oneline -5
```

如果只想回滚新增文件：

```bash
git rm src/guards/freshness_gate.py
 git rm src/user_tasks/task_1430_overnight_risk.py
 git rm docs/shajindi_finance_os_quickstart.md
 git commit -m "revert: remove shajindi finance os prototype"
 git push origin main
```
