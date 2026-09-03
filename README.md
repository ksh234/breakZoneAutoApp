# breakZoneAutoApp

KRX 투자경고종목(경고주)을 분석해 **자동매매**하는 시스템. 기존 [`breakZone`](../breakZone) 분석 대시보드의 로직을 재사용한다.

```
[전략엔진(Python 봇) — 집 PC → 클라우드] ──▶ [키움 REST API] (모의/실전 주문·체결)
          │ outbound-only (상태 push / 명령 구독)
          ▼
[Supabase — 중계·DB·Realtime] ◀── [Flutter 앱 — 모니터링 & 원격제어]
```

## 핵심 결정
- 증권사: **키움 REST API** (모의투자부터). 미래에셋은 개인 자동매매 API 미제공.
- 앱: **Flutter** · 중계: **Supabase** · 봇: **Python 3.11+**.
- 봇은 outbound 연결만 → NAT/유동IP 무관, 클라우드 이관 용이.

## 시작하기
- **사용법·매수/매도 조건: [`사용법.md`](사용법.md)** ← 실행 방법·앱 화면·전략 조건·설정 전부
- 진행 상황: [`PROGRESS.md`](PROGRESS.md) · 결정 근거: [`DECISIONS.md`](DECISIONS.md)
- 전체 로드맵 + 상세 설계: [`ROADMAP.md`](ROADMAP.md) (새 세션은 이 문서로 Phase 0부터 시작 가능)

설계 문서: [`docs/`](docs/)
- [00 아키텍처](docs/00-architecture.md) · [01 키움 브로커](docs/01-broker-kiwoom.md) · [02 Supabase 스키마](docs/02-supabase-schema.md) · [03 전략 명세](docs/03-strategy-spec.md) · [04 Flutter 앱](docs/04-flutter-app.md) · [05 보안·리스크](docs/05-security-risk.md) · [06 배포](docs/06-deployment.md)

## ⚠️ 주의
실제 자금이 오가는 자동매매입니다. **모의투자로 충분히 검증하기 전 실계좌 금지**(ROADMAP Phase 6·7). 리스크 가드·kill-switch·시크릿 관리는 선택이 아니라 전제입니다.

## 현재 상태 (2026-09-03)
Phase 0~5 구현 완료(봇 + Flutter 앱, 키움 모의 왕복주문·앱 제어 라이브 실증). 클라우드 이관(Phase 8) 진행 중 — 봇 준비(이중 실행 락·상태 영속화·드라이런)와 GitHub 원격까지 완료, VM 생성 대기. 상세는 [`PROGRESS.md`](PROGRESS.md).

- 실행: 바탕화면 `breakZone 봇 시작.bat`(= `engine/run_bot.bat`) → 앱에서 시작/정지.
- 원격: `github.com/ksh234/breakZoneAutoApp`(private). 서버 설치: `infra/server/`.
