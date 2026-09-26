-- Run in the SQL Editor as postgres after the migration. Every change is rolled back.
begin;
do $$
declare
  staff uuid;
  original_role text;
  summary jsonb;
  failed boolean;
begin
  select p.id, p.role into staff, original_role
  from public.profiles p
  join public.establishments e on e.id = p.establishment_id and e.active
  where p.active and p.role = 'admin'
  order by p.created_at
  limit 1;
  assert staff is not null, 'Test requires an active administrator';

  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';

  summary := public.get_sales_report_summary(current_date, current_date);
  assert summary ? 'total_commands', 'Report summary returns an aggregate count';
  assert (select count(*) from public.get_sales_report_page(current_date, current_date, 30, 0)) <= 30,
    'Report page respects the requested limit';
  summary := public.get_dashboard_summary();
  assert summary ? 'total_vendido_hoje', 'Administrator dashboard contains financial keys';

  execute 'reset role';
  update public.profiles set role = 'atendente' where id = staff;
  perform set_config('request.jwt.claims', jsonb_build_object('sub', staff, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';

  failed := false;
  begin
    perform public.get_sales_report_summary(current_date, current_date);
  exception when insufficient_privilege then
    failed := true;
  end;
  assert failed, 'Attendant cannot access administrative reports';
  summary := public.get_dashboard_summary();
  assert summary->'total_vendido_hoje' = 'null'::jsonb, 'Attendant dashboard hides financial totals';
  assert (select count(*) from public.cash_sessions) = 0, 'Attendant cannot read cash sessions';

  execute 'reset role';
  update public.profiles set role = original_role where id = staff;
end $$;
select 'PASS: paginated reports, financial privacy and role restrictions' as result;
rollback;
