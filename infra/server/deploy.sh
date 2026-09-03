#!/usr/bin/env bash
# 재배포: git pull → 의존성 갱신(변경 시) → 서비스 재시작 → 상태 출력. docs/06 §2b.
#   sudo bash /opt/breakZoneAutoApp/infra/server/deploy.sh [branch]
# 원칙: 장 마감 후 실행(재시작 시 전략상태는 strategy_state 에서 복원되지만 진행 중 주문 감시는 끊김).
set -euo pipefail
APP_DIR=/opt/breakZoneAutoApp
BOT_USER=bot
BRANCH="${1:-main}"
SVC=breakzone-bot

cd "$APP_DIR"
BEFORE=$(git rev-parse --short HEAD)
sudo -u $BOT_USER git fetch --all --prune
sudo -u $BOT_USER git checkout -q "$BRANCH"
sudo -u $BOT_USER git pull --ff-only
AFTER=$(git rev-parse --short HEAD)
echo "▶ $BEFORE → $AFTER"

if git diff --name-only "$BEFORE" "$AFTER" | grep -q '^engine/requirements.txt$'; then
  echo "▶ requirements 변경 → pip install"
  sudo -u $BOT_USER engine/.venv/bin/pip install -r engine/requirements.txt
fi
if git diff --name-only "$BEFORE" "$AFTER" | grep -q '^infra/server/breakzone-bot.service$'; then
  echo "▶ 서비스 유닛 변경 → 재설치"
  install -m 644 infra/server/breakzone-bot.service /etc/systemd/system/$SVC.service
  systemctl daemon-reload
fi

echo "▶ 테스트(빠른 회귀)"
sudo -u $BOT_USER bash -c "cd engine && .venv/bin/python -m pytest -q -x 2>&1 | tail -3"

echo "▶ 재시작"
systemctl restart $SVC
sleep 3
systemctl --no-pager --lines=0 status $SVC || true
journalctl -u $SVC -n 20 --no-pager
