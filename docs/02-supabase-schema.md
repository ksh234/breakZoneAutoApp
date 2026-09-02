# 02 · Supabase 스키마 · Realtime · (선택)푸시

> 봇·앱의 유일한 접점. Postgres 테이블(SSOT) + RLS + Realtime. 단일 사용자 전제.
> **Supabase 단독 백엔드.** `devices` 테이블과 Edge Function(FCM)은 **백그라운드 푸시를 채택할 때만**(Phase 5-B) 추가하는 선택 요소 — 아래에 "선택" 표기. 1단계(Phase 0~4)는 이들 없이 진행한다.

---

## 1. 접근 주체와 권한

| 주체 | 키 | 권한 |
|---|---|---|
| 봇(engine) | **secret key**(`sb_secret_…`, legacy `service_role` 대체) | 전체 읽기/쓰기(RLS 우회). 서버에서만 보관 |
| 앱(Flutter) | **publishable key**(`sb_publishable_…`, legacy `anon` 대체) + 로그인 세션 | RLS 하에서 본인 데이터만 |

> **키 체계(2026):** Supabase 신규 키 = publishable(공개용)/secret(서버용). legacy anon/service_role 는 2026말 폐기 예정이나 병행 동작. 신규 프로젝트는 신규 키 사용. env 명: 봇 `SUPABASE_SECRET_KEY`, 앱 publishable.

단일 사용자지만 `owner uuid = auth.uid()` 패턴으로 RLS를 걸어 앱 키 노출에 대비. 봇은 service_role이라 owner를 직접 세팅.

---

## 2. 테이블 DDL (`supabase/migrations/0001_init.sql`)

```sql
-- 공통: updated_at 자동 갱신 트리거
create or replace function set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end; $$ language plpgsql;

-- 2.1 설정(싱글턴): 봇 파라미터. 앱이 수정, 봇이 구독.
create table settings (
  id            int primary key default 1 check (id = 1),
  owner         uuid not null,
  mode          text not null default 'demo' check (mode in ('demo','real')),
  enabled       boolean not null default false,        -- 자동매매 on/off
  -- ⚠️ 아래 개별 컬럼은 초기 설계의 placeholder(레거시). 현재 전략 파라미터는
  --    전부 `extra` jsonb 에 저장·로드한다(StrategyParams, docs/03 §6). 이 컬럼들은
  --    미사용(무해). 실제 사용 컬럼: owner, mode, enabled, extra.
  entry_drop_min      numeric,      -- (레거시·미사용) → extra.entry_drop_pct 로 대체
  entry_drop_max      numeric,      -- (레거시·미사용)
  per_trade_krw       bigint default 1000000,          -- (레거시·미사용) → extra.per_stock_krw
  max_positions       int    default 5,                -- (레거시·미사용) → extra.max_positions
  take_profit_pct     numeric default 10,              -- (레거시·미사용) → extra.take_profit_pct
  stop_loss_pct       numeric default -5,              -- (레거시·미사용, 손절 없음)
  daily_max_loss_krw  bigint default 500000,           -- (레거시·미사용) → extra.max_unrealized_loss_krw
  extra               jsonb  default '{}'::jsonb,       -- ★ 전략 파라미터 전체(StrategyParams)
  updated_at    timestamptz not null default now()
);
create trigger t_settings before update on settings
  for each row execute function set_updated_at();

-- 2.2 봇 상태(하트비트): 봇이 쓰고 앱이 구독.
create table bot_state (
  id            int primary key default 1 check (id = 1),
  owner         uuid not null,
  status        text not null default 'stopped'
                check (status in ('stopped','running','paused','stopping','error')),
  market_open   boolean default false,
  equity        bigint,           -- 총평가금
  cash          bigint,           -- 주문가능현금
  day_pnl       bigint,           -- 당일 손익
  positions_cnt int default 0,
  message       text,             -- 최근 상태/오류 메시지
  heartbeat_at  timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create trigger t_bot_state before update on bot_state
  for each row execute function set_updated_at();

-- 2.3 후보(경고주 분석 스냅샷): 봇이 upsert, 앱이 구독.
create table candidates (
  code            text not null,
  owner           uuid not null,
  name            text not null,
  designated_date date,
  release_date    date,
  t5_close        bigint,
  t15_close       bigint,
  recent_15_high  bigint,
  release_amount  bigint,          -- 해제금액 = min(p1,p2,p3)
  current_price   bigint,
  drop_ratio      numeric,         -- (해제금액-현재가)/해제금액*100
  status          text,            -- ok | partial | pending | error
  signal          text default 'none'
                  check (signal in ('none','watch','enter','hold','exit')),
  updated_at      timestamptz not null default now(),
  primary key (owner, code)
);

-- 2.4 포지션(보유): 봇이 upsert/삭제, 앱이 구독.
create table positions (
  code          text not null,
  owner         uuid not null,
  name          text not null,
  qty           int not null,
  avg_price     bigint not null,
  current_price bigint,
  pnl           bigint,
  pnl_pct       numeric,
  opened_at     timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  primary key (owner, code)
);

-- 2.5 주문 이력: 봇이 insert/update, 앱이 구독(읽기).
create table orders (
  id              uuid primary key default gen_random_uuid(),
  owner           uuid not null,
  code            text not null,
  name            text,
  side            text not null check (side in ('buy','sell')),
  qty             int  not null,
  order_type      text not null check (order_type in ('market','limit')),
  price           bigint,
  status          text not null default 'pending',
  broker_order_id text,
  filled_qty      int default 0,
  filled_price    bigint,
  reason          text,            -- 진입/익절/손절/kill/manual
  created_at      timestamptz not null default now(),
  filled_at       timestamptz
);
create index on orders (owner, created_at desc);

-- 2.6 이벤트(알림 소스): 봇이 insert. 앱이 Realtime 구독(인앱 알림). severity high → (푸시 채택 시)푸시.
create table events (
  id         uuid primary key default gen_random_uuid(),
  owner      uuid not null,
  type       text not null,     -- order_filled|entry|exit|risk_block|error|kill|reconnect ...
  severity   text not null default 'info' check (severity in ('info','warn','high','critical')),
  title      text not null,
  message    text,
  payload    jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index on events (owner, created_at desc);

-- 2.7 명령(앱→봇): 앱이 insert, 봇이 구독·처리 후 status 갱신.
create table commands (
  id          uuid primary key default gen_random_uuid(),
  owner       uuid not null,
  type        text not null
              check (type in ('start','stop','pause','resume','kill',
                              'set_param','close_position','approve_order','reject_order')),
  payload     jsonb default '{}'::jsonb,   -- 예: {"code":"005930"}(close_position) / set_param 은 settings 직접 수정
  status      text not null default 'pending'
              check (status in ('pending','acked','done','failed')),
  result      text,
  created_at  timestamptz not null default now(),
  processed_at timestamptz
);
create index on commands (owner, status, created_at);

-- 2.8 디바이스(FCM 토큰) — [선택 · Phase 5-B 푸시 채택 시에만 생성]: 앱이 등록, Edge Function이 조회.
create table devices (
  id         uuid primary key default gen_random_uuid(),
  owner      uuid not null,
  fcm_token  text not null unique,
  platform   text,
  updated_at timestamptz not null default now()
);
```

싱글턴(`settings`,`bot_state`)은 최초 1행을 시드한다(`insert ... on conflict do nothing`). owner는 앱 사용자 uuid.

---

## 3. RLS 정책 (`0002_rls.sql`)

```sql
alter table settings   enable row level security;
alter table bot_state  enable row level security;
alter table candidates enable row level security;
alter table positions  enable row level security;
alter table orders     enable row level security;
alter table events     enable row level security;
alter table commands   enable row level security;
alter table devices    enable row level security;

-- 앱(authenticated): 본인 owner 행만. 대부분 읽기전용, 쓰기는 settings/commands/devices 만.
create policy sel_own on candidates for select using (auth.uid() = owner);
-- (positions/orders/events/bot_state 도 동일한 select 정책)
create policy rw_settings on settings for all
  using (auth.uid()=owner) with check (auth.uid()=owner);
create policy ins_commands on commands for insert with check (auth.uid()=owner);
create policy sel_commands on commands for select using (auth.uid()=owner);
create policy rw_devices on devices for all
  using (auth.uid()=owner) with check (auth.uid()=owner);
```
> 봇은 `service_role` 이라 RLS를 우회한다. **service_role 키는 서버에서만** 사용(앱에 넣지 말 것).

---

## 4. Realtime

구독 대상 테이블을 publication에 추가:
```sql
alter publication supabase_realtime add table
  bot_state, candidates, positions, orders, events, commands;
```
- 앱: `bot_state, candidates, positions, orders, events` 구독 → UI 실시간 갱신.
- 봇: `commands` INSERT 구독 → 명령 실행. (`settings` 는 변경 빈도 낮아 구독 or 폴링 택1)

---

## 5. 명령 처리 프로토콜 (앱 ↔ 봇)

1. 앱: `commands` 에 `{type, payload, status:'pending'}` INSERT.
2. 봇: realtime 수신 → `status:'acked'` 로 즉시 갱신(수신확인).
3. 봇: 실행 → 성공 `status:'done'`(+result), 실패 `status:'failed'`(+result 사유).
4. 앱: 해당 행 status 변화를 realtime 으로 보고 UI 피드백.

`set_param` 은 봇이 `settings` 를 직접 읽어 반영(또는 payload로 즉시 적용). `kill`·`close_position` 은 즉시 최우선 처리.

---

## 6. Edge Function — FCM 푸시 (`supabase/functions/push-notify`) — [선택 · Phase 5-B]

> 백그라운드 푸시를 채택할 때만 구현. 미채택 시 이 절 전체 생략(앱이 열려 있을 때의 알림은 §4 Realtime + `events` 구독으로 처리).

- 트리거: `events` INSERT 중 `severity in ('high','critical')`.
  - 구현 택1: (a) DB 웹훅/트리거 → Edge Function 호출, (b) 봇이 이벤트 발행 후 직접 Function 호출.
- 동작: `devices` 에서 owner의 fcm_token 조회 → FCM HTTP v1 로 발송(제목=event.title, 본문=message, data=딥링크용 type/id).
- 시크릿: Firebase 서비스계정 키를 Function secret 으로.

```ts
// pseudo
serve(async (req) => {
  const { record } = await req.json();               // events row
  if (!['high','critical'].includes(record.severity)) return ok();
  const tokens = await getDeviceTokens(record.owner);
  await sendFcm(tokens, { title: record.title, body: record.message,
                          data: { type: record.type, id: record.id }});
  return ok();
});
```

---

## 7. 봇 클라이언트 (`relay/supabase_client.py`) 계약

```python
class Relay:
    async def connect(self): ...
    async def push_bot_state(self, **fields): ...        # upsert id=1
    async def upsert_candidates(self, rows: list[dict]): ...
    async def upsert_positions(self, rows: list[dict]): ...
    async def remove_position(self, code: str): ...
    async def insert_order(self, order: dict) -> str: ...
    async def update_order(self, id: str, **fields): ...
    async def insert_event(self, type, severity, title, message="", payload=None): ...
    async def subscribe_commands(self, handler): ...     # realtime INSERT → handler
    async def ack_command(self, id, status, result=""): ...
    async def load_settings(self) -> dict: ...
```
- 파이썬 Supabase 라이브러리(`supabase-py`/`realtime-py`) 사용. Realtime 미지원 상황 대비 **폴백 폴링**(commands를 2초 주기 select) 옵션 유지.
- 오프라인 버퍼: 네트워크 끊김 시 이벤트/상태를 로컬 큐에 쌓고 재연결 시 flush.

---

## 8. 마이그레이션 운영

- `supabase/migrations/000N_*.sql` 로 버전관리. `supabase db push` 로 적용.
- 스키마 변경 시 앱·봇 매핑 동시 갱신. 파괴적 변경은 새 마이그레이션으로.
