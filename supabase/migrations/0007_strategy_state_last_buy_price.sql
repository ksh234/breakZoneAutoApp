-- 0007_strategy_state_last_buy_price.sql — 추가매수 기준을 평단 → 직전 매수가로 변경(2026-09-22, D-013 보강)
alter table strategy_state
  add column if not exists last_buy_price bigint not null default 0;
