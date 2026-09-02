-- 0002_rls.sql — Row Level Security (docs/02 §3)
-- 앱(authenticated)은 본인 owner 행만. 봇은 service_role 로 RLS 우회.
-- 앱 쓰기 허용: settings(수정), commands(insert). 나머지는 읽기전용.

alter table settings   enable row level security;
alter table bot_state  enable row level security;
alter table candidates enable row level security;
alter table positions  enable row level security;
alter table orders     enable row level security;
alter table events     enable row level security;
alter table commands   enable row level security;

-- 읽기(본인 owner) — 앱 대시보드용
drop policy if exists sel_own on candidates;
create policy sel_own on candidates for select using (auth.uid() = owner);
drop policy if exists sel_own on positions;
create policy sel_own on positions  for select using (auth.uid() = owner);
drop policy if exists sel_own on orders;
create policy sel_own on orders     for select using (auth.uid() = owner);
drop policy if exists sel_own on events;
create policy sel_own on events     for select using (auth.uid() = owner);
drop policy if exists sel_own on bot_state;
create policy sel_own on bot_state  for select using (auth.uid() = owner);

-- settings: 앱이 읽기+수정
drop policy if exists rw_settings on settings;
create policy rw_settings on settings for all
  using (auth.uid() = owner) with check (auth.uid() = owner);

-- commands: 앱이 insert + 본인 것 select
drop policy if exists ins_commands on commands;
create policy ins_commands on commands for insert with check (auth.uid() = owner);
drop policy if exists sel_commands on commands;
create policy sel_commands on commands for select using (auth.uid() = owner);
