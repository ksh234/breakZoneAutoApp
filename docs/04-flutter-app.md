# 04 · Flutter 앱 — 모니터링 & 원격제어

> "봇을 켜는 게 아니라 지켜보는" 앱. 매매 로직 없음. **Supabase 단독**: Realtime 읽기 + 인앱 알림(`events`) + `commands`/`settings` 쓰기.
> 백그라운드 푸시(FCM)는 **선택(Phase 5-B)** — 아래 §6은 채택할 때만. 기본 앱은 FCM 없이 완성된다(앱이 열려 있을 때 Realtime으로 알림).

---

## 1. 스택 & 패키지

- Flutter(안정 채널), Dart 3.
- `supabase_flutter` — 인증 + Realtime + Postgrest.
- `flutter_riverpod` — 상태관리.
- `fl_chart` — 손익/자산 차트.
- `intl` — KST 포맷.
- (선택) `go_router` — 딥링크 라우팅.
- **(선택 · Phase 5-B 푸시 채택 시)** `firebase_core`, `firebase_messaging` — FCM 백그라운드 푸시.

## 2. 앱 구조

```
app/lib/
├── main.dart                 # Supabase.initialize + ProviderScope (+ 선택: Firebase.init)
├── core/
│   ├── supabase.dart         # 클라이언트, 환경변수(anon key)
│   ├── theme.dart
│   └── router.dart
├── auth/
│   ├── auth_provider.dart    # 세션 스트림
│   └── login_screen.dart
├── data/
│   ├── models.dart           # BotState, Candidate, Position, OrderRow, EventRow, Settings
│   └── repos.dart            # 테이블별 realtime 스트림 + 쓰기 함수
├── features/
│   ├── dashboard/dashboard_screen.dart
│   ├── positions/positions_view.dart
│   ├── candidates/candidates_view.dart
│   ├── orders/orders_view.dart
│   ├── control/control_screen.dart      # start/stop/kill
│   ├── settings/settings_screen.dart    # 파라미터 편집
│   └── events/events_view.dart          # 알림 이력
└── push/fcm.dart             # [선택 · Phase 5-B] 토큰 등록(devices), 수신 핸들러, 딥링크
```

## 3. 상태관리 (Riverpod + Realtime)

각 테이블을 스트림 Provider로:
```dart
final botStateProvider = StreamProvider<BotState>((ref) =>
  supabase.from('bot_state').stream(primaryKey: ['id'])
    .map((rows) => BotState.fromMap(rows.first)));

final positionsProvider = StreamProvider<List<Position>>((ref) =>
  supabase.from('positions').stream(primaryKey: ['owner','code'])
    .map((rows) => rows.map(Position.fromMap).toList()));
// candidates / orders / events 동일 패턴
final settingsProvider = StreamProvider<Settings>(...);
```
UI는 `ref.watch(...)` 로 자동 갱신. 연결 상태/에러도 표시.

## 4. 화면 명세

### 4.1 대시보드 (홈)
- **봇 상태 카드:** status 배지(running=초록/paused=노랑/stopped=회색/error=빨강), **하트비트 경과**(now−heartbeat_at; 임계 초과 시 "연결 끊김" 경고), 평가금/현금/당일손익.
- **요약:** 보유수, 오늘 주문수, 미체결수.
- 탭 이동: 포지션 / 후보 / 주문 / 이벤트.

### 4.2 포지션 뷰
- 리스트: 종목명·수량·평단·현재가·평가손익(원/%). 손익 색상. 각 행에서 **[청산]**(→ `close_position` 명령, 2단계 확인).
- 상단: 총 평가손익, 미니 차트(fl_chart).

### 4.3 후보 뷰
- 후보 리스트: 종목명·해제금액·현재가·**하락비율**·상태·signal. 하락비율/신호로 정렬·강조(breakZone 강조 규칙 계승).
- 필터: signal, 상태.

### 4.4 주문 뷰
- 최근 주문(최신순): 시각·종목·매수/매도·수량·가격·상태·사유. 상태 실시간 갱신.

### 4.5 제어 화면
- **Start/Stop 토글** → `commands` insert(start/stop). 처리 status 피드백.
- **일시정지/재개**(pause/resume).
- **🔴 긴급 정지(kill-switch):** 크고 명확한 버튼 + **2단계 확인 다이얼로그**("전량 청산 후 정지합니다") → `kill` 명령. 처리 결과 표시.
- (반자동 확장) 승인 대기 주문 리스트: approve/reject.

### 4.6 설정 화면
- `settings` 파라미터 편집 폼(진입구간·1회금액·최대보유·익절/손절·일손실상한·mode). 저장 → `settings` update(또는 `set_param` 명령).
- **mode=real 토글은 강한 경고 + 재확인**(실제 자금). docs/05 체크리스트 링크.

### 4.7 이벤트/알림 이력
- `events` 최신순. severity 색상. 탭 시 관련 화면 딥링크.

## 5. 제어 흐름 (앱→봇)

```
버튼 → commands.insert({type, payload, status:'pending'})
     → (봇 realtime 처리) → status:'acked'→'done'/'failed'
     → 앱은 해당 command row 스트림으로 결과 토스트/스낵바
```
낙관적 UI 지양(실제 자금) — **봇의 ack/done 을 확인**해 표시. 타임아웃(예: 10초) 시 "봇 무응답" 경고.

## 6. 푸시 (FCM) — [선택 · Phase 5-B]

> **채택할 때만 구현.** 미채택 시 알림은 §4.7 이벤트 뷰(Realtime 인앱)로 처리하고 이 절은 생략한다. 백그라운드/종료 상태 알림이 필요할 때만 아래를 추가.

1. 앱 시작 시 권한 요청 → 토큰 획득 → `devices` upsert(owner, fcm_token, platform).
2. 포그라운드: `onMessage` → 인앱 배너. 백그라운드/종료: 시스템 알림.
3. 탭 → `data.type/id` 로 딥링크(예: order_filled → 주문 뷰, error → 이벤트 뷰).
4. 발송은 Supabase Edge Function 이 `events`(severity high/critical) 기준으로(docs/02 §6).

## 7. 인증

- Supabase 이메일/비번 단일 계정. 로그인 세션 유지(secure storage). 로그아웃 시 토큰 정리.
- 앱은 `anon key` 만 포함(공개 가능) — 실제 보호는 RLS. **service_role 키 절대 포함 금지.**

## 8. 완료 기준(Phase 5)과 매핑

- 실시간 반영 1~2초 → §3 스트림.
- Start/Stop/kill 실동작 → §5 제어흐름 + 봇 ack.
- 설정 반영 → §4.6.
- 인앱 알림(이벤트) → §4.7. (백그라운드 푸시·딥링크는 5-B 채택 시 §6.)

## 9. 확장(후순위)

- 위젯/홈스크린 요약, 생체인증 잠금, 다국어, iOS 빌드, 차트 고도화(자산곡선/일별손익).
