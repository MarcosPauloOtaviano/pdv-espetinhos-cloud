-- Cancelamentos de comandas com itens exigem uma justificativa auditável.
-- Comandas vazias continuam podendo ser canceladas sem justificativa para não
-- poluir o histórico com rascunhos abandonados.

create or replace function public.cancel_command_with_reason(p_command_id uuid, p_reason text default '')
returns public.commands
language plpgsql
security definer
set search_path = public
as $$
declare
  v_command public.commands;
  v_establishment_id uuid := public.current_establishment_id();
  v_reason text := nullif(left(trim(coalesce(p_reason, '')), 500), '');
  v_item_count integer;
begin
  if not public.can_edit_orders() or v_establishment_id is null then
    raise exception 'Seu perfil nao tem permissao para cancelar comandas.';
  end if;

  select * into v_command
  from public.commands
  where id = p_command_id and establishment_id = v_establishment_id
  for update;
  if not found then raise exception 'Comanda nao encontrada.'; end if;
  if v_command.status not in ('aberto', 'aguardando_pagamento', 'fiado') then
    raise exception 'Esta comanda nao pode ser cancelada.';
  end if;

  select count(*) into v_item_count
  from public.command_items
  where command_id = p_command_id and establishment_id = v_establishment_id;
  if v_item_count > 0 and (v_reason is null or char_length(v_reason) < 5) then
    raise exception 'Informe uma justificativa de ao menos 5 caracteres para cancelar uma comanda com itens.';
  end if;

  if v_command.status = 'fiado' then
    update public.products p
    set stock_quantity = p.stock_quantity + ci.qty
    from (
      select product_id, sum(quantity) qty
      from public.command_items
      where command_id = p_command_id and establishment_id = v_establishment_id and product_id is not null
      group by product_id
    ) ci
    where p.id = ci.product_id and p.establishment_id = v_establishment_id and p.track_stock = true;
  end if;

  update public.commands
  set status = 'cancelada', closed_at = now(), closed_by = auth.uid(), version = version + 1
  where id = p_command_id and establishment_id = v_establishment_id
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

-- Keep the legacy one-argument RPC safe for old clients: an empty command can
-- still be discarded, while a command with items is rejected by the new rule.
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

revoke all on function public.cancel_command_with_reason(uuid, text) from public, anon;
grant execute on function public.cancel_command_with_reason(uuid, text) to authenticated;
notify pgrst, 'reload schema';
