-- Run in the SQL Editor as postgres. Every fixture is rolled back.
begin;
do $$
declare
  staff uuid;
  tenant uuid;
  product uuid;
  unlinked_item uuid;
  c public.commands;
  order_request public.service_queue;
  waiter_request public.service_queue;
  claimed public.service_queue;
  result jsonb;
  failed boolean;
begin
  select p.id, p.establishment_id into staff, tenant
  from public.profiles p
  join public.establishments e on e.id = p.establishment_id and e.active
  where p.active and p.role = 'admin'
  order by p.created_at
  limit 1;
  assert staff is not null, 'Test requires an active establishment administrator';

  insert into public.products(establishment_id, name, price, track_stock, stock_quantity)
  values (tenant, '__QA kitchen restriction__', 9.50, false, 0)
  returning id into product;

  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  c := public.create_command('__QA kitchen__', '__QA table__');
  perform public.add_command_item(c.id, product, 2, 'Sem cebola');
  order_request := public.enqueue_service_request(
    c.id,
    'pedido_digital',
    jsonb_build_object('source', 'pdv'),
    '__qa-kitchen-order__' || c.id::text
  );
  waiter_request := public.enqueue_service_request(
    c.id,
    'chamar_garcom',
    jsonb_build_object('source', 'pdv'),
    '__qa-kitchen-waiter__' || c.id::text
  );
  perform public.add_command_item(c.id, product, 1, 'Ainda não enviado');
  execute 'reset role';

  select id into unlinked_item
  from public.command_items
  where command_id = c.id and source_request_id is null
  limit 1;
  assert unlinked_item is not null, 'Fixture requires an item that was not sent to the kitchen';

  update public.profiles set role = 'cozinha' where id = staff;
  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';

  result := public.get_kitchen_queue();
  assert jsonb_array_length(result) = 1, 'Kitchen receives only its active food order';
  assert result->0->>'request_type' = 'pedido_digital', 'Waiter calls must not appear in the kitchen';
  assert result->0->'commands'->>'table_ref' = '__QA table__', 'Kitchen receives the table reference';
  assert jsonb_array_length(result->0->'payload'->'items') = 1, 'Kitchen receives only items linked to this order';
  assert result->0->'payload'->'items'->0->>'name' = '__QA kitchen restriction__', 'Kitchen receives the item name';

  assert (select count(*) from public.profiles) = 1, 'Kitchen can read only its own profile';
  assert (select count(*) from public.settings) = 0, 'Kitchen cannot read settings';
  assert (select count(*) from public.categories) = 0, 'Kitchen cannot read categories';
  assert (select count(*) from public.products) = 0, 'Kitchen cannot read products or stock';
  assert (select count(*) from public.commands) = 0, 'Kitchen cannot read commands directly';
  assert (select count(*) from public.command_items) = 0, 'Kitchen cannot read command items directly';
  assert (select count(*) from public.cash_sessions) = 0, 'Kitchen cannot read cash sessions';
  assert (select count(*) from public.payments) = 0, 'Kitchen cannot read payments';
  assert (select count(*) from public.audit_logs) = 0, 'Kitchen cannot read audit records';
  assert (select count(*) from public.service_queue) = 1, 'Kitchen direct queue access excludes waiter calls';

  failed := false;
  begin
    perform public.get_dashboard_summary();
  exception when insufficient_privilege then
    failed := true;
  end;
  assert failed, 'Kitchen cannot call the dashboard summary';

  failed := false;
  begin
    perform public.enqueue_service_request(c.id, 'pedido_digital', jsonb_build_object('source', 'pdv'), null);
  exception when others then
    failed := true;
  end;
  assert failed, 'Kitchen cannot enqueue orders';

  failed := false;
  begin
    perform public.claim_service_request(waiter_request.id);
  exception when others then
    failed := true;
  end;
  assert failed, 'Kitchen cannot claim waiter calls';

  failed := false;
  begin
    perform public.update_item_kitchen_status(unlinked_item, 'preparando');
  exception when others then
    failed := true;
  end;
  assert failed, 'Kitchen cannot update items that were not sent to its queue';

  claimed := public.claim_next_service_request();
  assert claimed.id = order_request.id, 'Kitchen claims the oldest food order';
  perform public.complete_service_request(order_request.id);
  assert jsonb_array_length(public.get_kitchen_queue()) = 0, 'Completed order leaves the active kitchen queue';

  execute 'reset role';
  assert (
    select kitchen_status = 'pronto'
    from public.command_items
    where source_request_id = order_request.id
  ), 'Completing a kitchen order marks its items ready';
  assert (
    select status = 'pendente'
    from public.service_queue
    where id = waiter_request.id
  ), 'Kitchen processing does not change the waiter queue';
end $$;
select 'PASS: kitchen sees and processes only linked food orders; admin, stock, cash and waiter data remain blocked' as result;
rollback;
