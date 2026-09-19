-- Customer access is a revocable bearer credential, independent of staff sessions.
begin;
create schema if not exists private;
create table if not exists private.command_access (
  command_id uuid primary key references public.commands(id) on delete cascade,
  token text not null unique,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);
alter table private.command_access enable row level security;
revoke all on private.command_access from public, anon, authenticated;

create or replace function private.resolve_customer_command(p_token text)
returns public.commands language plpgsql security definer set search_path = '' as $$
declare c public.commands;
begin
  if p_token is null or p_token !~ '^[a-f0-9]{64}$' then
    raise exception 'Acesso inválido ou encerrado. Peça um novo QR Code ao atendente.' using errcode = 'P0001';
  end if;
  select cmd.* into c from public.commands cmd
  join private.command_access a on a.command_id = cmd.id where a.token = p_token
  for update of cmd;
  if c.id is null or c.status not in ('aberto', 'aguardando_pagamento') or not exists (
    select 1 from private.command_access a join public.establishments e on e.id = c.establishment_id
    where a.command_id = c.id and a.token = p_token and a.revoked_at is null
      and a.expires_at > now() and e.active
  ) then
    raise exception 'Acesso inválido ou encerrado. Peça um novo QR Code ao atendente.' using errcode = 'P0001';
  end if;
  return c;
end $$;

create or replace function private.manage_command_access(p_command_id uuid, p_action text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare c public.commands; a private.command_access; active_access boolean;
begin
  if auth.uid() is null or not public.can_edit_orders() then
    raise exception 'Somente a equipe autorizada pode gerenciar o acesso.';
  end if;
  select * into c from public.commands where id = p_command_id
    and establishment_id = public.current_establishment_id() for update;
  if c.id is null then raise exception 'Comanda não encontrada.'; end if;
  if p_action not in ('get', 'generate', 'revoke') or p_action is null then raise exception 'Ação inválida.'; end if;
  if p_action = 'generate' then
    if c.status not in ('aberto', 'aguardando_pagamento') then raise exception 'A comanda está encerrada.'; end if;
    insert into private.command_access(command_id, token, expires_at)
    values (c.id, replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), now() + interval '24 hours')
    on conflict (command_id) do update set token = excluded.token, created_at = now(),
      expires_at = excluded.expires_at, revoked_at = null;
  elsif p_action = 'revoke' then
    update private.command_access set revoked_at = now() where command_id = c.id;
  end if;
  select * into a from private.command_access where command_id = c.id;
  active_access := a.command_id is not null and a.revoked_at is null and a.expires_at > now()
    and c.status in ('aberto', 'aguardando_pagamento');
  if p_action <> 'get' then
    perform public.add_audit_log('digital_access_' || p_action, 'commands', c.id, null, null);
  end if;
  return jsonb_build_object('active', coalesce(active_access, false),
    'token', case when active_access then a.token else null end,
    'created_at', a.created_at, 'expires_at', a.expires_at,
    'status', case when active_access then 'Ativo' when a.revoked_at is not null then 'Revogado'
      when a.command_id is not null then 'Expirado ou encerrado' else 'Não gerado' end);
end $$;

create or replace function private.customer_command(p_token text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare c public.commands;
begin
  c := private.resolve_customer_command(p_token);
  return jsonb_build_object(
    'command', jsonb_build_object('number', c.number, 'customer_name', c.customer_name,
      'table_ref', c.table_ref, 'status', c.status, 'subtotal', c.subtotal, 'discount', c.discount, 'total', c.total),
    'establishment', (select jsonb_build_object('name', e.name, 'logo_url', e.logo_url,
      'primary_color', e.primary_color, 'background_color', e.background_color)
      from public.establishments e where e.id = c.establishment_id),
    'items', (select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'name', i.product_name,
      'quantity', i.quantity, 'unit_price', i.unit_price, 'subtotal', i.subtotal,
      'notes', i.notes, 'status', i.kitchen_status) order by i.created_at, i.id), '[]'::jsonb)
      from public.command_items i where i.command_id = c.id),
    'products', (select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'name', p.name,
      'price', p.price, 'category', cat.name, 'available', not p.track_stock or p.stock_quantity > 0)
      order by p.name), '[]'::jsonb) from public.products p
      left join public.categories cat on cat.id = p.category_id and cat.establishment_id = c.establishment_id
      where p.establishment_id = c.establishment_id and p.active),
    'requests', (select coalesce(jsonb_agg(jsonb_build_object('id', q.id, 'type', q.request_type,
      'status', q.status, 'requested_at', q.requested_at) order by q.requested_at desc), '[]'::jsonb)
      from (select * from public.service_queue where command_id = c.id order by requested_at desc limit 20) q)
  );
end $$;

create or replace function private.customer_request(p_token text, p_request_id uuid, p_type text, p_items jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare c public.commands; p public.products; line jsonb; qty numeric;
  request_key text; request_row public.service_queue; item_id uuid;
  order_items jsonb := '[]'::jsonb; reserved numeric;
begin
  c := private.resolve_customer_command(p_token);
  if p_request_id is null or p_type is null or p_type not in ('pedido_digital', 'chamar_garcom', 'solicitar_fechamento') then
    raise exception 'Solicitação inválida.';
  end if;
  request_key := 'customer:' || c.id::text || ':' || p_request_id::text;
  select * into request_row from public.service_queue where establishment_id = c.establishment_id and idempotency_key = request_key;
  if request_row.id is not null then return jsonb_build_object('request_id', request_row.id, 'duplicate', true); end if;
  if p_type <> 'pedido_digital' then
    select * into request_row from public.service_queue where command_id = c.id and request_type = p_type
      and status in ('pendente', 'em_atendimento') order by requested_at limit 1;
    if request_row.id is not null then return jsonb_build_object('request_id', request_row.id, 'duplicate', true); end if;
  end if;
  if exists (select 1 from public.service_queue where command_id = c.id and request_type = p_type
    and requested_at > now() - interval '5 seconds') then
    raise exception 'Aguarde alguns segundos antes de enviar outra solicitação.';
  end if;
  if p_type = 'pedido_digital' then
    if c.status <> 'aberto' then raise exception 'O fechamento já foi solicitado. Chame o atendente para novos pedidos.'; end if;
    if jsonb_typeof(p_items) is distinct from 'array' then raise exception 'Informe os itens do pedido.'; end if;
    if jsonb_array_length(p_items) < 1 or jsonb_array_length(p_items) > 40 then raise exception 'Selecione entre 1 e 40 itens.'; end if;
    -- Lock products in a consistent order across simultaneous customer carts.
    for line in select value from jsonb_array_elements(p_items) order by value->>'product_id' loop
      qty := (line->>'quantity')::numeric;
      if qty is null or qty < 1 or qty > 50 or qty <> trunc(qty) then raise exception 'Quantidade inválida (1 a 50).'; end if;
      select * into p from public.products where id = (line->>'product_id')::uuid
        and establishment_id = c.establishment_id and active for update;
      if p.id is null then raise exception 'Produto indisponível neste estabelecimento.'; end if;
      if p.track_stock then
        select coalesce(sum(i.quantity), 0) into reserved from public.command_items i
          join public.commands cmd on cmd.id = i.command_id
          where i.product_id = p.id and cmd.status in ('aberto', 'aguardando_pagamento');
        if reserved + qty > p.stock_quantity then raise exception 'Estoque insuficiente para %. Peça ajuda ao atendente.', p.name; end if;
      end if;
      insert into public.command_items(establishment_id, command_id, product_id, product_name, unit_price, quantity, notes)
      values (c.establishment_id, c.id, p.id, p.name, p.price, qty, nullif(left(trim(line->>'notes'), 300), ''))
      returning id into item_id;
      order_items := order_items || jsonb_build_array(jsonb_build_object('id', item_id, 'name', p.name,
        'quantity', qty, 'notes', nullif(left(trim(line->>'notes'), 300), '')));
    end loop;
    perform public.recalculate_command_totals(c.id);
  elsif p_type = 'solicitar_fechamento' then
    update public.commands set status = 'aguardando_pagamento', version = version + 1 where id = c.id;
  end if;
  insert into public.service_queue(establishment_id, command_id, request_type, payload, idempotency_key)
  values(c.establishment_id, c.id, p_type, jsonb_build_object('source', 'customer', 'items', order_items), request_key)
  returning * into request_row;
  insert into public.audit_logs(establishment_id, action, entity, entity_id, new_value)
  values(c.establishment_id, 'customer_request', 'commands', c.id, jsonb_build_object('request_id', request_row.id, 'type', p_type));
  return jsonb_build_object('request_id', request_row.id, 'duplicate', false);
end $$;

create or replace function private.end_command_access()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.status = 'fiado' and old.status is distinct from new.status then raise exception 'Pagamento fiado não está disponível.'; end if;
  if new.status not in ('aberto', 'aguardando_pagamento') then
    update private.command_access set revoked_at = coalesce(revoked_at, now()) where command_id = new.id;
  end if;
  return new;
end $$;
create trigger trg_end_command_digital_access before update of status on public.commands
for each row execute function private.end_command_access();

-- Only these narrow, validated entry points are exposed. No anonymous table access.
create or replace function public.manage_command_access(p_command_id uuid, p_action text default 'get')
returns jsonb language sql security invoker set search_path = '' as $$ select private.manage_command_access(p_command_id, p_action) $$;
create or replace function public.customer_command(p_token text)
returns jsonb language sql security invoker set search_path = '' as $$ select private.customer_command(p_token) $$;
create or replace function public.customer_request(p_token text, p_request_id uuid, p_type text, p_items jsonb default '[]')
returns jsonb language sql security invoker set search_path = '' as $$ select private.customer_request(p_token, p_request_id, p_type, p_items) $$;
revoke all on function private.resolve_customer_command(text), private.end_command_access() from public, anon, authenticated;
revoke all on function private.manage_command_access(uuid,text), public.manage_command_access(uuid,text) from public, anon;
revoke all on function private.customer_command(text), public.customer_command(text), private.customer_request(text,uuid,text,jsonb), public.customer_request(text,uuid,text,jsonb) from public;
grant usage on schema private to anon, authenticated;
grant execute on function private.manage_command_access(uuid,text), public.manage_command_access(uuid,text) to authenticated;
grant execute on function private.customer_command(text), public.customer_command(text), private.customer_request(text,uuid,text,jsonb), public.customer_request(text,uuid,text,jsonb) to anon, authenticated;
notify pgrst, 'reload schema';
commit;
