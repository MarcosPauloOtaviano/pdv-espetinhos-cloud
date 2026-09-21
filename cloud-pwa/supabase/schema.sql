-- PDV Espetinhos cloud schema for Supabase/PostgreSQL.
-- Run this file once in Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text not null unique,
  full_name text,
  role text not null default 'atendente'
    check (role in ('admin', 'caixa', 'atendente', 'cozinha')),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.settings (
  key text primary key,
  value text,
  updated_by uuid references public.profiles(id),
  updated_at timestamptz not null default now()
);

create table if not exists public.categories (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  category_id uuid references public.categories(id),
  price numeric(12,2) not null check (price >= 0),
  cost numeric(12,2) not null default 0 check (cost >= 0),
  track_stock boolean not null default false,
  stock_quantity numeric(12,3) not null default 0,
  low_stock_threshold numeric(12,3) not null default 5,
  active boolean not null default true,
  notes text,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.command_counters (
  business_date date primary key,
  last_number integer not null
);

create table if not exists public.cash_sessions (
  id uuid primary key default gen_random_uuid(),
  opened_by uuid not null references public.profiles(id),
  closed_by uuid references public.profiles(id),
  opening_amount numeric(12,2) not null default 0 check (opening_amount >= 0),
  counted_amount numeric(12,2),
  expected_cash numeric(12,2),
  difference numeric(12,2),
  status text not null default 'aberto' check (status in ('aberto', 'fechado')),
  open_notes text,
  close_notes text,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists only_one_open_cash_session
  on public.cash_sessions ((status))
  where status = 'aberto';

create table if not exists public.commands (
  id uuid primary key default gen_random_uuid(),
  business_date date not null default ((now() at time zone 'America/Sao_Paulo')::date),
  number integer not null,
  customer_name text,
  table_ref text,
  status text not null default 'aberto'
    check (status in ('aberto', 'aguardando_pagamento', 'paga', 'cancelada', 'fiado')),
  discount numeric(12,2) not null default 0 check (discount >= 0),
  subtotal numeric(12,2) not null default 0,
  total numeric(12,2) not null default 0,
  notes text,
  version integer not null default 1,
  cash_session_id uuid references public.cash_sessions(id),
  created_by uuid references public.profiles(id),
  closed_by uuid references public.profiles(id),
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_date, number)
);

create table if not exists public.command_items (
  id uuid primary key default gen_random_uuid(),
  command_id uuid not null references public.commands(id) on delete cascade,
  product_id uuid references public.products(id),
  product_name text not null,
  unit_price numeric(12,2) not null check (unit_price >= 0),
  quantity numeric(12,3) not null check (quantity > 0),
  subtotal numeric(12,2) generated always as (round(unit_price * quantity, 2)) stored,
  notes text,
  kitchen_status text not null default 'pendente'
    check (kitchen_status in ('pendente', 'preparando', 'pronto', 'entregue')),
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(),
  command_id uuid not null references public.commands(id) on delete cascade,
  cash_session_id uuid not null references public.cash_sessions(id),
  method text not null check (method in ('dinheiro', 'pix', 'debito', 'credito')),
  amount numeric(12,2) not null check (amount > 0),
  received_amount numeric(12,2),
  change_amount numeric(12,2),
  pix_confirmed boolean not null default false,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now()
);

create table if not exists public.cash_movements (
  id uuid primary key default gen_random_uuid(),
  cash_session_id uuid not null references public.cash_sessions(id) on delete cascade,
  type text not null check (type in ('sangria', 'reforco')),
  amount numeric(12,2) not null check (amount > 0),
  reason text,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now()
);

create table if not exists public.audit_logs (
  id bigint generated always as identity primary key,
  user_id uuid references public.profiles(id),
  action text not null,
  entity text not null,
  entity_id uuid,
  old_value jsonb,
  new_value jsonb,
  created_at timestamptz not null default now()
);

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_profiles_updated_at on public.profiles;
create trigger trg_profiles_updated_at before update on public.profiles
for each row execute function public.touch_updated_at();

drop trigger if exists trg_settings_updated_at on public.settings;
create trigger trg_settings_updated_at before update on public.settings
for each row execute function public.touch_updated_at();

drop trigger if exists trg_categories_updated_at on public.categories;
create trigger trg_categories_updated_at before update on public.categories
for each row execute function public.touch_updated_at();

drop trigger if exists trg_products_updated_at on public.products;
create trigger trg_products_updated_at before update on public.products
for each row execute function public.touch_updated_at();

drop trigger if exists trg_commands_updated_at on public.commands;
create trigger trg_commands_updated_at before update on public.commands
for each row execute function public.touch_updated_at();

drop trigger if exists trg_command_items_updated_at on public.command_items;
create trigger trg_command_items_updated_at before update on public.command_items
for each row execute function public.touch_updated_at();

drop trigger if exists trg_cash_sessions_updated_at on public.cash_sessions;
create trigger trg_cash_sessions_updated_at before update on public.cash_sessions
for each row execute function public.touch_updated_at();

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, username, full_name, role)
  values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data->>'username', ''), split_part(new.email, '@', 1)),
    nullif(new.raw_user_meta_data->>'full_name', ''),
    'atendente'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_auth_user();

create or replace function public.current_profile()
returns public.profiles
language sql
stable
security definer
set search_path = public
as $$
  select *
  from public.profiles
  where id = auth.uid() and active = true
  limit 1
$$;

create or replace function public.current_role()
returns text
language sql
stable
security definer
set search_path = public
as $$
  select role from public.profiles where id = auth.uid() and active = true
$$;

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(public.current_role() = 'admin', false)
$$;

create or replace function public.can_manage_money()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(public.current_role() in ('admin', 'caixa'), false)
$$;

create or replace function public.can_edit_orders()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(public.current_role() in ('admin', 'caixa', 'atendente'), false)
$$;

create or replace function public.add_audit_log(
  p_action text,
  p_entity text,
  p_entity_id uuid,
  p_old jsonb default null,
  p_new jsonb default null
)
returns void
language sql
security definer
set search_path = public
as $$
  insert into public.audit_logs (user_id, action, entity, entity_id, old_value, new_value)
  values (auth.uid(), p_action, p_entity, p_entity_id, p_old, p_new)
$$;

create or replace function public.recalculate_command_totals(p_command_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_subtotal numeric(12,2);
  v_discount numeric(12,2);
begin
  select coalesce(sum(subtotal), 0) into v_subtotal
  from public.command_items
  where command_id = p_command_id;

  select discount into v_discount
  from public.commands
  where id = p_command_id;

  update public.commands
  set subtotal = v_subtotal,
      total = greatest(v_subtotal - coalesce(v_discount, 0), 0),
      version = version + 1
  where id = p_command_id;
end;
$$;

create or replace function public.create_command(
  p_customer_name text default '',
  p_table_ref text default ''
)
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_date date := (now() at time zone 'America/Sao_Paulo')::date;
  v_number integer;
  v_command public.commands;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para criar comandas.';
  end if;

  insert into public.command_counters (business_date, last_number)
  values (v_date, 1)
  on conflict (business_date)
  do update set last_number = public.command_counters.last_number + 1
  returning last_number into v_number;

  insert into public.commands (business_date, number, customer_name, table_ref, created_by)
  values (v_date, v_number, nullif(trim(p_customer_name), ''), nullif(trim(p_table_ref), ''), auth.uid())
  returning * into v_command;

  perform public.add_audit_log('created', 'commands', v_command.id, null, to_jsonb(v_command));
  return v_command;
end;
$$;

create or replace function public.add_command_item(
  p_command_id uuid,
  p_product_id uuid,
  p_quantity numeric default 1,
  p_notes text default ''
)
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_command public.commands;
  v_product public.products;
  v_item_id uuid;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para editar comandas.';
  end if;
  if p_quantity is null or p_quantity <= 0 then
    raise exception 'A quantidade deve ser maior que zero.';
  end if;

  select * into v_command from public.commands where id = p_command_id for update;
  if not found then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento') then
    raise exception 'Comanda ja nao pode ser editada.';
  end if;

  select * into v_product from public.products where id = p_product_id and active = true;
  if not found then raise exception 'Produto invalido ou inativo.'; end if;

  if coalesce(trim(p_notes), '') = '' then
    select id into v_item_id
    from public.command_items
    where command_id = p_command_id and product_id = p_product_id and coalesce(notes, '') = ''
    limit 1
    for update;
  end if;

  if v_item_id is not null then
    update public.command_items
    set quantity = quantity + p_quantity
    where id = v_item_id;
  else
    insert into public.command_items (
      command_id, product_id, product_name, unit_price, quantity, notes, created_by
    )
    values (
      p_command_id, p_product_id, v_product.name, v_product.price, p_quantity,
      nullif(trim(p_notes), ''), auth.uid()
    )
    returning id into v_item_id;
  end if;

  perform public.recalculate_command_totals(p_command_id);
  perform public.add_audit_log('item_added', 'commands', p_command_id, null, jsonb_build_object('item_id', v_item_id));
  select * into v_command from public.commands where id = p_command_id;
  return v_command;
end;
$$;

create or replace function public.update_command_item_quantity(p_item_id uuid, p_quantity numeric)
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_item public.command_items;
  v_command public.commands;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para editar comandas.';
  end if;
  if p_quantity is null or p_quantity <= 0 then
    raise exception 'A quantidade deve ser maior que zero.';
  end if;

  select * into v_item from public.command_items where id = p_item_id for update;
  if not found then raise exception 'Item nao encontrado.'; end if;

  select * into v_command from public.commands where id = v_item.command_id for update;
  if v_command.status not in ('aberto', 'aguardando_pagamento') then
    raise exception 'Comanda ja nao pode ser editada.';
  end if;

  update public.command_items set quantity = p_quantity where id = p_item_id;
  perform public.recalculate_command_totals(v_item.command_id);
  perform public.add_audit_log('item_quantity_changed', 'commands', v_item.command_id, to_jsonb(v_item), jsonb_build_object('quantity', p_quantity));
  select * into v_command from public.commands where id = v_item.command_id;
  return v_command;
end;
$$;

create or replace function public.remove_command_item(p_item_id uuid)
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_item public.command_items;
  v_command public.commands;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para editar comandas.';
  end if;

  select * into v_item from public.command_items where id = p_item_id for update;
  if not found then raise exception 'Item nao encontrado.'; end if;
  select * into v_command from public.commands where id = v_item.command_id for update;
  if v_command.status not in ('aberto', 'aguardando_pagamento') then
    raise exception 'Comanda ja nao pode ser editada.';
  end if;

  delete from public.command_items where id = p_item_id;
  perform public.recalculate_command_totals(v_item.command_id);
  perform public.add_audit_log('item_removed', 'commands', v_item.command_id, to_jsonb(v_item), null);
  select * into v_command from public.commands where id = v_item.command_id;
  return v_command;
end;
$$;

create or replace function public.set_command_discount(p_command_id uuid, p_discount numeric)
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_command public.commands;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para editar comandas.';
  end if;
  if p_discount is null or p_discount < 0 then
    raise exception 'O desconto nao pode ser negativo.';
  end if;
  select * into v_command from public.commands where id = p_command_id for update;
  if not found then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento') then
    raise exception 'Comanda ja nao pode ser editada.';
  end if;
  update public.commands set discount = p_discount where id = p_command_id;
  perform public.recalculate_command_totals(p_command_id);
  perform public.add_audit_log('discount_changed', 'commands', p_command_id, to_jsonb(v_command), jsonb_build_object('discount', p_discount));
  select * into v_command from public.commands where id = p_command_id;
  return v_command;
end;
$$;

create or replace function public.update_command_info(
  p_command_id uuid,
  p_customer_name text default '',
  p_table_ref text default '',
  p_notes text default null
)
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_command public.commands;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para editar comandas.';
  end if;

  select * into v_command from public.commands where id = p_command_id for update;
  if not found then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento') then
    raise exception 'Comanda ja nao pode ser editada.';
  end if;

  update public.commands
  set customer_name = nullif(trim(p_customer_name), ''),
      table_ref = nullif(trim(p_table_ref), ''),
      notes = case when p_notes is null then notes else nullif(trim(p_notes), '') end,
      version = version + 1
  where id = p_command_id
  returning * into v_command;

  perform public.add_audit_log('info_changed', 'commands', p_command_id, null, to_jsonb(v_command));
  return v_command;
end;
$$;

create or replace function public.update_item_kitchen_status(p_item_id uuid, p_status text)
returns public.command_items
language plpgsql
security definer
set search_path = public
as $$
declare
  v_item public.command_items;
begin
  if public.current_role() not in ('admin', 'cozinha') then
    raise exception 'Seu perfil nao tem permissao para alterar cozinha.';
  end if;
  if p_status not in ('pendente', 'preparando', 'pronto', 'entregue') then
    raise exception 'Status de cozinha invalido.';
  end if;

  update public.command_items
  set kitchen_status = p_status
  where id = p_item_id
  returning * into v_item;
  if not found then raise exception 'Item nao encontrado.'; end if;

  update public.commands
  set version = version + 1
  where id = v_item.command_id;

  perform public.add_audit_log('kitchen_status_changed', 'command_items', p_item_id, null, to_jsonb(v_item));
  return v_item;
end;
$$;

create or replace function public.mark_command_pending(p_command_id uuid)
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_command public.commands;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para editar comandas.';
  end if;
  select * into v_command from public.commands where id = p_command_id for update;
  if not found then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento') then
    raise exception 'Comanda ja nao pode ser marcada como fiado.';
  end if;
  if not exists (select 1 from public.command_items where command_id = p_command_id) then
    raise exception 'Adicione ao menos um item antes.';
  end if;

  update public.products p
  set stock_quantity = p.stock_quantity - ci.qty
  from (
    select product_id, sum(quantity) qty
    from public.command_items
    where command_id = p_command_id and product_id is not null
    group by product_id
  ) ci
  where p.id = ci.product_id and p.track_stock = true;

  update public.commands
  set status = 'fiado', closed_at = now(), closed_by = auth.uid(), version = version + 1
  where id = p_command_id
  returning * into v_command;

  perform public.add_audit_log('marked_pending', 'commands', p_command_id, null, to_jsonb(v_command));
  return v_command;
end;
$$;

create or replace function public.cancel_command_with_reason(p_command_id uuid, p_reason text default '')
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_command public.commands;
  v_reason text := nullif(left(trim(coalesce(p_reason, '')), 500), '');
  v_item_count integer;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para cancelar comandas.';
  end if;
  select * into v_command from public.commands where id = p_command_id for update;
  if not found then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento', 'fiado') then
    raise exception 'Esta comanda nao pode ser cancelada.';
  end if;

  select count(*) into v_item_count from public.command_items where command_id = p_command_id;
  if v_item_count > 0 and (v_reason is null or char_length(v_reason) < 5) then
    raise exception 'Informe uma justificativa de ao menos 5 caracteres para cancelar uma comanda com itens.';
  end if;

  if v_command.status = 'fiado' then
    update public.products p
    set stock_quantity = p.stock_quantity + ci.qty
    from (
      select product_id, sum(quantity) qty
      from public.command_items
      where command_id = p_command_id and product_id is not null
      group by product_id
    ) ci
    where p.id = ci.product_id and p.track_stock = true;
  end if;

  update public.commands
  set status = 'cancelada', closed_at = now(), closed_by = auth.uid(), version = version + 1
  where id = p_command_id
  returning * into v_command;

  perform public.add_audit_log(
    'cancelled',
    'commands',
    p_command_id,
    null,
    jsonb_build_object('command', to_jsonb(v_command), 'reason', v_reason)
  );
  return v_command;
end;
$$;

create or replace function public.cancel_command(p_command_id uuid)
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
begin
  return public.cancel_command_with_reason(p_command_id, '');
end;
$$;

create or replace function public.open_cash_session(p_opening_amount numeric, p_notes text default '')
returns public.cash_sessions
language plpgsql
security definer
set search_path = public
as $$
declare
  v_session public.cash_sessions;
begin
  if not public.can_manage_money() then
    raise exception 'Seu perfil nao tem permissao para abrir caixa.';
  end if;
  if p_opening_amount is null or p_opening_amount < 0 then
    raise exception 'O fundo inicial nao pode ser negativo.';
  end if;

  insert into public.cash_sessions (opened_by, opening_amount, open_notes)
  values (auth.uid(), p_opening_amount, nullif(trim(p_notes), ''))
  returning * into v_session;

  perform public.add_audit_log('opened', 'cash_sessions', v_session.id, null, to_jsonb(v_session));
  return v_session;
exception
  when unique_violation then
    raise exception 'Ja existe um caixa aberto.';
end;
$$;

create or replace function public.add_cash_movement(p_cash_session_id uuid, p_type text, p_amount numeric, p_reason text default '')
returns public.cash_movements
language plpgsql
security definer
set search_path = public
as $$
declare
  v_session public.cash_sessions;
  v_movement public.cash_movements;
begin
  if not public.can_manage_money() then
    raise exception 'Seu perfil nao tem permissao para movimentar caixa.';
  end if;
  if p_type not in ('sangria', 'reforco') then raise exception 'Tipo de movimentacao invalido.'; end if;
  if p_amount is null or p_amount <= 0 then raise exception 'O valor deve ser maior que zero.'; end if;

  select * into v_session from public.cash_sessions where id = p_cash_session_id and status = 'aberto' for update;
  if not found then raise exception 'Caixa nao esta aberto.'; end if;

  insert into public.cash_movements (cash_session_id, type, amount, reason, created_by)
  values (p_cash_session_id, p_type, p_amount, nullif(trim(p_reason), ''), auth.uid())
  returning * into v_movement;

  perform public.add_audit_log(p_type, 'cash_sessions', p_cash_session_id, null, to_jsonb(v_movement));
  return v_movement;
end;
$$;

create or replace function public.finalize_command(p_command_id uuid, p_payments jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_command public.commands;
  v_cash public.cash_sessions;
  v_total numeric(12,2);
  v_payment jsonb;
  v_method text;
  v_amount numeric(12,2);
  v_received numeric(12,2);
  v_change numeric(12,2);
  v_sum numeric(12,2) := 0;
begin
  if not public.can_manage_money() then
    raise exception 'Seu perfil nao tem permissao para finalizar pagamentos.';
  end if;

  select * into v_command from public.commands where id = p_command_id for update;
  if not found then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento', 'fiado') then
    raise exception 'Comanda ja nao pode ser finalizada.';
  end if;

  select * into v_cash from public.cash_sessions where status = 'aberto' order by opened_at desc limit 1 for update;
  if not found then raise exception 'O caixa esta fechado. Abra o caixa antes de finalizar vendas.'; end if;

  if not exists (select 1 from public.command_items where command_id = p_command_id) then
    raise exception 'Adicione ao menos um item antes de finalizar.';
  end if;
  v_total := v_command.total;

  if p_payments is null or jsonb_typeof(p_payments) <> 'array' or jsonb_array_length(p_payments) = 0 then
    raise exception 'Informe ao menos uma forma de pagamento.';
  end if;

  for v_payment in select value from jsonb_array_elements(p_payments)
  loop
    v_method := v_payment->>'method';
    v_amount := (v_payment->>'amount')::numeric;
    if v_method not in ('dinheiro', 'pix', 'debito', 'credito') then
      raise exception 'Forma de pagamento invalida.';
    end if;
    if v_amount is null or v_amount <= 0 then
      raise exception 'O valor de cada pagamento deve ser maior que zero.';
    end if;
    if v_method = 'dinheiro' then
      v_received := coalesce(nullif(v_payment->>'received_amount', '')::numeric, v_amount);
      if v_received < v_amount then
        raise exception 'O valor recebido em dinheiro nao pode ser menor que o valor atribuido.';
      end if;
    end if;
    v_sum := v_sum + v_amount;
  end loop;

  if abs(v_sum - v_total) > 0.01 then
    raise exception 'A soma dos pagamentos precisa bater com o total da comanda.';
  end if;

  delete from public.payments where command_id = p_command_id;

  for v_payment in select value from jsonb_array_elements(p_payments)
  loop
    v_method := v_payment->>'method';
    v_amount := round((v_payment->>'amount')::numeric, 2);
    v_received := null;
    v_change := null;
    if v_method = 'dinheiro' then
      v_received := coalesce(nullif(v_payment->>'received_amount', '')::numeric, v_amount);
      v_change := round(v_received - v_amount, 2);
    end if;
    insert into public.payments (
      command_id, cash_session_id, method, amount, received_amount, change_amount, pix_confirmed, created_by
    )
    values (
      p_command_id, v_cash.id, v_method, v_amount, v_received, v_change,
      case when v_method = 'pix' then coalesce((v_payment->>'pix_confirmed')::boolean, true) else false end,
      auth.uid()
    );
  end loop;

  if v_command.status <> 'fiado' then
    update public.products p
    set stock_quantity = p.stock_quantity - ci.qty
    from (
      select product_id, sum(quantity) qty
      from public.command_items
      where command_id = p_command_id and product_id is not null
      group by product_id
    ) ci
    where p.id = ci.product_id and p.track_stock = true;
  end if;

  update public.commands
  set status = 'paga',
      cash_session_id = v_cash.id,
      closed_at = now(),
      closed_by = auth.uid(),
      version = version + 1
  where id = p_command_id
  returning * into v_command;

  perform public.add_audit_log('paid', 'commands', p_command_id, null, jsonb_build_object('total', v_total, 'payments', p_payments));
  return jsonb_build_object('total', v_total, 'cash_session_id', v_cash.id, 'command', to_jsonb(v_command));
end;
$$;

create or replace function public.get_cash_summary(p_cash_session_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_session public.cash_sessions;
  v_total_vendido numeric(12,2) := 0;
  v_reforcos numeric(12,2) := 0;
  v_sangrias numeric(12,2) := 0;
  v_raw_money numeric(12,2) := 0;
  v_change numeric(12,2) := 0;
  v_expected numeric(12,2) := 0;
  v_buckets jsonb;
  v_counts jsonb;
  v_qtd_pagas integer := 0;
  v_qtd_abertas integer := 0;
  v_qtd_canceladas integer := 0;
  v_qtd_pendentes integer := 0;
  v_top_products jsonb;
  v_users jsonb;
begin
  if not public.can_manage_money() and not public.is_admin() then
    raise exception 'Seu perfil nao tem permissao para ver o caixa.';
  end if;

  select * into v_session from public.cash_sessions where id = p_cash_session_id;
  if not found then raise exception 'Caixa nao encontrado.'; end if;

  select coalesce(sum(total), 0), count(*)
  into v_total_vendido, v_qtd_pagas
  from public.commands
  where cash_session_id = p_cash_session_id and status = 'paga';

  select
    coalesce(sum(amount) filter (where type = 'reforco'), 0),
    coalesce(sum(amount) filter (where type = 'sangria'), 0)
  into v_reforcos, v_sangrias
  from public.cash_movements
  where cash_session_id = p_cash_session_id;

  with paid as (
    select c.id, c.total
    from public.commands c
    where c.cash_session_id = p_cash_session_id and c.status = 'paga'
  ),
  methods as (
    select command_id, count(distinct method) method_count, min(method) method
    from public.payments
    where cash_session_id = p_cash_session_id
    group by command_id
  ),
  buckets as (
    select case when m.method_count > 1 then 'misto' else m.method end bucket,
           sum(p.total) total,
           count(*) qtd
    from paid p join methods m on m.command_id = p.id
    group by 1
  )
  select
    jsonb_build_object(
      'dinheiro', coalesce(sum(total) filter (where bucket = 'dinheiro'), 0),
      'pix', coalesce(sum(total) filter (where bucket = 'pix'), 0),
      'debito', coalesce(sum(total) filter (where bucket = 'debito'), 0),
      'credito', coalesce(sum(total) filter (where bucket = 'credito'), 0),
      'misto', coalesce(sum(total) filter (where bucket = 'misto'), 0)
    ),
    jsonb_build_object(
      'dinheiro', coalesce(sum(qtd) filter (where bucket = 'dinheiro'), 0),
      'pix', coalesce(sum(qtd) filter (where bucket = 'pix'), 0),
      'debito', coalesce(sum(qtd) filter (where bucket = 'debito'), 0),
      'credito', coalesce(sum(qtd) filter (where bucket = 'credito'), 0),
      'misto', coalesce(sum(qtd) filter (where bucket = 'misto'), 0)
    )
  into v_buckets, v_counts
  from buckets;

  select
    coalesce(sum(coalesce(received_amount, amount)) filter (where method = 'dinheiro'), 0),
    coalesce(sum(coalesce(change_amount, 0)) filter (where method = 'dinheiro'), 0)
  into v_raw_money, v_change
  from public.payments
  where cash_session_id = p_cash_session_id;

  select count(*) into v_qtd_abertas
  from public.commands
  where status in ('aberto', 'aguardando_pagamento');

  select count(*) into v_qtd_pendentes
  from public.commands
  where status = 'fiado';

  select count(*) into v_qtd_canceladas
  from public.commands
  where status = 'cancelada'
    and opened_at >= v_session.opened_at
    and (v_session.closed_at is null or opened_at <= v_session.closed_at);

  select coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
  into v_top_products
  from (
    select ci.product_name, sum(ci.quantity) quantity, sum(ci.subtotal) total
    from public.command_items ci
    join public.commands c on c.id = ci.command_id
    where c.cash_session_id = p_cash_session_id and c.status = 'paga'
    group by ci.product_name
    order by sum(ci.quantity) desc
    limit 10
  ) t;

  select coalesce(jsonb_agg(row_to_json(u)), '[]'::jsonb)
  into v_users
  from (
    select coalesce(p.username, 'sem usuario') username, count(*) sales_count, coalesce(sum(c.total), 0) total
    from public.commands c
    left join public.profiles p on p.id = c.closed_by
    where c.cash_session_id = p_cash_session_id and c.status = 'paga'
    group by p.username
    order by coalesce(sum(c.total), 0) desc
  ) u;

  v_expected := v_session.opening_amount + v_reforcos - v_sangrias + v_raw_money - v_change;

  return jsonb_build_object(
    'session', to_jsonb(v_session),
    'opening_amount', v_session.opening_amount,
    'reforcos', v_reforcos,
    'sangrias', v_sangrias,
    'total_vendido', v_total_vendido,
    'por_forma', coalesce(v_buckets, '{"dinheiro":0,"pix":0,"debito":0,"credito":0,"misto":0}'::jsonb),
    'qtd_por_forma', coalesce(v_counts, '{"dinheiro":0,"pix":0,"debito":0,"credito":0,"misto":0}'::jsonb),
    'qtd_pagas', v_qtd_pagas,
    'qtd_abertas', v_qtd_abertas,
    'qtd_canceladas', v_qtd_canceladas,
    'qtd_pendentes', v_qtd_pendentes,
    'produtos_mais_vendidos', v_top_products,
    'usuarios_vendedores', v_users,
    'dinheiro_recebido_bruto', v_raw_money,
    'troco_total', v_change,
    'dinheiro_esperado', v_expected
  );
end;
$$;

create or replace function public.close_cash_session(p_cash_session_id uuid, p_counted_amount numeric, p_close_notes text default '', p_force boolean default false)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_session public.cash_sessions;
  v_summary jsonb;
  v_expected numeric(12,2);
  v_open_count integer;
begin
  if not public.is_admin() then
    raise exception 'Somente administrador pode fechar caixa.';
  end if;

  select * into v_session from public.cash_sessions where id = p_cash_session_id and status = 'aberto' for update;
  if not found then raise exception 'Este caixa ja esta fechado ou nao existe.'; end if;

  select count(*) into v_open_count from public.commands where status in ('aberto', 'aguardando_pagamento');
  if v_open_count > 0 and not p_force then
    raise exception 'Existem comandas em aberto. Finalize ou cancele antes de fechar.';
  end if;

  v_summary := public.get_cash_summary(p_cash_session_id);
  v_expected := (v_summary->>'dinheiro_esperado')::numeric;

  update public.cash_sessions
  set status = 'fechado',
      closed_by = auth.uid(),
      closed_at = now(),
      counted_amount = p_counted_amount,
      expected_cash = v_expected,
      difference = round(p_counted_amount - v_expected, 2),
      close_notes = nullif(trim(p_close_notes), '')
  where id = p_cash_session_id
  returning * into v_session;

  perform public.add_audit_log('closed', 'cash_sessions', p_cash_session_id, null, to_jsonb(v_session));
  return public.get_cash_summary(p_cash_session_id) || jsonb_build_object('closed_session', to_jsonb(v_session));
end;
$$;

create or replace function public.get_dashboard_summary()
returns jsonb
language sql
security definer
set search_path = public
as $$
  with today_paid as (
    select c.*
    from public.commands c
    where c.status = 'paga'
      and (c.closed_at at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date
  ),
  pay as (
    select p.method, sum(p.amount) total
    from public.payments p
    join today_paid c on c.id = p.command_id
    group by p.method
  )
  select jsonb_build_object(
    'cash_open', exists(select 1 from public.cash_sessions where status = 'aberto'),
    'session', (select to_jsonb(cs) from public.cash_sessions cs where status = 'aberto' order by opened_at desc limit 1),
    'total_vendido_hoje', coalesce((select sum(total) from today_paid), 0),
    'qtd_abertas', (select count(*) from public.commands where status in ('aberto','aguardando_pagamento')),
    'qtd_finalizadas_hoje', (select count(*) from today_paid),
    'qtd_pendentes_hoje', (
      select count(*) from public.commands
      where status = 'fiado'
        and (opened_at at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date
    ),
    'total_dinheiro', coalesce((select total from pay where method = 'dinheiro'), 0),
    'total_pix', coalesce((select total from pay where method = 'pix'), 0),
    'total_cartao', coalesce((select sum(total) from pay where method in ('debito','credito')), 0)
  )
$$;

alter table public.profiles enable row level security;
alter table public.settings enable row level security;
alter table public.categories enable row level security;
alter table public.products enable row level security;
alter table public.command_counters enable row level security;
alter table public.cash_sessions enable row level security;
alter table public.commands enable row level security;
alter table public.command_items enable row level security;
alter table public.payments enable row level security;
alter table public.cash_movements enable row level security;
alter table public.audit_logs enable row level security;

drop policy if exists "profiles readable by authenticated" on public.profiles;
create policy "profiles readable by authenticated" on public.profiles
for select to authenticated using (true);

drop policy if exists "profiles admin update" on public.profiles;
create policy "profiles admin update" on public.profiles
for update to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists "settings readable" on public.settings;
create policy "settings readable" on public.settings
for select to authenticated using (true);

drop policy if exists "settings admin write" on public.settings;
create policy "settings admin write" on public.settings
for all to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists "categories readable" on public.categories;
create policy "categories readable" on public.categories
for select to authenticated using (true);

drop policy if exists "categories admin write" on public.categories;
create policy "categories admin write" on public.categories
for all to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists "products readable" on public.products;
create policy "products readable" on public.products
for select to authenticated using (true);

drop policy if exists "products admin write" on public.products;
create policy "products admin write" on public.products
for all to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists "commands readable" on public.commands;
create policy "commands readable" on public.commands
for select to authenticated using (true);

drop policy if exists "command_items readable" on public.command_items;
create policy "command_items readable" on public.command_items
for select to authenticated using (true);

drop policy if exists "payments money readable" on public.payments;
create policy "payments money readable" on public.payments
for select to authenticated using (public.can_manage_money() or public.is_admin());

drop policy if exists "cash_sessions readable" on public.cash_sessions;
create policy "cash_sessions readable" on public.cash_sessions
for select to authenticated using (true);

drop policy if exists "cash_movements money readable" on public.cash_movements;
create policy "cash_movements money readable" on public.cash_movements
for select to authenticated using (public.can_manage_money() or public.is_admin());

drop policy if exists "audit admin readable" on public.audit_logs;
create policy "audit admin readable" on public.audit_logs
for select to authenticated using (public.is_admin());

-- Funcoes SECURITY DEFINER nao devem herdar EXECUTE de PUBLIC. O frontend
-- recebe acesso apenas aos helpers de autorizacao e RPCs que possuem suas
-- proprias validacoes de perfil. Funcoes internas continuam privadas.
do $$
declare
  fn regprocedure;
begin
  for fn in
    select p.oid::regprocedure
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = any(array[
        'touch_updated_at', 'handle_new_auth_user', 'current_profile',
        'current_role', 'is_admin', 'can_manage_money', 'can_edit_orders',
        'add_audit_log', 'recalculate_command_totals', 'create_command',
        'add_command_item', 'update_command_item_quantity',
        'remove_command_item', 'set_command_discount', 'update_command_info',
        'update_item_kitchen_status', 'mark_command_pending', 'cancel_command', 'cancel_command_with_reason',
        'open_cash_session', 'add_cash_movement', 'finalize_command',
        'get_cash_summary', 'close_cash_session', 'get_dashboard_summary'
      ])
  loop
    execute format('revoke execute on function %s from public, anon', fn);
  end loop;

  for fn in
    select p.oid::regprocedure
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = any(array[
        'current_profile', 'current_role', 'is_admin', 'can_manage_money',
        'can_edit_orders', 'create_command', 'add_command_item',
        'update_command_item_quantity', 'remove_command_item',
        'set_command_discount', 'update_command_info',
        'update_item_kitchen_status', 'mark_command_pending', 'cancel_command', 'cancel_command_with_reason',
        'open_cash_session', 'add_cash_movement', 'finalize_command',
        'get_cash_summary', 'close_cash_session', 'get_dashboard_summary'
      ])
  loop
    execute format('grant execute on function %s to authenticated', fn);
  end loop;
end
$$;

insert into public.settings (key, value)
values
  ('establishment_name', 'PDV Espetinhos'),
  ('pix_key', ''),
  ('pix_receiver_name', 'PDV ESPETINHOS'),
  ('pix_city', 'SAO PAULO'),
  ('pix_description', 'Pagamento PDV Espetinhos'),
  ('theme', 'light')
on conflict (key) do nothing;

insert into public.categories (name)
values ('Espetinhos'), ('Bebidas'), ('Marmitas'), ('Porcoes'), ('Adicionais')
on conflict (name) do nothing;

insert into public.products (name, category_id, price, cost, track_stock, stock_quantity)
select item.name, c.id, item.price, item.cost, item.track_stock, item.stock_quantity
from (
  values
    ('Espetinho de vaca', 'Espetinhos', 8.00::numeric, 4.00::numeric, true, 40::numeric),
    ('Espetinho de frango', 'Espetinhos', 7.00::numeric, 3.50::numeric, true, 40::numeric),
    ('Espetinho de coracao', 'Espetinhos', 7.50::numeric, 3.50::numeric, true, 30::numeric),
    ('Coca-Cola lata', 'Bebidas', 6.00::numeric, 3.20::numeric, true, 30::numeric),
    ('Guarana lata', 'Bebidas', 6.00::numeric, 3.20::numeric, true, 30::numeric),
    ('Agua', 'Bebidas', 3.00::numeric, 1.00::numeric, true, 40::numeric),
    ('Marmita do dia', 'Marmitas', 18.00::numeric, 9.00::numeric, true, 15::numeric),
    ('Porcao de mandioca', 'Porcoes', 15.00::numeric, 6.00::numeric, true, 20::numeric),
    ('Vinagrete extra', 'Adicionais', 2.00::numeric, 0.50::numeric, false, 0::numeric)
) as item(name, category_name, price, cost, track_stock, stock_quantity)
join public.categories c on c.name = item.category_name
where not exists (select 1 from public.products p where p.name = item.name);

do $$
declare
  t text;
begin
  foreach t in array array[
    'settings', 'categories', 'products', 'cash_sessions', 'commands',
    'command_items', 'payments', 'cash_movements', 'profiles'
  ]
  loop
    if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
       and not exists (
         select 1
         from pg_publication_tables
         where pubname = 'supabase_realtime'
           and schemaname = 'public'
           and tablename = t
       )
    then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;
