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

## 3. 컨테이너화 (`infra/Dockerfile`)

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

## 4. 클라우드 이관 절차

1. VM 준비: **국내 VPS(카페24/가비아/네이버클라우드)** 또는 **AWS/GCP 서울 리전**. 국내 증권사 API 지연 최소화엔 국내가 유리.
2. Docker 설치 → 이미지 빌드/실행(또는 레지스트리 경유).
3. 시크릿 주입(환경변수/시크릿매니저). 실전 키는 여기서만.
4. 프로세스 관리: `--restart=always`(Docker) 또는 systemd. 크래시/재부팅 자동복구.
5. **이중 실행 방지:** 집 봇 종료 확인 후 클라우드 봇 시작(docs/05 §4 락).
6. 검증: 앱·Supabase **무변경**으로 그대로 연동되는지 확인(하트비트·명령 왕복).

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
