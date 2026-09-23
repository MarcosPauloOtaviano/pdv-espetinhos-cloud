-- Restrict kitchen users to the kitchen order queue.
-- The kitchen receives only the operational fields needed to prepare orders;
-- administrative and financial tables remain inaccessible at the database layer.
begin;

create or replace function public.enqueue_service_request(
  p_command_id uuid,
  p_request_type text,
  p_payload jsonb default '{}'::jsonb,
  p_idempotency_key text default null
)
returns public.service_queue
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_command public.commands;
  v_request public.service_queue;
  v_existing public.service_queue;
  v_items jsonb := '[]'::jsonb;
  v_key text := nullif(trim(p_idempotency_key), '');
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para enviar pedidos.';
  end if;
  if p_request_type not in ('pedido_digital', 'chamar_garcom', 'solicitar_fechamento') then
    raise exception 'Tipo de solicitacao invalido.';
  end if;

  select * into v_command
  from public.commands
  where id = p_command_id
    and establishment_id = public.current_establishment_id()
    and status in ('aberto', 'aguardando_pagamento')
  for update;
  if not found then raise exception 'Comanda aberta nao encontrada.'; end if;

  if v_key is not null then
    select * into v_existing
    from public.service_queue
    where establishment_id = v_command.establishment_id
      and idempotency_key = v_key;
    if v_existing.id is not null then return v_existing; end if;
  end if;

  insert into public.service_queue (
    establishment_id, command_id, request_type, payload, idempotency_key
  ) values (
    v_command.establishment_id, v_command.id, p_request_type,
    coalesce(p_payload, '{}'::jsonb), v_key
  )
  on conflict (establishment_id, idempotency_key) where idempotency_key is not null
  do nothing
  returning * into v_request;

  if v_request.id is null and v_key is not null then
    select * into v_request
    from public.service_queue
    where establishment_id = v_command.establishment_id
      and idempotency_key = v_key;
    return v_request;
  end if;

  if p_request_type = 'pedido_digital' then
    with linked as (
      update public.command_items
      set source_request_id = v_request.id
      where establishment_id = v_command.establishment_id
        and command_id = v_command.id
        and source_request_id is null
        and kitchen_status = 'pendente'
      returning id, product_id, product_name, quantity, notes
    )
    select coalesce(jsonb_agg(jsonb_build_object(
      'id', id,
      'product_id', product_id,
      'name', product_name,
      'quantity', quantity,
      'notes', notes
    ) order by id), '[]'::jsonb)
    into v_items
    from linked;

    if coalesce(p_payload->>'source', '') = 'pdv' and jsonb_array_length(v_items) = 0 then
      raise exception 'Nenhum item novo para enviar a cozinha.';
    end if;

    update public.service_queue
    set payload = coalesce(p_payload, '{}'::jsonb) || jsonb_build_object('items', v_items)
    where id = v_request.id
    returning * into v_request;
  end if;

  perform public.add_audit_log('queued', 'service_queue', null, null, to_jsonb(v_request));
  return v_request;
end;
$$;

revoke all on function public.enqueue_service_request(uuid, text, jsonb, text) from public, anon;
grant execute on function public.enqueue_service_request(uuid, text, jsonb, text) to authenticated;

create or replace function public.get_kitchen_queue()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_establishment_id uuid;
  v_result jsonb;
begin
  if public.current_role() <> 'cozinha' then
    raise exception 'Esta consulta e exclusiva da cozinha.' using errcode = '42501';
  end if;

  v_establishment_id := public.current_establishment_id();
  if v_establishment_id is null then
    raise exception 'Usuario sem estabelecimento ativo.' using errcode = '42501';
  end if;

  select coalesce(jsonb_agg(jsonb_build_object(
    'id', q.id,
    'command_id', q.command_id,
    'request_type', q.request_type,
    'status', q.status,
    'payload', jsonb_set(coalesce(q.payload, '{}'::jsonb), '{items}', items.value, true),
    'requested_at', q.requested_at,
    'claimed_at', q.claimed_at,
    'claimed_by', q.claimed_by,
    'claimed_by_name', coalesce(claimed.full_name, claimed.username),
    'commands', jsonb_build_object(
      'number', c.number,
      'customer_name', c.customer_name,
      'table_ref', c.table_ref
    )
  ) order by q.requested_at, q.id), '[]'::jsonb)
  into v_result
  from public.service_queue q
  join public.commands c
    on c.id = q.command_id
   and c.establishment_id = q.establishment_id
  left join public.profiles claimed on claimed.id = q.claimed_by
  cross join lateral (
    select coalesce(jsonb_agg(jsonb_build_object(
      'id', ci.id,
      'name', ci.product_name,
      'quantity', ci.quantity,
      'notes', ci.notes,
      'status', ci.kitchen_status
    ) order by ci.created_at, ci.id), '[]'::jsonb) as value
    from public.command_items ci
    where ci.establishment_id = q.establishment_id
      and ci.command_id = q.command_id
      and ci.source_request_id = q.id
  ) items
  where q.establishment_id = v_establishment_id
    and q.request_type = 'pedido_digital'
    and q.status in ('pendente', 'em_atendimento');

  return v_result;
end;
$$;

revoke all on function public.get_kitchen_queue() from public, anon;
grant execute on function public.get_kitchen_queue() to authenticated;

create or replace function public.claim_service_request(p_request_id bigint)
returns public.service_queue
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.service_queue;
  v_role text := public.current_role();
begin
  if coalesce(v_role, '') not in ('admin', 'caixa', 'atendente', 'cozinha') then
    raise exception 'Seu perfil nao tem permissao para atender a fila.';
  end if;

  update public.service_queue
  set status = 'em_atendimento', claimed_at = now(), claimed_by = (select auth.uid())
  where id = p_request_id
    and establishment_id = public.current_establishment_id()
    and status = 'pendente'
    and (v_role <> 'cozinha' or request_type = 'pedido_digital')
  returning * into v_request;

  if v_request.id is null then
    raise exception 'Solicitacao nao encontrada, nao permitida ou ja aceita.';
  end if;

  if v_request.request_type = 'pedido_digital' then
    update public.command_items
    set kitchen_status = 'preparando'
    where establishment_id = v_request.establishment_id
      and source_request_id = v_request.id
      and kitchen_status = 'pendente';
  end if;

  perform public.add_audit_log('claimed', 'service_queue', null, null, to_jsonb(v_request));
  return v_request;
end;
$$;

revoke all on function public.claim_service_request(bigint) from public, anon;
grant execute on function public.claim_service_request(bigint) to authenticated;

create or replace function public.claim_next_service_request()
returns public.service_queue
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.service_queue;
  v_role text := public.current_role();
begin
  if coalesce(v_role, '') not in ('admin', 'caixa', 'atendente', 'cozinha') then
    raise exception 'Seu perfil nao tem permissao para atender a fila.';
  end if;

  update public.service_queue
  set status = 'em_atendimento', claimed_at = now(), claimed_by = (select auth.uid())
  where id = (
    select q.id
    from public.service_queue q
    where q.establishment_id = public.current_establishment_id()
      and q.status = 'pendente'
      and (v_role <> 'cozinha' or q.request_type = 'pedido_digital')
    order by q.requested_at, q.id
    limit 1
    for update skip locked
  )
  returning * into v_request;

  if v_request.id is not null then
    if v_request.request_type = 'pedido_digital' then
      update public.command_items
      set kitchen_status = 'preparando'
      where establishment_id = v_request.establishment_id
        and source_request_id = v_request.id
        and kitchen_status = 'pendente';
    end if;
    perform public.add_audit_log('claimed', 'service_queue', null, null, to_jsonb(v_request));
  end if;
  return v_request;
end;
$$;

revoke all on function public.claim_next_service_request() from public, anon;
grant execute on function public.claim_next_service_request() to authenticated;

create or replace function public.complete_service_request(p_request_id bigint)
returns public.service_queue
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.service_queue;
  v_role text := public.current_role();
begin
  if coalesce(v_role, '') not in ('admin', 'caixa', 'atendente', 'cozinha') then
    raise exception 'Seu perfil nao tem permissao para concluir a fila.';
  end if;

  update public.service_queue
  set status = 'concluido', completed_at = now(), completed_by = (select auth.uid())
  where id = p_request_id
    and establishment_id = public.current_establishment_id()
    and status = 'em_atendimento'
    and (v_role <> 'cozinha' or request_type = 'pedido_digital')
  returning * into v_request;

  if v_request.id is null then
    raise exception 'Solicitacao nao encontrada, nao permitida ou ainda nao iniciada.';
  end if;

  if v_request.request_type = 'pedido_digital' then
    update public.command_items
    set kitchen_status = 'pronto'
    where establishment_id = v_request.establishment_id
      and source_request_id = v_request.id
      and kitchen_status = 'preparando';
  end if;

  perform public.add_audit_log('completed', 'service_queue', null, null, to_jsonb(v_request));
  return v_request;
end;
$$;

revoke all on function public.complete_service_request(bigint) from public, anon;
grant execute on function public.complete_service_request(bigint) to authenticated;

create or replace function public.update_item_kitchen_status(p_item_id uuid, p_status text)
returns public.command_items
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_item public.command_items;
  v_role text := public.current_role();
begin
  if coalesce(v_role, '') not in ('admin', 'cozinha') then
    raise exception 'Seu perfil nao tem permissao para alterar cozinha.';
  end if;
  if p_status not in ('pendente', 'preparando', 'pronto', 'entregue') then
    raise exception 'Status de cozinha invalido.';
  end if;

  update public.command_items i
  set kitchen_status = p_status
  where i.id = p_item_id
    and i.establishment_id = public.current_establishment_id()
    and (
      v_role = 'admin'
      or exists (
        select 1
        from public.service_queue q
        where q.id = i.source_request_id
          and q.establishment_id = i.establishment_id
          and q.request_type = 'pedido_digital'
      )
    )
  returning * into v_item;

  if v_item.id is null then
    raise exception 'Item nao encontrado ou nao permitido.';
  end if;

  update public.commands
  set version = version + 1
  where id = v_item.command_id
    and establishment_id = v_item.establishment_id;

  perform public.add_audit_log('kitchen_status_changed', 'command_items', p_item_id, null, to_jsonb(v_item));
  return v_item;
end;
$$;

revoke all on function public.update_item_kitchen_status(uuid, text) from public, anon;
grant execute on function public.update_item_kitchen_status(uuid, text) to authenticated;

create or replace function public.dashboard_establishment_id()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if public.current_role() = 'cozinha' then
    raise exception 'A cozinha nao possui acesso ao painel.' using errcode = '42501';
  end if;
  return public.current_establishment_id();
end;
$$;

revoke all on function public.dashboard_establishment_id() from public, anon;
grant execute on function public.dashboard_establishment_id() to authenticated;

create or replace function public.get_dashboard_summary()
returns jsonb
language sql
security definer
set search_path = ''
as $$
  with tenant as (
    select public.dashboard_establishment_id() id
  ),
  today_paid as (
    select c.* from public.commands c, tenant t
    where c.establishment_id = t.id
      and c.status = 'paga'
      and (c.closed_at at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date
  ),
  pay as (
    select p.method, sum(p.amount) total
    from public.payments p join today_paid c on c.id = p.command_id
    group by p.method
  )
  select jsonb_build_object(
    'cash_open', exists(select 1 from public.cash_sessions cs, tenant t where cs.establishment_id = t.id and cs.status = 'aberto'),
    'session', (select to_jsonb(cs) from public.cash_sessions cs, tenant t where cs.establishment_id = t.id and cs.status = 'aberto' order by opened_at desc limit 1),
    'total_vendido_hoje', coalesce((select sum(total) from today_paid), 0),
    'qtd_abertas', (select count(*) from public.commands c, tenant t where c.establishment_id = t.id and c.status in ('aberto','aguardando_pagamento')),
    'qtd_finalizadas_hoje', (select count(*) from today_paid),
    'qtd_pendentes_hoje', (
      select count(*) from public.commands c, tenant t
      where c.establishment_id = t.id and c.status = 'fiado'
        and (c.opened_at at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date
    ),
    'fila_pendente', (select count(*) from public.service_queue q, tenant t where q.establishment_id = t.id and q.status = 'pendente'),
    'total_dinheiro', coalesce((select total from pay where method = 'dinheiro'), 0),
    'total_pix', coalesce((select total from pay where method = 'pix'), 0),
    'total_cartao', coalesce((select sum(total) from pay where method in ('debito','credito')), 0)
  )
$$;

revoke all on function public.get_dashboard_summary() from public, anon;
grant execute on function public.get_dashboard_summary() to authenticated;

drop policy if exists "profiles tenant read" on public.profiles;
create policy "profiles tenant read" on public.profiles for select to authenticated
using (
  id = (select auth.uid())
  or (
    (select public.current_role()) <> 'cozinha'
    and (
      (select public.is_super_admin())
      or establishment_id = (select public.current_establishment_id())
    )
  )
);

drop policy if exists "settings tenant read" on public.settings;
create policy "settings tenant read" on public.settings for select to authenticated
using (
  establishment_id = (select public.current_establishment_id())
  and (select public.current_role()) <> 'cozinha'
);

drop policy if exists "categories tenant read" on public.categories;
create policy "categories tenant read" on public.categories for select to authenticated
using (
  establishment_id = (select public.current_establishment_id())
  and (select public.current_role()) <> 'cozinha'
);

drop policy if exists "products tenant read" on public.products;
create policy "products tenant read" on public.products for select to authenticated
using (
  establishment_id = (select public.current_establishment_id())
  and (select public.current_role()) <> 'cozinha'
);

drop policy if exists "commands tenant read" on public.commands;
create policy "commands tenant read" on public.commands for select to authenticated
using (
  establishment_id = (select public.current_establishment_id())
  and (select public.current_role()) <> 'cozinha'
);

drop policy if exists "command_items tenant read" on public.command_items;
create policy "command_items tenant read" on public.command_items for select to authenticated
using (
  establishment_id = (select public.current_establishment_id())
  and (select public.current_role()) <> 'cozinha'
);

drop policy if exists "cash_sessions tenant read" on public.cash_sessions;
create policy "cash_sessions tenant read" on public.cash_sessions for select to authenticated
using (
  establishment_id = (select public.current_establishment_id())
  and (select public.current_role()) <> 'cozinha'
);

drop policy if exists "service_queue tenant read" on public.service_queue;
create policy "service_queue tenant read" on public.service_queue for select to authenticated
using (
  establishment_id = (select public.current_establishment_id())
  and (
    (select public.current_role()) <> 'cozinha'
    or request_type = 'pedido_digital'
  )
);

notify pgrst, 'reload schema';
commit;
