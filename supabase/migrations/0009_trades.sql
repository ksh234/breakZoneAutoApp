-- 0009_trades.sql — 거래 이력(사이클: 첫 매수 → 잔고 0). 앱 "이력" 탭. (2026-09-28)
-- 금액은 전부 키움 체결 실데이터(체결수량·체결가·수수료·세금)의 합계(D-016). 사이클 묶음만 봇이 함.
create table if not exists trades (
  id             uuid primary key default gen_random_uuid(),
  owner          uuid not null,
  code           text not null,
  name           text,
  status         text not null default 'open' check (status in ('open','closed')),
  first_buy_at   timestamptz not null default now(),
  last_sell_at   timestamptz,
  buy_qty        int    not null default 0,
  buy_amount     bigint not null default 0,   -- Σ 체결수량×체결가 (매수)
  sell_qty       int    not null default 0,
  sell_amount    bigint not null default 0,   -- Σ 체결수량×체결가 (매도)
  buy_count      int    not null default 0,   -- 체결된 매수 주문 수(분할 횟수)
  sell_count     int    not null default 0,
  commission     bigint not null default 0,   -- 매수+매도 수수료
  tax            bigint not null default 0,   -- 거래세
  profit         bigint,                      -- sell_amount − buy_amount − commission − tax (청산 후)
  profit_pct     numeric,                     -- profit / buy_amount × 100
  exit_reason    text,                        -- 마지막 매도 사유: limit_up / take_profit_partial / post_sell_gain / trailing_stop / kill / manual / external
  holding_days   int,
  orders         jsonb not null default '[]', -- [{ord_no, side, qty, price, at, reason}]
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create unique index if not exists uq_trades_open on trades (owner, code) where status = 'open';
create index if not exists idx_trades_owner_first on trades (owner, first_buy_at desc);
alter table trades enable row level security;
drop policy if exists sel_own on trades;
create policy sel_own on trades for select using (auth.uid() = owner);
do $$
begin
  alter publication supabase_realtime add table trades;
exception when duplicate_object then
  null;
end $$;
