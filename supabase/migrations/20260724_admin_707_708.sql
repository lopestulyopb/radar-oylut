create table if not exists public.source_monitor (
  source_key text primary key,
  source_name text not null,
  source_url text not null,
  enabled boolean not null default true,
  status text not null default 'nao_testado' check (status in ('online','instavel','offline','nao_testado')),
  last_checked_at timestamptz,
  last_collection_at timestamptz,
  average_response_ms integer,
  collected_news_count integer not null default 0,
  updated_at timestamptz not null default now()
);

create table if not exists public.app_settings (
  setting_key text primary key,
  setting_value jsonb not null,
  description text,
  updated_at timestamptz not null default now()
);

insert into public.source_monitor (source_key, source_name, source_url)
values
  ('clickpb','ClickPB','https://www.clickpb.com.br/ultimas-noticias'),
  ('jornal_paraiba','Jornal da Paraíba','https://jornaldaparaiba.com.br/feed'),
  ('maispb','MaisPB','https://www.maispb.com.br/ultimas-noticias'),
  ('polemica_paraiba','Polêmica Paraíba','https://www.polemicaparaiba.com.br/feed/')
on conflict (source_key) do nothing;

insert into public.app_settings (setting_key, setting_value, description)
values
  ('daily_limit','18'::jsonb,'Limite diário padrão de pesquisas por usuário'),
  ('cache_ttl_seconds','180'::jsonb,'Tempo do cache de notícias em segundos'),
  ('default_order','"editor_chefe"'::jsonb,'Ordenação padrão do Radar'),
  ('app_version','"7.0.8"'::jsonb,'Versão exibida no painel'),
  ('enabled_sources','["clickpb","jornal_paraiba","maispb","polemica_paraiba"]'::jsonb,'Fontes habilitadas na coleta')
on conflict (setting_key) do nothing;

alter table public.source_monitor enable row level security;
alter table public.app_settings enable row level security;
revoke all on public.source_monitor from anon, authenticated;
revoke all on public.app_settings from anon, authenticated;
grant all on public.source_monitor to service_role;
grant all on public.app_settings to service_role;

create or replace function public.set_updated_at_generic()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists source_monitor_updated_at on public.source_monitor;
create trigger source_monitor_updated_at before update on public.source_monitor
for each row execute function public.set_updated_at_generic();

drop trigger if exists app_settings_updated_at on public.app_settings;
create trigger app_settings_updated_at before update on public.app_settings
for each row execute function public.set_updated_at_generic();
