-- 0006_strategy_state_partial_sell_price.sql — 2차 상승 전량매도(X2b) 기준가 영속화 (docs/03 §2.2, 2026-09-04)
-- 1차(분할) 매도 가격을 저장해 재시작 후에도 post_sell_gain_pct 판정이 이어지게 함.
alter table strategy_state
  add column if not exists partial_sell_price bigint not null default 0;
