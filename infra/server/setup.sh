#!/usr/bin/env bash
# 클라우드 VM 최초 설치 (Ubuntu 22.04/24.04). docs/06 §4. 1회 실행, root(sudo)로.
#   sudo bash setup.sh <git-repo-url> [branch]
# 하는 일: 시스템 패키지 → bot 사용자 → /opt/breakZoneAutoApp clone → venv+deps → systemd 서비스 등록.
# 시크릿(.env)은 이 스크립트가 만들지 않는다. 설치 후 /opt/breakZoneAutoApp/engine/.env 를 직접 배치할 것.
set -euo pipefail

REPO_URL="${1:?사용법: sudo bash setup.sh <git-repo-url> [branch]}"
BRANCH="${2:-main}"
APP_DIR=/opt/breakZoneAutoApp
BOT_USER=bot
PY=python3.12

echo "▶ 시스템 패키지"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git curl ca-certificates software-properties-common
if ! command -v $PY >/dev/null 2>&1; then
  echo "▶ $PY 없음 → deadsnakes PPA (Ubuntu 22.04)"
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update -y
fi
apt-get install -y $PY $PY-venv $PY-dev build-essential

echo "▶ 타임존 KST"
timedatectl set-timezone Asia/Seoul || true

echo "▶ 사용자 $BOT_USER"
id -u $BOT_USER >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash $BOT_USER

echo "▶ 코드 clone → $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch --all && git -C "$APP_DIR" checkout "$BRANCH" && git -C "$APP_DIR" pull --ff-only
fi
chown -R $BOT_USER:$BOT_USER "$APP_DIR"

echo "▶ venv + 의존성"
sudo -u $BOT_USER bash -c "cd $APP_DIR/engine && $PY -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt"

echo "▶ systemd 서비스"
install -m 644 "$APP_DIR/infra/server/breakzone-bot.service" /etc/systemd/system/breakzone-bot.service
systemctl daemon-reload
systemctl enable breakzone-bot.service

cat <<MSG

✅ 설치 완료. 남은 작업:
  1) 시크릿 배치:   $APP_DIR/engine/.env   (소유자 $BOT_USER, 권한 600)
       예)  sudo install -m 600 -o $BOT_USER -g $BOT_USER /tmp/.env $APP_DIR/engine/.env
     .env 에 BOT_HOLDER_ID=cloud-seoul, BOT_DRY_RUN=0 권장.
  2) 스모크:        sudo -u $BOT_USER $APP_DIR/engine/.venv/bin/python -m tools.check_kiwoom_token  (engine/ 에서)
  3) 시작:          sudo systemctl start breakzone-bot && journalctl -u breakzone-bot -f
  재배포:           sudo bash $APP_DIR/infra/server/deploy.sh
MSG
