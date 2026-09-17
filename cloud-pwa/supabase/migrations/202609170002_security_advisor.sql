begin;

alter function public.touch_updated_at()
  set search_path = public;

revoke execute on function public.get_cash_summary(uuid) from public, anon;
grant execute on function public.get_cash_summary(uuid) to authenticated;

commit;
