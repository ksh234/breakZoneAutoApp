# 06 · 배포 — 집 PC 구동 & 클라우드 이관

> outbound-only 설계(docs/00 §3) 덕분에 "이관 = 봇 프로세스 이동". 여기선 실제 구동/이관 절차.

---

## 1. 로컬 개발 실행 (집 PC)

```bash
# engine
cd engine
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
copy .env.example .env    # 키 채우기 (KIWOOM_*, SUPABASE_*)
python -m src.main
```
- `.env`: `KIWOOM_MODE=demo`, `KIWOOM_APP_KEY/SECRET`, `KIWOOM_ACCOUNT_NO`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, 로그레벨 등.
- 로그: `logs/engine.log`(RotatingFileHandler, breakZone `run.py` 방식 재사용).

## 2. 집 Windows PC 상시(간헐) 구동

옵션:
- **작업 스케줄러:** 로그온 시/장 시작 시 봇 실행. 가장 간단.
- **NSSM(서비스화):** 봇을 Windows 서비스로 등록 → 부팅 시 자동, 크래시 재시작.
- 절전/최대절전 방지(장중). 인터넷 안정성 확인.
- 봇은 인바운드 포트 불필요 → **방화벽/포트포워딩 설정 없음**.

주의: 집 PC는 정전·절전·업데이트 재부팅으로 끊길 수 있다 → 하트비트로 앱에서 감지. 상시성이 중요해지면 클라우드로(아래).

### 2b. 클라우드 이관 후 PC 의 역할 = 개발·드라이런 (D-015)
- PC `.env` 에 **`BOT_DRY_RUN=1`** 고정 → PC 에서 봇을 켜도 주문·Supabase 쓰기 없음(docs/05 §4 ②). 락도 안 잡음.
- 새 기능 검증 흐름: ① 단위테스트(모의객체) → ② (선택) PC 드라이런으로 장중 `[DRY]` 판정 로그 관찰 → ③ 커밋·push → **장 마감 후** 클라우드 재배포(`git pull` + 서비스 재시작, 전략상태는 `strategy_state` 에서 복원) → ④ 다음 장 앱으로 확인.
- 주문 경로까지 PC 에서 실증해야 하면: 클라우드 서비스 정지(락 해제) → PC `BOT_DRY_RUN=0` 으로 실행(락 획득) → 끝나면 원복.

## 3. 컨테이너화 (`infra/Dockerfile`) — **보류(D-015: 1차 이관은 venv+systemd)**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine/ .
ENV TZ=Asia/Seoul
CMD ["python", "-m", "src.main"]
```
- pykrx/finance-datareader 네트워크 의존 확인. 타임존 KST 고정.
- 시크릿은 이미지에 넣지 말고 **런타임 환경변수/시크릿**으로 주입.
- `infra/docker-compose.yml` 로 로컬 재현.

## 4. 클라우드 이관 절차 (D-015 · venv+systemd, `infra/server/`)

1. VM 준비(사용자): **서울 리전** Ubuntu 22.04/24.04, 1GB+ RAM, 공인 IP. 후보: Oracle Cloud 무료 티어(서울) / AWS Lightsail 서울 / Vultr 서울. KIND 크롤링·키움 API 가 해외 IP 를 막을 수 있어 국내 리전 필수. SSH 개인키는 작업 PC `~/.ssh/` 에만 보관.
2. 최초 설치(Claude, SSH): `sudo bash infra/server/setup.sh <repo-url>` → python3.12·git, `bot` 시스템 사용자, `/opt/breakZoneAutoApp` clone, venv+deps, systemd 유닛(`breakzone-bot.service`: Restart=always, SIGINT 안전종료, KST) 등록.
3. 시크릿(`engine/.env`)을 서버에 배치(600, bot 소유). 유닛 파일·이미지·깃에 넣지 않는다. `BOT_HOLDER_ID=cloud-seoul`, `BOT_DRY_RUN=0`.
4. 스모크: `tools/check_kiwoom_token.py`(키움 토큰·잔고) + `tools/check_supabase.py`(중계) 를 서버에서 실행해 서버 IP 에서 외부 접속이 되는지 확인.
5. **전환:** 집 PC 봇 종료 → `systemctl start breakzone-bot` → 로그에 "락 획득(cloud-seoul)" + 앱 이벤트 "봇 LIVE" 확인. PC `.env` 는 `BOT_DRY_RUN=1` 로 바꿔 둔다(docs/05 §4).
6. 검증: 앱·Supabase **무변경**으로 연동(하트비트·시작/정지·설정 반영·후보 표시 왕복).
7. 재배포: `sudo bash infra/server/deploy.sh` (pull → deps 변경 시 설치 → pytest -x → restart → 로그). **장 마감 후** 원칙. 로그: `journalctl -u breakzone-bot -f`.

### 이관 시 바뀌는 것 / 안 바뀌는 것
- **안 바뀜:** 앱, Supabase 스키마/URL, 통신 규약, 브로커 어댑터, 전략 코드.
- **바뀜:** 봇이 도는 호스트, 시크릿 저장 위치, 프로세스 관리 방식.

## 5. 모니터링/운영

- **하트비트:** `bot_state.heartbeat_at` — 앱과 (선택)외부 uptime 모니터가 감시.
- **로그:** 파일 + (클라우드)로그수집. 오류는 `events`(critical)로 승격 → 인앱 알림(푸시 채택 시 푸시도).
- **백업:** Supabase 자동 백업 + 주기 export(주문/이벤트 이력).
- **업데이트:** 무중단 필요 없으면 장외 시간에 재배포. 스키마 변경은 마이그레이션 순서 준수.

## 6. 비용(초기)

- Supabase 무료 티어(초기 충분). 트래픽 증가 시 유료.
- FCM 무료 (선택 · 푸시 채택 시).
- 집 PC = 전기요금만. 클라우드 VM = 소형 인스턴스 월 수천~수만원(국내 VPS 저렴).

## 7. 롤백

- 문제 발생 시: 앱/서버에서 **kill(전량청산+정지)** → 원인분석 → 이전 안정 버전으로 재배포. 스키마 파괴적 변경은 역마이그레이션 준비.
