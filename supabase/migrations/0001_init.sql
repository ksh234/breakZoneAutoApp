-- 0001_init.sql — breakZoneAutoApp 초기 스키마 (docs/02 §2)
-- 봇·앱의 유일한 접점. 단일 사용자 전제(owner = auth.uid()).

-- 공통: updated_at 자동 갱신 트리거
create or replace function set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end; $$ language plpgsql;

-- 2.1 설정(싱글턴): 봇 파라미터. 앱이 수정, 봇이 읽음.
create table if not exists settings (
  id            int primary key default 1 check (id = 1),
  owner         uuid not null,
  mode          text not null default 'demo' check (mode in ('demo','real')),
  enabled       boolean not null default false,
  entry_drop_min      numeric,
  entry_drop_max      numeric,
  per_trade_krw       bigint default 1000000,
  max_positions       int    default 5,
  take_profit_pct     numeric default 10,
  stop_loss_pct       numeric default -5,
  daily_max_loss_krw  bigint default 500000,
  extra               jsonb  default '{}'::jsonb,
  updated_at    timestamptz not null default now()
);
drop trigger if exists t_settings on settings;
create trigger t_settings before update on settings
  for each row execute function set_updated_at();

-- 2.2 봇 상태(하트비트): 봇이 쓰고 앱이 구독.
create table if not exists bot_state (
  id            int primary key default 1 check (id = 1),
  owner         uuid not null,
  status        text not null default 'stopped'
                check (status in ('stopped','running','paused','stopping','error')),
  market_open   boolean default false,
  equity        bigint,
  cash          bigint,
  day_pnl       bigint,
  positions_cnt int default 0,
  message       text,
  heartbeat_at  timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
drop trigger if exists t_bot_state on bot_state;
create trigger t_bot_state before update on bot_state
  for each row execute function set_updated_at();

-- 2.3 후보(경고주 분석 스냅샷): 봇이 upsert, 앱이 구독.
create table if not exists candidates (
  code            text not null,
  owner           uuid not null,
  name            text not null,
  designated_date date,
  release_date    date,
  t5_close        bigint,
  t15_close       bigint,
  recent_15_high  bigint,
  release_amount  bigint,
  current_price   bigint,
  drop_ratio      numeric,
  status          text,
  signal          text default 'none'
                  check (signal in ('none','watch','enter','hold','exit')),
  updated_at      timestamptz not null default now(),
  primary key (owner, code)
);

-- 2.4 포지션(보유): 봇이 upsert/삭제, 앱이 구독.
create table if not exists positions (
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
create table if not exists orders (
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
  reason          text,
  created_at      timestamptz not null default now(),
  filled_at       timestamptz
);
create index if not exists idx_orders_owner_created on orders (owner, created_at desc);

-- 2.6 이벤트(알림 소스): 봇이 insert. 앱이 Realtime 구독.
create table if not exists events (
  id         uuid primary key default gen_random_uuid(),
  owner      uuid not null,
  type       text not null,
  severity   text not null default 'info' check (severity in ('info','warn','high','critical')),
  title      text not null,
  message    text,
  payload    jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_events_owner_created on events (owner, created_at desc);

-- 2.7 명령(앱→봇): 앱이 insert, 봇이 구독·처리 후 status 갱신.
create table if not exists commands (
  id          uuid primary key default gen_random_uuid(),
  owner       uuid not null,
  type        text not null
              check (type in ('start','stop','pause','resume','kill',
                              'set_param','close_position','approve_order','reject_order')),
  payload     jsonb default '{}'::jsonb,
  status      text not null default 'pending'
              check (status in ('pending','acked','done','failed')),
  result      text,
  created_at  timestamptz not null default now(),
  processed_at timestamptz
);
create index if not exists idx_commands_owner_status on commands (owner, status, created_at);
