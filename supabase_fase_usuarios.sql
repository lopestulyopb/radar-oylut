alter table public.profiles enable row level security;
alter table public.daily_usage enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles for select to authenticated using ((select auth.uid()) = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

drop policy if exists "daily_usage_select_own" on public.daily_usage;
create policy "daily_usage_select_own" on public.daily_usage for select to authenticated using ((select auth.uid()) = user_id);

create unique index if not exists daily_usage_user_date_unique on public.daily_usage(user_id,usage_date);
create index if not exists daily_usage_user_id_index on public.daily_usage(user_id);

create or replace function public.consume_daily_query(p_limit integer default 18)
returns table(allowed boolean,used integer,remaining integer)
language plpgsql
security definer
set search_path=public
as $$
declare
  v_user_id uuid:=auth.uid();
  v_used integer;
begin
  if v_user_id is null then raise exception 'Not authenticated'; end if;
  insert into public.daily_usage(user_id,usage_date,queries_used)
  values(v_user_id,current_date,0)
  on conflict(user_id,usage_date) do nothing;
  update public.daily_usage
  set queries_used=queries_used+1
  where user_id=v_user_id and usage_date=current_date and queries_used<p_limit
  returning queries_used into v_used;
  if v_used is null then
    select queries_used into v_used from public.daily_usage where user_id=v_user_id and usage_date=current_date;
    return query select false,coalesce(v_used,p_limit),0;
    return;
  end if;
  return query select true,v_used,greatest(p_limit-v_used,0);
end;
$$;
revoke all on function public.consume_daily_query(integer) from public;
grant execute on function public.consume_daily_query(integer) to authenticated;
