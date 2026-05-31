#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/shajindi/AI-Company-Workspace/daily_stock_analysis}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
STOCKS="${STOCKS:-600519,hk00700,AAPL,NVDA,VOO}"
OUTPUT="${OUTPUT:-reports/task_1430_latest.md}"

printf '\n[1/7] Enter project directory\n'
cd "$PROJECT_DIR"
pwd

printf '\n[2/7] Pull latest repository changes\n'
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git pull origin main || {
    echo "git pull failed. If this is a GitHub network problem, run it again after checking proxy/SSH."
    exit 1
  }
else
  echo "Not a git repository: $PROJECT_DIR"
  exit 1
fi

printf '\n[3/7] Create virtual environment if missing\n'
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

printf '\n[4/7] Activate virtual environment\n'
# shellcheck disable=SC1091
source .venv/bin/activate
python -V

printf '\n[5/7] Install project and finance dependencies\n'
python -m pip install --upgrade pip -i "$PIP_INDEX"
python -m pip install -r requirements.txt -i "$PIP_INDEX"
python -m pip install yfinance akshare tushare vectorbt -i "$PIP_INDEX"

printf '\n[6/7] Run 14:30 overnight risk task\n'
mkdir -p "$(dirname "$OUTPUT")"
python src/user_tasks/task_1430_overnight_risk.py \
  --stocks "$STOCKS" \
  --output "$OUTPUT"

printf '\n[7/7] Done\n'
echo "Report generated: $PROJECT_DIR/$OUTPUT"
echo "Open it in Cursor: $OUTPUT"
