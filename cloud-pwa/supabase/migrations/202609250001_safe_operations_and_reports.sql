-- Melhorias operacionais aditivas: relatórios paginados, resumo agregado,
-- contagem de caixa com justificativa e exposição financeira por perfil.
begin;

create or replace function public.get_sales_report_page(
  p_from date default null,
  p_to date default null,
  p_limit integer default 30,
  p_offset integer default 0
)
returns table (
  id uuid,
  business_date date,
  number integer,
  customer_name text,
  status text,
  total numeric,
  created_by uuid,
  opened_at timestamptz,
  closed_at timestamptz,
  total_count bigint
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if not public.is_admin() then
    raise exception 'Somente administrador pode consultar relatorios.' using errcode = '42501';
  end if;
  if p_from is not null and p_to is not null and p_from > p_to then
    raise exception 'Periodo de relatorio invalido.';
  end if;

  return query
  with filtered as (
    select c.*
    from public.commands c
    where c.establishment_id = public.current_establishment_id()
      and (
        (p_from is null and p_to is null)
        or (
          (p_from is null or c.business_date >= p_from)
          and (p_to is null or c.business_date <= p_to)
        )
        or (
          c.closed_at is not null
          and (p_from is null or (c.closed_at at time zone 'America/Sao_Paulo')::date >= p_from)
          and (p_to is null or (c.closed_at at time zone 'America/Sao_Paulo')::date <= p_to)
        )
      )
      and (
        c.status <> 'cancelada'
        or exists (select 1 from public.command_items ci where ci.command_id = c.id)
      )
  )
  select f.id, f.business_date, f.number, f.customer_name, f.status, f.total,
         f.created_by, f.opened_at, f.closed_at, count(*) over() as total_count
  from filtered f
  order by coalesce(f.closed_at, f.opened_at) desc, f.id
  limit least(greatest(coalesce(p_limit, 30), 1), 500)
  offset greatest(coalesce(p_offset, 0), 0);
end;
$$;

create or replace function public.get_sales_report_summary(
  p_from date default null,
  p_to date default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_result jsonb;
begin
  if not public.is_admin() then
    raise exception 'Somente administrador pode consultar relatorios.' using errcode = '42501';
  end if;
  if p_from is not null and p_to is not null and p_from > p_to then
    raise exception 'Periodo de relatorio invalido.';
  end if;

  with filtered as (
    select c.*
    from public.commands c
    where c.establishment_id = public.current_establishment_id()
      and (
        (p_from is null and p_to is null)
        or (
          (p_from is null or c.business_date >= p_from)
          and (p_to is null or c.business_date <= p_to)
        )
        or (
          c.closed_at is not null
          and (p_from is null or (c.closed_at at time zone 'America/Sao_Paulo')::date >= p_from)
          and (p_to is null or (c.closed_at at time zone 'America/Sao_Paulo')::date <= p_to)
        )
      )
      and (
        c.status <> 'cancelada'
        or exists (select 1 from public.command_items ci where ci.command_id = c.id)
      )
  ), payment_totals as (
    select p.method, sum(p.amount) as amount
    from public.payments p
    join filtered f on f.id = p.command_id and f.status = 'paga'
    group by p.method
  )
  select jsonb_build_object(
    'total_commands', count(*),
    'total_sold', coalesce(sum(f.total) filter (where f.status = 'paga'), 0),
    'paid_count', count(*) filter (where f.status = 'paga'),
    'cancelled_count', count(*) filter (where f.status = 'cancelada'),
    'cash_total', coalesce((select amount from payment_totals where method = 'dinheiro'), 0),
    'pix_total', coalesce((select amount from payment_totals where method = 'pix'), 0),
    'debit_total', coalesce((select amount from payment_totals where method = 'debito'), 0),
    'credit_total', coalesce((select amount from payment_totals where method = 'credito'), 0)
  ) into v_result
  from filtered f;

  return v_result;
end;
$$;

revoke all on function public.get_sales_report_page(date, date, integer, integer) from public, anon;
revoke all on function public.get_sales_report_summary(date, date) from public, anon;
grant execute on function public.get_sales_report_page(date, date, integer, integer) to authenticated;
grant execute on function public.get_sales_report_summary(date, date) to authenticated;

create or replace function public.close_cash_session(
  p_cash_session_id uuid,
  p_counted_amount numeric,
  p_close_notes text default '',
  p_force boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_session public.cash_sessions;
  v_summary jsonb;
  v_expected numeric(12,2);
  v_difference numeric(12,2);
  v_open_count integer;
  v_establishment_id uuid := public.current_establishment_id();
  v_reason text := nullif(trim(coalesce(p_close_notes, '')), '');
begin
  if not public.is_admin() then
    raise exception 'Somente administrador pode fechar caixa.' using errcode = '42501';
  end if;
  if p_counted_amount is null or p_counted_amount < 0 then
    raise exception 'Informe o valor contado no caixa.';
  end if;

  select * into v_session from public.cash_sessions
  where id = p_cash_session_id and status = 'aberto' and establishment_id = v_establishment_id
  for update;
  if not found then raise exception 'Este caixa ja esta fechado ou nao existe.'; end if;

  select count(*) into v_open_count from public.commands
  where establishment_id = v_establishment_id and status in ('aberto', 'aguardando_pagamento');
  if v_open_count > 0 and not p_force then
    raise exception 'Existem comandas em aberto. Finalize ou cancele antes de fechar.';
  end if;

  v_summary := public.get_cash_summary(p_cash_session_id);
  v_expected := (v_summary->>'dinheiro_esperado')::numeric;
  v_difference := round(p_counted_amount - v_expected, 2);
  if (v_difference <> 0 or (p_force and v_open_count > 0)) and coalesce(length(v_reason), 0) < 5 then
    raise exception 'Informe uma justificativa com pelo menos 5 caracteres.';
  end if;

  update public.cash_sessions
  set status = 'fechado', closed_by = auth.uid(), closed_at = now(),
      counted_amount = p_counted_amount, expected_cash = v_expected,
      difference = v_difference, close_notes = v_reason
  where id = p_cash_session_id
  returning * into v_session;

  perform public.add_audit_log('closed', 'cash_sessions', p_cash_session_id, null, to_jsonb(v_session));
  return public.get_cash_summary(p_cash_session_id) || jsonb_build_object('closed_session', to_jsonb(v_session));
end;
$$;

revoke all on function public.close_cash_session(uuid, numeric, text, boolean) from public, anon;
grant execute on function public.close_cash_session(uuid, numeric, text, boolean) to authenticated;

drop policy if exists "cash_sessions tenant read" on public.cash_sessions;
create policy "cash_sessions tenant money read" on public.cash_sessions for select to authenticated
using (
  establishment_id = (select public.current_establishment_id())
  and (select public.can_manage_money())
);

create or replace function public.get_dashboard_summary()
returns jsonb
language sql
security definer
set search_path = ''
as $$
  with access as (
    select public.dashboard_establishment_id() id, public.can_manage_money() money
  ), today_paid as (
    select c.* from public.commands c, access a
    where c.establishment_id = a.id
      and c.status = 'paga'
      and (c.closed_at at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date
  ), pay as (
    select p.method, sum(p.amount) total
    from public.payments p join today_paid c on c.id = p.command_id
    group by p.method
  )
  select jsonb_build_object(
    'business_date', (now() at time zone 'America/Sao_Paulo')::date,
    'cash_open', case when a.money then exists(
      select 1 from public.cash_sessions cs where cs.establishment_id = a.id and cs.status = 'aberto'
    ) else null end,
    'session', case when a.money then (
      select to_jsonb(cs) from public.cash_sessions cs
      where cs.establishment_id = a.id and cs.status = 'aberto' order by opened_at desc limit 1
    ) else null end,
    'total_vendido_hoje', case when a.money then coalesce((select sum(total) from today_paid), 0) else null end,
    'qtd_abertas', (select count(*) from public.commands c where c.establishment_id = a.id and c.status in ('aberto','aguardando_pagamento')),
    'qtd_finalizadas_hoje', (select count(*) from today_paid),
    'qtd_pendentes_hoje', (
      select count(*) from public.commands c
      where c.establishment_id = a.id and c.status = 'fiado'
        and (c.opened_at at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date
    ),
    'fila_pendente', (select count(*) from public.service_queue q where q.establishment_id = a.id and q.status = 'pendente'),
    'total_dinheiro', case when a.money then coalesce((select total from pay where method = 'dinheiro'), 0) else null end,
    'total_pix', case when a.money then coalesce((select total from pay where method = 'pix'), 0) else null end,
    'total_cartao', case when a.money then coalesce((select sum(total) from pay where method in ('debito','credito')), 0) else null end
  )
  from access a
$$;

revoke all on function public.get_dashboard_summary() from public, anon;
grant execute on function public.get_dashboard_summary() to authenticated;

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (
       select 1 from pg_publication_tables
       where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'establishments'
     )
  then
    alter publication supabase_realtime add table public.establishments;
  end if;
end $$;

notify pgrst, 'reload schema';
commit;
