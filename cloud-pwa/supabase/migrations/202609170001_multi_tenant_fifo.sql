-- Migracao aditiva: isolamento multiestabelecimento e fila FIFO.
-- Preserva os dados atuais e os associa ao estabelecimento Du Dair.

begin;

create table if not exists public.establishments (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  active boolean not null default true,
  logo_url text,
  primary_color text not null default '#e67e22',
  secondary_color text not null default '#ca6f1e',
  accent_color text not null default '#f1c40f',
  background_color text not null default '#1a1310',
  contact_phone text,
  contact_email text,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint establishments_slug_format check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  constraint establishments_colors_format check (
    primary_color ~ '^#[0-9a-fA-F]{6}$' and
    secondary_color ~ '^#[0-9a-fA-F]{6}$' and
    accent_color ~ '^#[0-9a-fA-F]{6}$' and
    background_color ~ '^#[0-9a-fA-F]{6}$'
  )
);

insert into public.establishments (slug, name)
values
  ('du-dair', 'Du Dair'),
  ('espetinho-do-ronaldo', 'Espetinho do Ronaldo')
on conflict (slug) do update set name = excluded.name;

alter table public.profiles add column if not exists establishment_id uuid references public.establishments(id);
alter table public.profiles add column if not exists platform_role text not null default 'member';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'profiles_platform_role_check'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_platform_role_check
      check (platform_role in ('member', 'super_admin'));
  end if;
end $$;

update public.profiles
set establishment_id = (select id from public.establishments where slug = 'du-dair')
where establishment_id is null;

update public.profiles
set platform_role = 'super_admin'
where username = 'admin';

alter table public.settings add column if not exists establishment_id uuid references public.establishments(id);
alter table public.categories add column if not exists establishment_id uuid references public.establishments(id);
alter table public.products add column if not exists establishment_id uuid references public.establishments(id);
alter table public.command_counters add column if not exists establishment_id uuid references public.establishments(id);
alter table public.cash_sessions add column if not exists establishment_id uuid references public.establishments(id);
alter table public.commands add column if not exists establishment_id uuid references public.establishments(id);
alter table public.command_items add column if not exists establishment_id uuid references public.establishments(id);
alter table public.payments add column if not exists establishment_id uuid references public.establishments(id);
alter table public.cash_movements add column if not exists establishment_id uuid references public.establishments(id);
alter table public.audit_logs add column if not exists establishment_id uuid references public.establishments(id);

update public.settings set establishment_id = e.id
from public.establishments e where e.slug = 'du-dair' and public.settings.establishment_id is null;
update public.categories set establishment_id = e.id
from public.establishments e where e.slug = 'du-dair' and public.categories.establishment_id is null;
update public.products set establishment_id = e.id
from public.establishments e where e.slug = 'du-dair' and public.products.establishment_id is null;
update public.command_counters set establishment_id = e.id
from public.establishments e where e.slug = 'du-dair' and public.command_counters.establishment_id is null;
update public.cash_sessions set establishment_id = e.id
from public.establishments e where e.slug = 'du-dair' and public.cash_sessions.establishment_id is null;
update public.commands set establishment_id = e.id
from public.establishments e where e.slug = 'du-dair' and public.commands.establishment_id is null;
update public.command_items ci set establishment_id = c.establishment_id
from public.commands c where c.id = ci.command_id and ci.establishment_id is null;
update public.payments p set establishment_id = c.establishment_id
from public.commands c where c.id = p.command_id and p.establishment_id is null;
update public.cash_movements cm set establishment_id = cs.establishment_id
from public.cash_sessions cs where cs.id = cm.cash_session_id and cm.establishment_id is null;
update public.audit_logs set establishment_id = e.id
from public.establishments e where e.slug = 'du-dair' and public.audit_logs.establishment_id is null;

alter table public.settings alter column establishment_id set not null;
alter table public.categories alter column establishment_id set not null;
alter table public.products alter column establishment_id set not null;
alter table public.command_counters alter column establishment_id set not null;
alter table public.cash_sessions alter column establishment_id set not null;
alter table public.commands alter column establishment_id set not null;
alter table public.command_items alter column establishment_id set not null;
alter table public.payments alter column establishment_id set not null;
alter table public.cash_movements alter column establishment_id set not null;
alter table public.audit_logs alter column establishment_id set not null;

alter table public.settings drop constraint if exists settings_pkey;
alter table public.settings add constraint settings_pkey primary key (establishment_id, key);
alter table public.categories drop constraint if exists categories_name_key;
alter table public.categories add constraint categories_establishment_name_key unique (establishment_id, name);
alter table public.command_counters drop constraint if exists command_counters_pkey;
alter table public.command_counters add constraint command_counters_pkey primary key (establishment_id, business_date);
alter table public.commands drop constraint if exists commands_business_date_number_key;
alter table public.commands add constraint commands_establishment_date_number_key unique (establishment_id, business_date, number);
drop index if exists public.only_one_open_cash_session;
create unique index only_one_open_cash_session_per_establishment
  on public.cash_sessions (establishment_id)
  where status = 'aberto';

create index if not exists profiles_establishment_id_idx on public.profiles (establishment_id);
create index if not exists settings_establishment_id_idx on public.settings (establishment_id);
create index if not exists categories_establishment_id_idx on public.categories (establishment_id);
create index if not exists products_establishment_active_name_idx on public.products (establishment_id, active, name);
create index if not exists products_category_id_idx on public.products (category_id);
create index if not exists cash_sessions_establishment_status_idx on public.cash_sessions (establishment_id, status, opened_at desc);
create index if not exists commands_establishment_status_opened_idx on public.commands (establishment_id, status, opened_at desc);
create index if not exists commands_created_by_idx on public.commands (created_by);
create index if not exists command_items_command_id_idx on public.command_items (command_id);
create index if not exists command_items_product_id_idx on public.command_items (product_id);
create index if not exists payments_command_id_idx on public.payments (command_id);
create index if not exists payments_cash_session_id_idx on public.payments (cash_session_id);
create index if not exists cash_movements_cash_session_id_idx on public.cash_movements (cash_session_id);
create index if not exists audit_logs_establishment_created_idx on public.audit_logs (establishment_id, created_at desc);

create table if not exists public.service_queue (
  id bigint generated always as identity primary key,
  establishment_id uuid not null references public.establishments(id),
  command_id uuid not null references public.commands(id) on delete cascade,
  request_type text not null check (request_type in ('pedido_digital', 'chamar_garcom', 'solicitar_fechamento')),
  status text not null default 'pendente' check (status in ('pendente', 'em_atendimento', 'concluido', 'cancelado')),
  payload jsonb not null default '{}'::jsonb,
  idempotency_key text,
  requested_at timestamptz not null default now(),
  claimed_at timestamptz,
  completed_at timestamptz,
  claimed_by uuid references public.profiles(id),
  completed_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists service_queue_tenant_idempotency_key
  on public.service_queue (establishment_id, idempotency_key)
  where idempotency_key is not null;
create index if not exists service_queue_fifo_pending_idx
  on public.service_queue (establishment_id, requested_at, id)
  where status = 'pendente';
create index if not exists service_queue_command_id_idx on public.service_queue (command_id);

create trigger trg_establishments_updated_at before update on public.establishments
for each row execute function public.touch_updated_at();
create trigger trg_service_queue_updated_at before update on public.service_queue
for each row execute function public.touch_updated_at();

create or replace function public.current_establishment_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select p.establishment_id
  from public.profiles p
  join public.establishments e on e.id = p.establishment_id and e.active = true
  where p.id = (select auth.uid()) and p.active = true
  limit 1
$$;

create or replace function public.is_super_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(exists (
    select 1 from public.profiles p
    where p.id = (select auth.uid())
      and p.active = true
      and p.platform_role = 'super_admin'
  ), false)
$$;

create or replace function public.enforce_tenant_scope()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_establishment_id uuid;
begin
  if (select auth.uid()) is null then
    return case when tg_op = 'DELETE' then old else new end;
  end if;

  v_establishment_id := public.current_establishment_id();
  if v_establishment_id is null then
    raise exception 'Usuario sem estabelecimento ativo.';
  end if;

  if tg_op = 'DELETE' then
    if old.establishment_id <> v_establishment_id then
      raise exception 'Operacao bloqueada: estabelecimento incorreto.';
    end if;
    return old;
  end if;

  if tg_op = 'INSERT' and new.establishment_id is null then
    new.establishment_id := v_establishment_id;
  end if;
  if new.establishment_id <> v_establishment_id then
    raise exception 'Operacao bloqueada: estabelecimento incorreto.';
  end if;
  if tg_op = 'UPDATE' and old.establishment_id <> new.establishment_id then
    raise exception 'Nao e permitido transferir dados entre estabelecimentos.';
  end if;
  return new;
end;
$$;

do $$
declare
  t text;
begin
  foreach t in array array[
    'settings', 'categories', 'products', 'command_counters', 'cash_sessions',
    'commands', 'command_items', 'payments', 'cash_movements', 'audit_logs', 'service_queue'
  ]
  loop
    execute format('drop trigger if exists trg_tenant_scope on public.%I', t);
    execute format(
      'create trigger trg_tenant_scope before insert or update or delete on public.%I for each row execute function public.enforce_tenant_scope()',
      t
    );
  end loop;
end $$;

create or replace function public.validate_tenant_relationships()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_parent_establishment_id uuid;
begin
  if tg_table_name = 'command_items' then
    select establishment_id into v_parent_establishment_id from public.commands where id = new.command_id;
    if new.establishment_id is null then new.establishment_id := v_parent_establishment_id; end if;
    if v_parent_establishment_id is distinct from new.establishment_id then
      raise exception 'Item e comanda pertencem a estabelecimentos diferentes.';
    end if;
    if new.product_id is not null and not exists (
      select 1 from public.products p where p.id = new.product_id and p.establishment_id = new.establishment_id
    ) then
      raise exception 'Produto nao pertence ao estabelecimento da comanda.';
    end if;
  elsif tg_table_name = 'payments' then
    if new.establishment_id is null then
      select establishment_id into v_parent_establishment_id from public.commands where id = new.command_id;
      new.establishment_id := v_parent_establishment_id;
    end if;
    if not exists (
      select 1 from public.commands c where c.id = new.command_id and c.establishment_id = new.establishment_id
    ) or not exists (
      select 1 from public.cash_sessions cs where cs.id = new.cash_session_id and cs.establishment_id = new.establishment_id
    ) then
      raise exception 'Pagamento, comanda e caixa precisam pertencer ao mesmo estabelecimento.';
    end if;
  elsif tg_table_name = 'cash_movements' then
    if new.establishment_id is null then
      select establishment_id into v_parent_establishment_id from public.cash_sessions where id = new.cash_session_id;
      new.establishment_id := v_parent_establishment_id;
    end if;
    if not exists (
      select 1 from public.cash_sessions cs where cs.id = new.cash_session_id and cs.establishment_id = new.establishment_id
    ) then
      raise exception 'Movimento e caixa pertencem a estabelecimentos diferentes.';
    end if;
  elsif tg_table_name = 'service_queue' then
    if new.establishment_id is null then
      select establishment_id into v_parent_establishment_id from public.commands where id = new.command_id;
      new.establishment_id := v_parent_establishment_id;
    end if;
    if not exists (
      select 1 from public.commands c where c.id = new.command_id and c.establishment_id = new.establishment_id
    ) then
      raise exception 'Solicitacao e comanda pertencem a estabelecimentos diferentes.';
    end if;
  end if;
  return new;
end;
$$;

create trigger trg_command_items_tenant_parent before insert or update on public.command_items
for each row execute function public.validate_tenant_relationships();
create trigger trg_payments_tenant_parent before insert or update on public.payments
for each row execute function public.validate_tenant_relationships();
create trigger trg_cash_movements_tenant_parent before insert or update on public.cash_movements
for each row execute function public.validate_tenant_relationships();
create trigger trg_service_queue_tenant_parent before insert or update on public.service_queue
for each row execute function public.validate_tenant_relationships();

create or replace function public.protect_establishment_identity()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if (select auth.uid()) is not null and not public.is_super_admin() then
    if new.slug is distinct from old.slug or new.active is distinct from old.active then
      raise exception 'Somente o Super Admin pode alterar slug ou status do estabelecimento.';
    end if;
  end if;
  return new;
end;
$$;

create trigger trg_protect_establishment_identity before update on public.establishments
for each row execute function public.protect_establishment_identity();

create or replace function public.close_command_queue()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.status in ('aberto', 'aguardando_pagamento')
     and new.status not in ('aberto', 'aguardando_pagamento') then
    update public.service_queue
    set status = 'cancelado', completed_at = now(), completed_by = (select auth.uid())
    where command_id = new.id and establishment_id = new.establishment_id
      and status in ('pendente', 'em_atendimento');
  end if;
  return new;
end;
$$;

create trigger trg_close_command_queue after update of status on public.commands
for each row execute function public.close_command_queue();

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, username, full_name, role, active)
  values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data->>'username', ''), split_part(new.email, '@', 1)),
    nullif(new.raw_user_meta_data->>'full_name', ''),
    'atendente',
    false
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create or replace function public.add_audit_log(
  p_action text,
  p_entity text,
  p_entity_id uuid,
  p_old jsonb default null,
  p_new jsonb default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_establishment_id uuid := public.current_establishment_id();
begin
  if v_establishment_id is null then
    raise exception 'Usuario sem estabelecimento ativo.';
  end if;
  insert into public.audit_logs (establishment_id, user_id, action, entity, entity_id, old_value, new_value)
  values (v_establishment_id, (select auth.uid()), p_action, p_entity, p_entity_id, p_old, p_new);
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
  v_establishment_id uuid := public.current_establishment_id();
  v_date date := (now() at time zone 'America/Sao_Paulo')::date;
  v_number integer;
  v_command public.commands;
begin
  if not public.can_edit_orders() or v_establishment_id is null then
    raise exception 'Seu perfil nao tem permissao para criar comandas.';
  end if;

  insert into public.command_counters (establishment_id, business_date, last_number)
  values (v_establishment_id, v_date, 1)
  on conflict (establishment_id, business_date)
  do update set last_number = public.command_counters.last_number + 1
  returning last_number into v_number;

  insert into public.commands (establishment_id, business_date, number, customer_name, table_ref, created_by)
  values (v_establishment_id, v_date, v_number, nullif(trim(p_customer_name), ''), nullif(trim(p_table_ref), ''), (select auth.uid()))
  returning * into v_command;

  perform public.add_audit_log('created', 'commands', v_command.id, null, to_jsonb(v_command));
  return v_command;
end;
$$;

create or replace function public.enqueue_service_request(
  p_command_id uuid,
  p_request_type text,
  p_payload jsonb default '{}'::jsonb,
  p_idempotency_key text default null
)
returns public.service_queue
language plpgsql
security definer
set search_path = public
as $$
declare
  v_command public.commands;
  v_request public.service_queue;
begin
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

  insert into public.service_queue (
    establishment_id, command_id, request_type, payload, idempotency_key
  ) values (
    v_command.establishment_id, v_command.id, p_request_type,
    coalesce(p_payload, '{}'::jsonb), nullif(trim(p_idempotency_key), '')
  )
  on conflict (establishment_id, idempotency_key) where idempotency_key is not null
  do update set idempotency_key = excluded.idempotency_key
  returning * into v_request;

  perform public.add_audit_log('queued', 'service_queue', null, null, to_jsonb(v_request));
  return v_request;
end;
$$;

create or replace function public.claim_next_service_request()
returns public.service_queue
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request public.service_queue;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para atender a fila.';
  end if;

  update public.service_queue
  set status = 'em_atendimento',
      claimed_at = now(),
      claimed_by = (select auth.uid())
  where id = (
    select q.id
    from public.service_queue q
    where q.establishment_id = public.current_establishment_id()
      and q.status = 'pendente'
    order by q.requested_at asc, q.id asc
    limit 1
    for update skip locked
  )
  returning * into v_request;

  if v_request.id is not null then
    perform public.add_audit_log('claimed', 'service_queue', null, null, to_jsonb(v_request));
  end if;
  return v_request;
end;
$$;

create or replace function public.complete_service_request(p_request_id bigint)
returns public.service_queue
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request public.service_queue;
begin
  if not public.can_edit_orders() then
    raise exception 'Seu perfil nao tem permissao para concluir a fila.';
  end if;
  update public.service_queue
  set status = 'concluido', completed_at = now(), completed_by = (select auth.uid())
  where id = p_request_id
    and establishment_id = public.current_establishment_id()
    and status = 'em_atendimento'
  returning * into v_request;
  if not found then raise exception 'Solicitacao nao encontrada ou ainda nao iniciada.'; end if;
  perform public.add_audit_log('completed', 'service_queue', null, null, to_jsonb(v_request));
  return v_request;
end;
$$;

create or replace function public.finalize_command(p_command_id uuid, p_payments jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_establishment_id uuid := public.current_establishment_id();
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
  if not public.can_manage_money() or v_establishment_id is null then
    raise exception 'Seu perfil nao tem permissao para finalizar pagamentos.';
  end if;

  select * into v_command from public.commands
  where id = p_command_id and establishment_id = v_establishment_id
  for update;
  if not found then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento', 'fiado') then
    raise exception 'Comanda ja nao pode ser finalizada.';
  end if;

  select * into v_cash from public.cash_sessions
  where establishment_id = v_establishment_id and status = 'aberto'
  order by opened_at desc limit 1 for update;
  if not found then raise exception 'O caixa esta fechado. Abra o caixa antes de finalizar vendas.'; end if;

  if not exists (select 1 from public.command_items where command_id = p_command_id and establishment_id = v_establishment_id) then
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

  delete from public.payments where command_id = p_command_id and establishment_id = v_establishment_id;
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
      establishment_id, command_id, cash_session_id, method, amount,
      received_amount, change_amount, pix_confirmed, created_by
    ) values (
      v_establishment_id, p_command_id, v_cash.id, v_method, v_amount,
      v_received, v_change,
      case when v_method = 'pix' then coalesce((v_payment->>'pix_confirmed')::boolean, true) else false end,
      (select auth.uid())
    );
  end loop;

  if v_command.status <> 'fiado' then
    update public.products p
    set stock_quantity = p.stock_quantity - ci.qty
    from (
      select product_id, sum(quantity) qty
      from public.command_items
      where command_id = p_command_id and establishment_id = v_establishment_id and product_id is not null
      group by product_id
    ) ci
    where p.id = ci.product_id and p.establishment_id = v_establishment_id and p.track_stock = true;
  end if;

  update public.commands
  set status = 'paga', cash_session_id = v_cash.id, closed_at = now(),
      closed_by = (select auth.uid()), version = version + 1
  where id = p_command_id and establishment_id = v_establishment_id
  returning * into v_command;

  update public.service_queue
  set status = 'cancelado', completed_at = now(), completed_by = (select auth.uid())
  where command_id = p_command_id and establishment_id = v_establishment_id
    and status in ('pendente', 'em_atendimento');

  perform public.add_audit_log('paid', 'commands', p_command_id, null, jsonb_build_object('total', v_total, 'payments', p_payments));
  return jsonb_build_object('total', v_total, 'cash_session_id', v_cash.id, 'command', to_jsonb(v_command));
end;
$$;

-- Mantem a implementacao detalhada existente, mas adiciona uma barreira de tenant
-- antes de qualquer resumo financeiro ser calculado.
alter function public.get_cash_summary(uuid) rename to get_cash_summary_legacy;
revoke execute on function public.get_cash_summary_legacy(uuid) from public, anon, authenticated;

create or replace function public.get_cash_summary(p_cash_session_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_result jsonb;
  v_establishment_id uuid := public.current_establishment_id();
  v_open integer;
  v_pending integer;
  v_cancelled integer;
  v_session public.cash_sessions;
begin
  if not public.can_manage_money() and not public.is_admin() then
    raise exception 'Seu perfil nao tem permissao para ver o caixa.';
  end if;
  select * into v_session from public.cash_sessions
  where id = p_cash_session_id and establishment_id = v_establishment_id;
  if not found then raise exception 'Caixa nao encontrado.'; end if;

  v_result := public.get_cash_summary_legacy(p_cash_session_id);
  select count(*) into v_open from public.commands
    where establishment_id = v_establishment_id and status in ('aberto', 'aguardando_pagamento');
  select count(*) into v_pending from public.commands
    where establishment_id = v_establishment_id and status = 'fiado';
  select count(*) into v_cancelled from public.commands
    where establishment_id = v_establishment_id and status = 'cancelada'
      and opened_at >= v_session.opened_at
      and (v_session.closed_at is null or opened_at <= v_session.closed_at);

  return v_result || jsonb_build_object(
    'qtd_abertas', v_open,
    'qtd_pendentes', v_pending,
    'qtd_canceladas', v_cancelled
  );
end;
$$;

create or replace function public.close_cash_session(
  p_cash_session_id uuid,
  p_counted_amount numeric,
  p_close_notes text default '',
  p_force boolean default false
)
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
  v_establishment_id uuid := public.current_establishment_id();
begin
  if not public.is_admin() then raise exception 'Somente administrador pode fechar caixa.'; end if;
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
  update public.cash_sessions
  set status = 'fechado', closed_by = (select auth.uid()), closed_at = now(),
      counted_amount = p_counted_amount, expected_cash = v_expected,
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
  with tenant as (
    select public.current_establishment_id() id
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

alter table public.establishments enable row level security;
alter table public.service_queue enable row level security;

drop policy if exists "profiles readable by authenticated" on public.profiles;
drop policy if exists "profiles admin update" on public.profiles;
create policy "profiles tenant read" on public.profiles for select to authenticated
using (
  id = (select auth.uid())
  or establishment_id = (select public.current_establishment_id())
  or (select public.is_super_admin())
);
create policy "profiles tenant admin update" on public.profiles for update to authenticated
using (
  (select public.is_super_admin())
  or (public.is_admin() and establishment_id = (select public.current_establishment_id()))
)
with check (
  (select public.is_super_admin())
  or (public.is_admin() and establishment_id = (select public.current_establishment_id()) and platform_role = 'member')
);

create policy "establishments tenant read" on public.establishments for select to authenticated
using (id = (select public.current_establishment_id()) or (select public.is_super_admin()));
create policy "establishments super insert" on public.establishments for insert to authenticated
with check ((select public.is_super_admin()));
create policy "establishments managed update" on public.establishments for update to authenticated
using (id = (select public.current_establishment_id()) or (select public.is_super_admin()))
with check (id = (select public.current_establishment_id()) or (select public.is_super_admin()));

drop policy if exists "settings readable" on public.settings;
drop policy if exists "settings admin write" on public.settings;
create policy "settings tenant read" on public.settings for select to authenticated
using (establishment_id = (select public.current_establishment_id()));
create policy "settings tenant admin insert" on public.settings for insert to authenticated
with check (public.is_admin() and establishment_id = (select public.current_establishment_id()));
create policy "settings tenant admin update" on public.settings for update to authenticated
using (public.is_admin() and establishment_id = (select public.current_establishment_id()))
with check (public.is_admin() and establishment_id = (select public.current_establishment_id()));

drop policy if exists "categories readable" on public.categories;
drop policy if exists "categories admin write" on public.categories;
create policy "categories tenant read" on public.categories for select to authenticated
using (establishment_id = (select public.current_establishment_id()));
create policy "categories tenant admin insert" on public.categories for insert to authenticated
with check (public.is_admin() and establishment_id = (select public.current_establishment_id()));
create policy "categories tenant admin update" on public.categories for update to authenticated
using (public.is_admin() and establishment_id = (select public.current_establishment_id()))
with check (public.is_admin() and establishment_id = (select public.current_establishment_id()));
create policy "categories tenant admin delete" on public.categories for delete to authenticated
using (public.is_admin() and establishment_id = (select public.current_establishment_id()));

drop policy if exists "products readable" on public.products;
drop policy if exists "products admin write" on public.products;
create policy "products tenant read" on public.products for select to authenticated
using (establishment_id = (select public.current_establishment_id()));
create policy "products tenant admin insert" on public.products for insert to authenticated
with check (public.is_admin() and establishment_id = (select public.current_establishment_id()));
create policy "products tenant admin update" on public.products for update to authenticated
using (public.is_admin() and establishment_id = (select public.current_establishment_id()))
with check (public.is_admin() and establishment_id = (select public.current_establishment_id()));

drop policy if exists "commands readable" on public.commands;
create policy "commands tenant read" on public.commands for select to authenticated
using (establishment_id = (select public.current_establishment_id()));
drop policy if exists "command_items readable" on public.command_items;
create policy "command_items tenant read" on public.command_items for select to authenticated
using (establishment_id = (select public.current_establishment_id()));
drop policy if exists "payments money readable" on public.payments;
create policy "payments tenant money read" on public.payments for select to authenticated
using (establishment_id = (select public.current_establishment_id()) and public.can_manage_money());
drop policy if exists "cash_sessions readable" on public.cash_sessions;
create policy "cash_sessions tenant read" on public.cash_sessions for select to authenticated
using (establishment_id = (select public.current_establishment_id()));
drop policy if exists "cash_movements money readable" on public.cash_movements;
create policy "cash_movements tenant money read" on public.cash_movements for select to authenticated
using (establishment_id = (select public.current_establishment_id()) and public.can_manage_money());
drop policy if exists "audit admin readable" on public.audit_logs;
create policy "audit tenant admin read" on public.audit_logs for select to authenticated
using (establishment_id = (select public.current_establishment_id()) and public.is_admin());
create policy "service_queue tenant read" on public.service_queue for select to authenticated
using (establishment_id = (select public.current_establishment_id()));

revoke all on public.establishments, public.service_queue from anon;
grant select, insert, update on public.establishments to authenticated;
grant select on public.service_queue to authenticated;

revoke execute on function public.current_establishment_id() from public, anon;
revoke execute on function public.is_super_admin() from public, anon;
revoke execute on function public.enforce_tenant_scope() from public, anon, authenticated;
revoke execute on function public.validate_tenant_relationships() from public, anon, authenticated;
revoke execute on function public.protect_establishment_identity() from public, anon, authenticated;
revoke execute on function public.close_command_queue() from public, anon, authenticated;
revoke execute on function public.enqueue_service_request(uuid, text, jsonb, text) from public, anon;
revoke execute on function public.claim_next_service_request() from public, anon;
revoke execute on function public.complete_service_request(bigint) from public, anon;
grant execute on function public.current_establishment_id() to authenticated;
grant execute on function public.is_super_admin() to authenticated;
grant execute on function public.enqueue_service_request(uuid, text, jsonb, text) to authenticated;
grant execute on function public.claim_next_service_request() to authenticated;
grant execute on function public.complete_service_request(bigint) to authenticated;

insert into public.settings (establishment_id, key, value)
select e.id, v.key, v.value
from public.establishments e
cross join (values
  ('establishment_name', 'Espetinho do Ronaldo'),
  ('pix_key', ''),
  ('pix_receiver_name', 'ESPETINHO DO RONALDO'),
  ('pix_city', 'SAO PAULO'),
  ('pix_description', 'Pagamento Espetinho do Ronaldo'),
  ('theme', 'dark')
) as v(key, value)
where e.slug = 'espetinho-do-ronaldo'
on conflict (establishment_id, key) do nothing;

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (
       select 1 from pg_publication_tables
       where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'service_queue'
     )
  then
    alter publication supabase_realtime add table public.service_queue;
  end if;
end $$;

commit;
