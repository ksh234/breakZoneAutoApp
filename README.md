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
**먼저 [`ROADMAP.md`](ROADMAP.md) 를 읽으세요.** 전체 로드맵 + 상세 설계가 들어 있고, 새 세션은 이 문서만으로 Phase 0부터 시작할 수 있습니다.

설계 문서: [`docs/`](docs/)
- [00 아키텍처](docs/00-architecture.md) · [01 키움 브로커](docs/01-broker-kiwoom.md) · [02 Supabase 스키마](docs/02-supabase-schema.md) · [03 전략 명세](docs/03-strategy-spec.md) · [04 Flutter 앱](docs/04-flutter-app.md) · [05 보안·리스크](docs/05-security-risk.md) · [06 배포](docs/06-deployment.md)

## ⚠️ 주의
실제 자금이 오가는 자동매매입니다. **모의투자로 충분히 검증하기 전 실계좌 금지**(ROADMAP Phase 6·7). 리스크 가드·kill-switch·시크릿 관리는 선택이 아니라 전제입니다.

## 현재 상태
설계 단계 완료. 구현은 새 PC의 새 세션에서 ROADMAP Phase 0부터 진행 예정. (`breakZone`, `breakZoneAutoApp` 폴더를 새 PC로 이동)
