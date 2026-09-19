-- Allow an authorized operator to accept a specific queue entry from the
-- queue overview or directly from a command detail screen.
-- The update is atomic, tenant-scoped and preserves FIFO as the default path.
begin;

create or replace function public.claim_service_request(p_request_id bigint)
returns public.service_queue language plpgsql security definer set search_path = '' as $$
declare v_request public.service_queue;
begin
  if public.current_role() not in ('admin', 'caixa', 'atendente', 'cozinha') then
    raise exception 'Seu perfil nao tem permissao para atender a fila.';
  end if;

  update public.service_queue
  set status = 'em_atendimento', claimed_at = now(), claimed_by = (select auth.uid())
  where id = p_request_id
    and establishment_id = public.current_establishment_id()
    and status = 'pendente'
  returning * into v_request;

  if v_request.id is null then
    raise exception 'Solicitação não encontrada ou já foi aceita por outra pessoa.';
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
end $$;

revoke all on function public.claim_service_request(bigint) from public, anon;
grant execute on function public.claim_service_request(bigint) to authenticated;

-- Keep the original FIFO action consistent with the direct-action shortcut:
-- accepting a digital order always starts kitchen preparation atomically.
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

notify pgrst, 'reload schema';
commit;
