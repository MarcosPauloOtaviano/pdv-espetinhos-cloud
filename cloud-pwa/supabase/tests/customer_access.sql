-- Run in the SQL Editor as postgres. Every fixture is rolled back.
begin;
do $$
declare
  staff uuid; other_tenant uuid; tenant uuid; c public.commands;
  product uuid; foreign_product uuid; token1 text; token2 text; result jsonb;
  request_id uuid := gen_random_uuid(); queue_id bigint; cancelled_queue_id bigint; item_id uuid; failed boolean;
begin
  select id, establishment_id into staff, tenant from public.profiles where username = 'ronaldo' and active;
  assert staff is not null, 'Test requires the configured Ronaldo admin';
  select id into other_tenant from public.establishments where id <> tenant limit 1;
  assert other_tenant is not null, 'Test requires two establishments';
  insert into public.products(establishment_id, name, price, track_stock, stock_quantity)
  values (tenant, '__QA digital__', 7.50, true, 10) returning id into product;
  insert into public.products(establishment_id, name, price)
  values (other_tenant, '__QA isolation__', 11) returning id into foreign_product;
  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  c := public.create_command('__QA rollback__', '__QA');
  token1 := public.manage_command_access(c.id, 'generate')->>'token';
  assert length(token1) = 64;
  assert public.manage_command_access(c.id, 'get')->>'token' = token1, 'Redisplay must preserve token';
  execute 'reset role';
  perform set_config('request.jwt.claims', '{}', true);
  execute 'set local role anon';
  result := public.customer_command(token1);
  assert result->'command'->>'number' = c.number::text;
  assert not exists(select 1 from jsonb_array_elements(result->'products') p where p->>'id' = foreign_product::text);
  assert not exists(select 1 from jsonb_array_elements(result->'products') p where p ? 'cost' or p ? 'stock_quantity');
  failed := false;
  begin perform public.manage_command_access(c.id, 'generate'); exception when insufficient_privilege then failed := true; end;
  assert failed, 'Anonymous cannot generate credentials';
  failed := false;
  begin perform public.manage_command_access(c.id, 'revoke'); exception when insufficient_privilege then failed := true; end;
  assert failed, 'Anonymous cannot revoke credentials';
  failed := false;
  begin perform public.customer_command(repeat('a', 64)); exception when raise_exception then failed := true; end;
  assert failed, 'Invalid token rejected';
  failed := false;
  begin
    perform public.customer_request(token1, gen_random_uuid(), 'pedido_digital', jsonb_build_array(
      jsonb_build_object('product_id', product, 'quantity', 1), jsonb_build_object('product_id', foreign_product, 'quantity', 1)));
  exception when raise_exception then failed := true; end;
  assert failed, 'Cross-establishment product rejected';
  assert jsonb_array_length(public.customer_command(token1)->'items') = 0, 'Invalid cart must roll back every item';
  failed := false;
  begin perform public.customer_request(token1, gen_random_uuid(), 'pedido_digital', jsonb_build_array(jsonb_build_object('product_id', product, 'quantity', 11)));
  exception when raise_exception then failed := true; end;
  assert failed, 'Insufficient stock rejected';
  result := public.customer_request(token1, request_id, 'pedido_digital', jsonb_build_array(
    jsonb_build_object('product_id', product, 'quantity', 2, 'price', 0.01, 'notes', 'Sem cebola')));
  assert (result->>'duplicate')::boolean = false;
  queue_id := (result->>'request_id')::bigint;
  result := public.customer_request(token1, request_id, 'pedido_digital', jsonb_build_array(jsonb_build_object('product_id', product, 'quantity', 2)));
  assert (result->>'duplicate')::boolean, 'Retry must not duplicate order';
  result := public.customer_command(token1);
  assert (result->'command'->>'total')::numeric = 15, 'Prices come from server';
  assert jsonb_array_length(result->'items') = 1, 'Retry adds no items';
  assert jsonb_array_length(result->'requests') = 1, 'Retry adds no queue event';

  result := public.customer_change_request(token1, queue_id, 'edit', jsonb_build_array(
    jsonb_build_object('product_id', product, 'quantity', 3, 'notes', 'Sem cebola')));
  assert (result->>'edited')::boolean, 'Customer can edit an unaccepted request';
  assert (public.customer_command(token1)->'command'->>'total')::numeric = 22.50, 'Edited request recalculates the server total';
  assert (public.customer_command(token1)->'requests'->0->>'can_change')::boolean, 'Pending request remains editable';

  -- The production flow rate-limits repeated requests for five seconds. Move
  -- the fixture clock-equivalent request outside that window before testing a
  -- separate cancellation.
  execute 'reset role';
  update public.service_queue set requested_at = now() - interval '6 seconds' where id = queue_id;
  perform set_config('request.jwt.claims', '{}', true);
  execute 'set local role anon';
  result := public.customer_request(token1, gen_random_uuid(), 'pedido_digital', jsonb_build_array(
    jsonb_build_object('product_id', product, 'quantity', 1)));
  cancelled_queue_id := (result->>'request_id')::bigint;
  result := public.customer_change_request(token1, cancelled_queue_id, 'cancel', '[]');
  assert (result->>'cancelled')::boolean, 'Customer can cancel an unaccepted request';
  assert (public.customer_command(token1)->'command'->>'total')::numeric = 22.50, 'Cancelled request is removed from the total';
  assert (select status = 'cancelado' from public.service_queue where id = cancelled_queue_id), 'Cancelled request leaves an audit-safe queue record';

  execute 'reset role';
  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.claim_next_service_request();
  select id into item_id from public.command_items where source_request_id = queue_id;
  assert (select kitchen_status = 'preparando' from public.command_items where id = item_id), 'Queue acceptance starts preparation';
  execute 'reset role';
  perform set_config('request.jwt.claims', '{}', true);
  execute 'set local role anon';
  failed := false;
  begin perform public.customer_change_request(token1, queue_id, 'cancel', '[]'); exception when raise_exception then failed := true; end;
  assert failed, 'Customer cannot change an accepted request';
  execute 'reset role';
  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  failed := false;
  begin perform public.admin_adjust_command_item(item_id, product, 3, ''); exception when raise_exception then failed := true; end;
  assert failed, 'Administrator justification is mandatory';
  perform public.admin_adjust_command_item(item_id, product, 3, 'Confirmação do pedido após conferência na mesa');
  assert exists(select 1 from public.audit_logs where entity_id = c.id and action = 'admin_item_adjusted'), 'Administrator correction is audited';
  execute 'reset role';
  perform set_config('request.jwt.claims', '{}', true);
  execute 'set local role anon';

  perform public.customer_request(token1, gen_random_uuid(), 'chamar_garcom', '[]');
  result := public.customer_request(token1, gen_random_uuid(), 'chamar_garcom', '[]');
  assert (result->>'duplicate')::boolean, 'Waiter call deduplicated';
  execute 'reset role';
  assert (select count(*) from public.service_queue where command_id = c.id and establishment_id = tenant) = 3;
  assert (select stock_quantity from public.products where id = product) = 10, 'Stock is not deducted twice';
  assert not has_table_privilege('anon', 'private.command_access', 'select');
  assert not has_function_privilege('anon', 'private.resolve_customer_command(text)', 'execute');
  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  token2 := public.manage_command_access(c.id, 'generate')->>'token';
  assert token1 <> token2;
  execute 'reset role';
  perform set_config('request.jwt.claims', '{}', true);
  execute 'set local role anon';
  failed := false;
  begin perform public.customer_command(token1); exception when raise_exception then failed := true; end;
  assert failed, 'Rotated token rejected';
  assert (public.customer_command(token2)->'command'->>'total')::numeric = 22.50, 'Rotation preserves items and total';
  perform public.customer_request(token2, gen_random_uuid(), 'solicitar_fechamento', '[]');
  assert public.customer_command(token2)->'command'->>'status' = 'aguardando_pagamento';
  execute 'reset role';
  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  perform public.manage_command_access(c.id, 'revoke');
  execute 'reset role';
  perform set_config('request.jwt.claims', '{}', true);
  execute 'set local role anon';
  failed := false;
  begin perform public.customer_command(token2); exception when raise_exception then failed := true; end;
  assert failed, 'Revoked token rejected';
  execute 'reset role';
  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  token2 := public.manage_command_access(c.id, 'generate')->>'token';
  update private.command_access set expires_at = now() - interval '1 second' where command_id = c.id;
  failed := false;
  begin perform public.customer_command(token2); exception when raise_exception then failed := true; end;
  assert failed, 'Expired token rejected';
  token2 := public.manage_command_access(c.id, 'generate')->>'token';
  failed := false;
  begin perform public.mark_command_pending(c.id); exception when raise_exception then failed := true; end;
  assert failed, 'Fiado is disabled in the backend';
  update public.commands set status = 'paga' where id = c.id;
  failed := false;
  begin perform public.customer_command(token2); exception when raise_exception then failed := true; end;
  assert failed, 'Closing invalidates access';
  update public.commands set status = 'aberto' where id = c.id;
  failed := false;
  begin perform public.customer_command(token2); exception when raise_exception then failed := true; end;
  assert failed, 'Reopening cannot revive old access';
  token2 := public.manage_command_access(c.id, 'generate')->>'token';
  perform public.cancel_command(c.id);
  failed := false;
  begin perform public.customer_command(token2); exception when raise_exception then failed := true; end;
  assert failed, 'Cancel invalidates access';
end $$;
select 'PASS: access, isolation, prices, pending edits/cancellation, accepted-order protection, admin audit, stock, queue, rotation, revocation, expiration, closure and fiado' as result;
rollback;
