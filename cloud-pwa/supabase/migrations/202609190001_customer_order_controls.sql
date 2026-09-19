-- Customer-request lifecycle and administrator-only order corrections.
-- This migration is additive: existing command items remain intact.
begin;

alter table public.command_items
  add column if not exists source_request_id bigint references public.service_queue(id) on delete set null;
alter table public.service_queue
  add column if not exists cancelled_at timestamptz;

create index if not exists command_items_source_request_id_idx
  on public.command_items (source_request_id)
  where source_request_id is not null;

-- The customer sees only the items and requests for the command represented by
-- their bearer credential. A pending digital request remains changeable until
-- it is accepted from the operational queue.
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
    'items', (select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'product_id', i.product_id,
      'source_request_id', i.source_request_id, 'name', i.product_name, 'quantity', i.quantity,
      'unit_price', i.unit_price, 'subtotal', i.subtotal, 'notes', i.notes, 'status', i.kitchen_status)
      order by i.created_at, i.id), '[]'::jsonb)
      from public.command_items i where i.command_id = c.id),
    'products', (select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'name', p.name,
      'price', p.price, 'category', cat.name, 'available', not p.track_stock or p.stock_quantity > 0)
      order by p.name), '[]'::jsonb) from public.products p
      left join public.categories cat on cat.id = p.category_id and cat.establishment_id = c.establishment_id
      where p.establishment_id = c.establishment_id and p.active),
    'requests', (select coalesce(jsonb_agg(jsonb_build_object(
      'id', q.id, 'type', q.request_type, 'status', q.status, 'requested_at', q.requested_at,
      'can_change', q.request_type = 'pedido_digital' and q.status = 'pendente' and exists (
        select 1 from public.command_items i
        where i.command_id = c.id and i.source_request_id = q.id and i.kitchen_status = 'pendente'
      ) and not exists (
        select 1 from public.command_items i
        where i.command_id = c.id and i.source_request_id = q.id and i.kitchen_status <> 'pendente'
      ),
      'items', (select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'product_id', i.product_id,
        'name', i.product_name, 'quantity', i.quantity, 'notes', i.notes, 'status', i.kitchen_status)
        order by i.created_at, i.id), '[]'::jsonb)
        from public.command_items i where i.command_id = c.id and i.source_request_id = q.id)
    ) order by q.requested_at desc), '[]'::jsonb)
      from (select * from public.service_queue where command_id = c.id order by requested_at desc limit 20) q)
  );
end $$;

-- New digital orders are grouped by their queue entry. That grouping is what
-- makes a later customer edit or cancellation atomic and safe.
create or replace function private.customer_request(p_token text, p_request_id uuid, p_type text, p_items jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare c public.commands; p public.products; line jsonb; qty numeric; p_id uuid;
  request_key text; request_row public.service_queue; item_id uuid;
  order_items jsonb := '[]'::jsonb; reserved numeric;
begin
  c := private.resolve_customer_command(p_token);
  if p_request_id is null or p_type is null or p_type not in ('pedido_digital', 'chamar_garcom', 'solicitar_fechamento') then
    raise exception 'Solicitação inválida.';
  end if;
  request_key := 'customer:' || c.id::text || ':' || p_request_id::text;
  select * into request_row from public.service_queue
    where establishment_id = c.establishment_id and idempotency_key = request_key;
  if request_row.id is not null then
    return jsonb_build_object('request_id', request_row.id, 'duplicate', true);
  end if;
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
    if exists (
      select 1 from (
        select nullif(trim(value->>'product_id'), '') as product_id, count(*) as occurrences
        from jsonb_array_elements(p_items) group by 1
      ) requested where requested.product_id is null or requested.occurrences > 1
    ) then raise exception 'Cada produto deve aparecer apenas uma vez no pedido.'; end if;

    insert into public.service_queue(establishment_id, command_id, request_type, payload, idempotency_key)
    values(c.establishment_id, c.id, p_type, jsonb_build_object('source', 'customer', 'items', '[]'::jsonb), request_key)
    returning * into request_row;

    -- Lock products in a consistent order across simultaneous customer carts.
    for line in select value from jsonb_array_elements(p_items) order by value->>'product_id' loop
      p_id := (line->>'product_id')::uuid;
      qty := (line->>'quantity')::numeric;
      if qty is null or qty < 1 or qty > 50 or qty <> trunc(qty) then raise exception 'Quantidade inválida (1 a 50).'; end if;
      p := null;
      select * into p from public.products where id = p_id
        and establishment_id = c.establishment_id and active for update;
      if p.id is null then raise exception 'Produto indisponível neste estabelecimento.'; end if;
      if p.track_stock then
        select coalesce(sum(i.quantity), 0) into reserved from public.command_items i
          join public.commands cmd on cmd.id = i.command_id
          where i.product_id = p.id and cmd.status in ('aberto', 'aguardando_pagamento');
        if reserved + qty > p.stock_quantity then raise exception 'Estoque insuficiente para %. Peça ajuda ao atendente.', p.name; end if;
      end if;
    end loop;

    for line in select value from jsonb_array_elements(p_items) order by value->>'product_id' loop
      p_id := (line->>'product_id')::uuid;
      qty := (line->>'quantity')::numeric;
      select * into p from public.products where id = p_id and establishment_id = c.establishment_id and active;
      insert into public.command_items(establishment_id, command_id, product_id, product_name, unit_price, quantity, notes, source_request_id)
      values (c.establishment_id, c.id, p.id, p.name, p.price, qty,
        nullif(left(trim(line->>'notes'), 300), ''), request_row.id)
      returning id into item_id;
      order_items := order_items || jsonb_build_array(jsonb_build_object('id', item_id, 'product_id', p.id,
        'name', p.name, 'quantity', qty, 'notes', nullif(left(trim(line->>'notes'), 300), '')));
    end loop;
    update public.service_queue set payload = jsonb_build_object('source', 'customer', 'items', order_items)
      where id = request_row.id;
    perform public.recalculate_command_totals(c.id);
  elsif p_type = 'solicitar_fechamento' then
    update public.commands set status = 'aguardando_pagamento', version = version + 1 where id = c.id;
    insert into public.service_queue(establishment_id, command_id, request_type, payload, idempotency_key)
    values(c.establishment_id, c.id, p_type, jsonb_build_object('source', 'customer', 'items', '[]'::jsonb), request_key)
    returning * into request_row;
  else
    insert into public.service_queue(establishment_id, command_id, request_type, payload, idempotency_key)
    values(c.establishment_id, c.id, p_type, jsonb_build_object('source', 'customer', 'items', '[]'::jsonb), request_key)
    returning * into request_row;
  end if;

  insert into public.audit_logs(establishment_id, user_id, action, entity, entity_id, new_value)
  values(c.establishment_id, null, 'customer_request', 'commands', c.id,
    jsonb_build_object('request_id', request_row.id, 'type', p_type));
  return jsonb_build_object('request_id', request_row.id, 'duplicate', false);
end $$;

create or replace function private.customer_change_request(
  p_token text,
  p_queue_id bigint,
  p_action text,
  p_items jsonb default '[]'::jsonb
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare c public.commands; q public.service_queue; p public.products; line jsonb;
  qty numeric; p_id uuid; reserved numeric; old_items jsonb; new_items jsonb := '[]'::jsonb; item_id uuid;
begin
  c := private.resolve_customer_command(p_token);
  if p_queue_id is null or p_action not in ('edit', 'cancel') then raise exception 'Alteração inválida.'; end if;
  select * into q from public.service_queue
    where id = p_queue_id and command_id = c.id and establishment_id = c.establishment_id
      and request_type = 'pedido_digital'
    for update;
  if q.id is null then raise exception 'Pedido não encontrado nesta comanda.'; end if;
  if q.status <> 'pendente' or exists (
    select 1 from public.command_items i
    where i.command_id = c.id and i.source_request_id = q.id and i.kitchen_status <> 'pendente'
  ) then
    raise exception 'Este pedido já foi aceito pela cozinha e não pode mais ser alterado pelo cliente.';
  end if;
  select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'product_id', i.product_id, 'name', i.product_name,
    'quantity', i.quantity, 'notes', i.notes) order by i.created_at, i.id), '[]'::jsonb)
    into old_items from public.command_items i where i.command_id = c.id and i.source_request_id = q.id;
  if jsonb_array_length(old_items) = 0 then raise exception 'Este pedido não possui itens alteráveis.'; end if;

  if p_action = 'cancel' then
    delete from public.command_items where command_id = c.id and source_request_id = q.id;
    update public.service_queue set status = 'cancelado', cancelled_at = now() where id = q.id;
    perform public.recalculate_command_totals(c.id);
    insert into public.audit_logs(establishment_id, user_id, action, entity, entity_id, old_value, new_value)
    values(c.establishment_id, null, 'customer_request_cancelled', 'commands', c.id, old_items,
      jsonb_build_object('request_id', q.id));
    return jsonb_build_object('request_id', q.id, 'cancelled', true);
  end if;

  if jsonb_typeof(p_items) is distinct from 'array' or jsonb_array_length(p_items) < 1 or jsonb_array_length(p_items) > 40 then
    raise exception 'Selecione entre 1 e 40 itens.';
  end if;
  if exists (
    select 1 from (
      select nullif(trim(value->>'product_id'), '') as product_id, count(*) as occurrences
      from jsonb_array_elements(p_items) group by 1
    ) requested where requested.product_id is null or requested.occurrences > 1
  ) then raise exception 'Cada produto deve aparecer apenas uma vez no pedido.'; end if;

  for line in select value from jsonb_array_elements(p_items) order by value->>'product_id' loop
    p_id := (line->>'product_id')::uuid;
    qty := (line->>'quantity')::numeric;
    if qty is null or qty < 1 or qty > 50 or qty <> trunc(qty) then raise exception 'Quantidade inválida (1 a 50).'; end if;
    p := null;
    select * into p from public.products where id = p_id and establishment_id = c.establishment_id and active for update;
    if p.id is null then raise exception 'Produto indisponível neste estabelecimento.'; end if;
    if p.track_stock then
      select coalesce(sum(i.quantity), 0) into reserved from public.command_items i
        join public.commands cmd on cmd.id = i.command_id
        where i.product_id = p.id and i.source_request_id is distinct from q.id
          and cmd.status in ('aberto', 'aguardando_pagamento');
      if reserved + qty > p.stock_quantity then raise exception 'Estoque insuficiente para %. Peça ajuda ao atendente.', p.name; end if;
    end if;
  end loop;

  delete from public.command_items where command_id = c.id and source_request_id = q.id;
  for line in select value from jsonb_array_elements(p_items) order by value->>'product_id' loop
    p_id := (line->>'product_id')::uuid;
    qty := (line->>'quantity')::numeric;
    select * into p from public.products where id = p_id and establishment_id = c.establishment_id and active;
    insert into public.command_items(establishment_id, command_id, product_id, product_name, unit_price, quantity, notes, source_request_id)
    values(c.establishment_id, c.id, p.id, p.name, p.price, qty,
      nullif(left(trim(line->>'notes'), 300), ''), q.id)
    returning id into item_id;
    new_items := new_items || jsonb_build_array(jsonb_build_object('id', item_id, 'product_id', p.id,
      'name', p.name, 'quantity', qty, 'notes', nullif(left(trim(line->>'notes'), 300), '')));
  end loop;
  update public.service_queue set payload = jsonb_build_object('source', 'customer', 'items', new_items) where id = q.id;
  perform public.recalculate_command_totals(c.id);
  insert into public.audit_logs(establishment_id, user_id, action, entity, entity_id, old_value, new_value)
  values(c.establishment_id, null, 'customer_request_edited', 'commands', c.id, old_items,
    jsonb_build_object('request_id', q.id, 'items', new_items));
  return jsonb_build_object('request_id', q.id, 'edited', true);
end $$;

create or replace function public.customer_change_request(p_token text, p_queue_id bigint, p_action text, p_items jsonb default '[]'::jsonb)
returns jsonb language sql security invoker set search_path = '' as $$
  select private.customer_change_request(p_token, p_queue_id, p_action, p_items)
$$;

-- A kitchen/queue acceptance turns a pending customer request into preparation.
-- From this point the customer can still see it, but cannot rewrite or remove it.
create or replace function public.claim_next_service_request()
returns public.service_queue language plpgsql security definer set search_path = '' as $$
declare v_request public.service_queue;
begin
  if public.current_role() not in ('admin', 'caixa', 'atendente', 'cozinha') then
    raise exception 'Seu perfil nao tem permissao para atender a fila.';
  end if;
  update public.service_queue
  set status = 'em_atendimento', claimed_at = now(), claimed_by = (select auth.uid())
  where id = (
    select q.id from public.service_queue q
    where q.establishment_id = public.current_establishment_id() and q.status = 'pendente'
    order by q.requested_at asc, q.id asc
    limit 1 for update skip locked
  )
  returning * into v_request;
  if v_request.id is not null then
    if v_request.request_type = 'pedido_digital' then
      update public.command_items set kitchen_status = 'preparando'
      where establishment_id = v_request.establishment_id and source_request_id = v_request.id
        and kitchen_status = 'pendente';
    end if;
    perform public.add_audit_log('claimed', 'service_queue', null, null, to_jsonb(v_request));
  end if;
  return v_request;
end $$;

create or replace function public.complete_service_request(p_request_id bigint)
returns public.service_queue language plpgsql security definer set search_path = '' as $$
declare v_request public.service_queue;
begin
  if public.current_role() not in ('admin', 'caixa', 'atendente', 'cozinha') then
    raise exception 'Seu perfil nao tem permissao para concluir a fila.';
  end if;
  update public.service_queue set status = 'concluido', completed_at = now(), completed_by = (select auth.uid())
  where id = p_request_id and establishment_id = public.current_establishment_id() and status = 'em_atendimento'
  returning * into v_request;
  if v_request.id is null then raise exception 'Solicitacao nao encontrada ou ainda nao iniciada.'; end if;
  perform public.add_audit_log('completed', 'service_queue', null, null, to_jsonb(v_request));
  return v_request;
end $$;

-- Adding a new item always creates a new line. It never silently alters an
-- existing accepted item just because product and notes happen to match.
create or replace function public.add_command_item(
  p_command_id uuid,
  p_product_id uuid,
  p_quantity numeric default 1,
  p_notes text default ''
)
returns public.commands language plpgsql security definer set search_path = '' as $$
declare v_command public.commands; v_product public.products; v_item_id uuid; v_establishment_id uuid;
begin
  v_establishment_id := public.current_establishment_id();
  if not public.can_edit_orders() or v_establishment_id is null then raise exception 'Seu perfil nao tem permissao para editar comandas.'; end if;
  if p_quantity is null or p_quantity <= 0 then raise exception 'A quantidade deve ser maior que zero.'; end if;
  select * into v_command from public.commands where id = p_command_id and establishment_id = v_establishment_id for update;
  if v_command.id is null then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento') then raise exception 'Comanda ja nao pode ser editada.'; end if;
  select * into v_product from public.products where id = p_product_id and establishment_id = v_establishment_id and active for update;
  if v_product.id is null then raise exception 'Produto invalido ou inativo.'; end if;
  insert into public.command_items(establishment_id, command_id, product_id, product_name, unit_price, quantity, notes, created_by)
  values(v_establishment_id, p_command_id, v_product.id, v_product.name, v_product.price, p_quantity,
    nullif(trim(p_notes), ''), (select auth.uid())) returning id into v_item_id;
  perform public.recalculate_command_totals(p_command_id);
  perform public.add_audit_log('item_added', 'commands', p_command_id, null, jsonb_build_object('item_id', v_item_id));
  select * into v_command from public.commands where id = p_command_id and establishment_id = v_establishment_id;
  return v_command;
end $$;

-- Existing item corrections are deliberately separate from adding a new order.
-- Only an administrator can correct/remove a line and a reason is mandatory.
create or replace function public.admin_adjust_command_item(
  p_item_id uuid,
  p_product_id uuid,
  p_quantity numeric,
  p_reason text
)
returns public.commands language plpgsql security definer set search_path = '' as $$
declare v_item public.command_items; v_command public.commands; v_product public.products;
  v_establishment_id uuid := public.current_establishment_id(); v_reason text; reserved numeric;
begin
  if (select auth.uid()) is null or not public.is_admin() or v_establishment_id is null then
    raise exception 'Somente o administrador pode ajustar itens.';
  end if;
  v_reason := nullif(left(trim(coalesce(p_reason, '')), 500), '');
  if v_reason is null or char_length(v_reason) < 5 then
    raise exception 'Informe uma justificativa de ao menos 5 caracteres.';
  end if;
  if p_quantity is null or p_quantity < 0 or p_quantity > 999 then raise exception 'Quantidade inválida.'; end if;
  select * into v_item from public.command_items where id = p_item_id and establishment_id = v_establishment_id for update;
  if v_item.id is null then raise exception 'Item não encontrado.'; end if;
  select * into v_command from public.commands where id = v_item.command_id and establishment_id = v_establishment_id for update;
  if v_command.id is null or v_command.status not in ('aberto', 'aguardando_pagamento') then raise exception 'Comanda já não pode ser ajustada.'; end if;
  if p_quantity = 0 then
    delete from public.command_items where id = v_item.id and establishment_id = v_establishment_id;
    perform public.recalculate_command_totals(v_command.id);
    perform public.add_audit_log('admin_item_adjusted', 'commands', v_command.id, to_jsonb(v_item),
      jsonb_build_object('reason', v_reason, 'action', 'removed'));
  else
    if p_product_id is null then p_product_id := v_item.product_id; end if;
    select * into v_product from public.products where id = p_product_id and establishment_id = v_establishment_id and active for update;
    if v_product.id is null then raise exception 'Produto inválido ou inativo.'; end if;
    if v_product.track_stock then
      select coalesce(sum(i.quantity), 0) into reserved from public.command_items i
      join public.commands c on c.id = i.command_id
      where i.establishment_id = v_establishment_id and i.product_id = v_product.id and i.id <> v_item.id
        and c.status in ('aberto', 'aguardando_pagamento');
      if reserved + p_quantity > v_product.stock_quantity then raise exception 'Estoque insuficiente para %.', v_product.name; end if;
    end if;
    update public.command_items set product_id = v_product.id, product_name = v_product.name,
      unit_price = v_product.price, quantity = p_quantity where id = v_item.id and establishment_id = v_establishment_id;
    perform public.recalculate_command_totals(v_command.id);
    select * into v_item from public.command_items where id = p_item_id and establishment_id = v_establishment_id;
    perform public.add_audit_log('admin_item_adjusted', 'commands', v_command.id, null,
      jsonb_build_object('reason', v_reason, 'action', 'updated', 'item', to_jsonb(v_item)));
  end if;
  select * into v_command from public.commands where id = v_command.id and establishment_id = v_establishment_id;
  return v_command;
end $$;

-- Old generic correction RPCs remain callable only as explicit failures, so a
-- stale client cannot bypass the administrator-and-reason rule.
create or replace function public.update_command_item_quantity(p_item_id uuid, p_quantity numeric)
returns public.commands language plpgsql security definer set search_path = '' as $$
begin
  raise exception 'Use o ajuste administrativo com justificativa para alterar um item existente.';
end $$;

create or replace function public.remove_command_item(p_item_id uuid)
returns public.commands language plpgsql security definer set search_path = '' as $$
begin
  raise exception 'Use o ajuste administrativo com justificativa para remover um item existente.';
end $$;

revoke all on function private.customer_change_request(text, bigint, text, jsonb) from public, anon, authenticated;
revoke all on function public.customer_change_request(text, bigint, text, jsonb) from public;
revoke all on function public.admin_adjust_command_item(uuid, uuid, numeric, text) from public, anon;
grant execute on function public.customer_change_request(text, bigint, text, jsonb) to anon, authenticated;
grant execute on function public.admin_adjust_command_item(uuid, uuid, numeric, text) to authenticated;
grant execute on function public.claim_next_service_request(), public.complete_service_request(bigint) to authenticated;

notify pgrst, 'reload schema';
commit;
