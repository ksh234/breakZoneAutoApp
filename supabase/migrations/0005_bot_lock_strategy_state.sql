-- 0005_bot_lock_strategy_state.sql — 이중 실행 방지 락 + 포지션 전략상태 영속화 (docs/05 §4, docs/03 §2.2b)
-- 클라우드 이관(D-015) 선행 작업. 단일 사용자 전제 유지(D-014): bot_lock 은 id=1 단일행.

-- ── 1) bot_lock: 봇 인스턴스 락 ──
-- holder_id = 봇 인스턴스 식별자(호스트명 등). heartbeat_at 이 stale_sec 이상 오래되면 다른 봇이 승계 가능.
create table if not exists bot_lock (
  id            int primary key default 1 check (id = 1),
  owner         uuid not null,
  holder_id     text not null,
  acquired_at   timestamptz not null default now(),
  heartbeat_at  timestamptz not null default now()
);
alter table bot_lock enable row level security;
drop policy if exists sel_own on bot_lock;
create policy sel_own on bot_lock for select using (auth.uid() = owner);

-- 획득/갱신을 한 함수로: 내가 보유 중이면 heartbeat 갱신, 비어있거나 stale 이면 승계. 성공 시 true.
-- (INSERT ... ON CONFLICT DO UPDATE ... WHERE 로 원자적. FOUND = 행이 영향받았는가)
create or replace function acquire_bot_lock(p_owner uuid, p_holder text, p_stale_sec int default 90)
returns boolean
language plpgsql security definer set search_path = public as $$
begin
  insert into bot_lock (id, owner, holder_id, acquired_at, heartbeat_at)
  values (1, p_owner, p_holder, now(), now())
  on conflict (id) do update
    set owner        = excluded.owner,
        holder_id    = excluded.holder_id,
        heartbeat_at = now(),
        acquired_at  = case when bot_lock.holder_id = excluded.holder_id
                            then bot_lock.acquired_at else now() end
    where bot_lock.holder_id = excluded.holder_id
       or bot_lock.heartbeat_at < now() - make_interval(secs => p_stale_sec);
  return found;
end $$;

create or replace function release_bot_lock(p_owner uuid, p_holder text)
returns boolean
language plpgsql security definer set search_path = public as $$
begin
  delete from bot_lock where id = 1 and owner = p_owner and holder_id = p_holder;
  return found;
end $$;

-- 락 함수는 봇(service role)만. 앱 사용자(anon/authenticated)는 실행 금지.
revoke execute on function acquire_bot_lock(uuid, text, int) from public, anon, authenticated;
revoke execute on function release_bot_lock(uuid, text) from public, anon, authenticated;

-- ── 2) strategy_state: 종목별 전략 상태(엔진 메모리 → DB, 재시작/재배포 시 복원) ──
create table if not exists strategy_state (
  owner               uuid not null,
  code                text not null,
  entries_done        int not null default 0,       -- 분할매수 횟수
  invested_krw        bigint not null default 0,    -- 누적 매수금액
  partial_sold        boolean not null default false,
  peak_since_partial  bigint not null default 0,    -- 분할매도 후 고점(트레일링)
  zone_low            bigint,                       -- 매수구간 저점(저가 반등 매수용, 미보유 후보도)
  updated_at          timestamptz not null default now(),
  primary key (owner, code)
);
alter table strategy_state enable row level security;
drop policy if exists sel_own on strategy_state;
create policy sel_own on strategy_state for select using (auth.uid() = owner);

-- Realtime: 앱에서 "어느 봇이 락을 잡았나" 표시용(후속)
do $$
begin
  alter publication supabase_realtime add table bot_lock;
exception when duplicate_object then
  null;
end $$;
