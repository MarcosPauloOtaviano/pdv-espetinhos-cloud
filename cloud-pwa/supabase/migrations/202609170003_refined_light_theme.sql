begin;

update public.establishments
set
  primary_color = '#a85a2a',
  secondary_color = '#6f3f2b',
  accent_color = '#d79a3a',
  background_color = '#f6f2ec'
where
  primary_color = '#e67e22'
  and secondary_color = '#ca6f1e'
  and accent_color = '#f1c40f'
  and background_color = '#1a1310';

update public.settings
set value = 'light'
where key = 'theme' and value = 'dark';

commit;
