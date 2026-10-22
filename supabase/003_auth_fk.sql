-- Point actor FKs at app_users (backend identity), not auth-linked profiles.
do $$
declare r record;
begin
  for r in
    select con.conname, tbl.relname as tname
    from pg_constraint con
    join pg_class tbl on tbl.oid = con.conrelid
    join pg_attribute a on a.attrelid = tbl.oid and a.attnum = any(con.conkey)
    where con.contype = 'f'
      and ((tbl.relname = 'payments' and a.attname = 'created_by')
        or (tbl.relname = 'timesheets' and a.attname = 'decided_by')
        or (tbl.relname = 'audit_log' and a.attname = 'actor'))
  loop
    execute format('alter table public.%I drop constraint %I', r.tname, r.conname);
  end loop;
  alter table public.payments
    add constraint payments_created_by_fkey foreign key (created_by) references public.app_users(id);
  alter table public.timesheets
    add constraint timesheets_decided_by_fkey foreign key (decided_by) references public.app_users(id);
  alter table public.audit_log
    add constraint audit_log_actor_fkey foreign key (actor) references public.app_users(id);
end $$;
