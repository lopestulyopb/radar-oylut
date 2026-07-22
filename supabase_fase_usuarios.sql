-- ETAPA 5 — ASSINATURAS
-- Novos perfis começam com status pending e são ativados manualmente no Supabase.

alter table public.profiles
  add column if not exists subscription_status text not null default 'pending',
  add column if not exists subscription_expires_at timestamptz;

alter table public.profiles
  drop constraint if exists profiles_subscription_status_check;

alter table public.profiles
  add constraint profiles_subscription_status_check
  check (subscription_status in ('pending', 'active', 'expired', 'inactive'));

create index if not exists profiles_subscription_status_index
  on public.profiles(subscription_status);

alter table public.profiles enable row level security;
alter table public.daily_usage enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
  for select to authenticated
  using ((select auth.uid()) = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
  for update to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

drop policy if exists "daily_usage_select_own" on public.daily_usage;
create policy "daily_usage_select_own" on public.daily_usage
  for select to authenticated
  using ((select auth.uid()) = user_id);

create unique index if not exists daily_usage_user_date_unique
  on public.daily_usage(user_id, usage_date);
create index if not exists daily_usage_user_id_index
  on public.daily_usage(user_id);

create or replace function public.consume_daily_query(p_limit integer default 18)
returns table(allowed boolean, used integer, remaining integer)
language plpgsql
security definer
set search_path=public
as $$
declare
  v_user_id uuid := auth.uid();
  v_used integer;
  v_subscription_status text;
  v_subscription_expires_at timestamptz;
begin
  if v_user_id is null then
    raise exception 'Not authenticated';
  end if;

  select subscription_status, subscription_expires_at
    into v_subscription_status, v_subscription_expires_at
  from public.profiles
  where id = v_user_id;

  if v_subscription_status is distinct from 'active'
     or (v_subscription_expires_at is not null and v_subscription_expires_at < now()) then
    return query select false, 0, 0;
    return;
  end if;

  insert into public.daily_usage(user_id, usage_date, queries_used)
  values(v_user_id, current_date, 0)
  on conflict(user_id, usage_date) do nothing;

  update public.daily_usage
  set queries_used = queries_used + 1
  where user_id = v_user_id
    and usage_date = current_date
    and queries_used < p_limit
  returning queries_used into v_used;

  if v_used is null then
    select queries_used into v_used
    from public.daily_usage
    where user_id = v_user_id and usage_date = current_date;

    return query select false, coalesce(v_used, p_limit), 0;
    return;
  end if;

  return query select true, v_used, greatest(p_limit - v_used, 0);
end;
$$;

revoke all on function public.consume_daily_query(integer) from public;
grant execute on function public.consume_daily_query(integer) to authenticated;

-- ATIVAÇÃO MANUAL (substitua pelo e-mail do usuário)
-- update public.profiles
-- set subscription_status = 'active',
--     subscription_expires_at = now() + interval '30 days'
-- where email = 'usuario@exemplo.com';

-- DESATIVAÇÃO NEUTRA
-- update public.profiles
-- set subscription_status = 'inactive'
-- where email = 'usuario@exemplo.com';
