-- =============================================================================
-- myTrakIn · 20261022000400 · Fix ts_client_decide crash (ts.full_name)
--
--   ts_client_decide (the e-mailed approval link's decision, used by
--   /public/ts-approvals/{token}/approve and /return) selected the timesheet row
--   only — `select * into ts from mytrakin.timesheets ...` — but then returned
--   ts.full_name in the decision payload. plpgsql raises
--   'record "ts" has no field "full_name"', so approving from the client's link
--   (and the placed-by's in-app Review & approve for the same week) dies with a
--   500. Recreate the function joining the consultant with explicit aliases;
--   behaviour and gates unchanged.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.ts_client_decide(p_hash text, p_decision text, p_note text default null)
returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  link record; ts record; v_creator text; v_client text; v_cemail text;
begin
  select * into link from mytrakin.ts_approval_links where token_hash = p_hash;
  if link.id is null then
    return json_build_object('error', 'invalid');
  end if;
  if link.used_at is not null or link.expires_at < now() then
    return json_build_object('error', case when link.used_at is not null then 'used' else 'expired' end);
  end if;
  select t.id, t.status, t.placed_by_approved, t.end_client_approved, t.week_start, t.consultant_id,
         c.full_name as full_name, c.engagement as engagement
    into ts
    from mytrakin.timesheets t
    join mytrakin.consultants c on c.id = t.consultant_id
   where t.id = link.timesheet_id
     for update of t;
  if ts.id is null or ts.status <> 'submitted' or not ts.placed_by_approved then
    return json_build_object('error', 'not_ready');
  end if;
  select coalesce((select email from mytrakin.profiles where id = link.created_by), '') into v_creator;
  select coalesce(c.name, '') into v_client from mytrakin.companies c where c.id = link.company_id;
  select coalesce((select p.email from mytrakin.profiles p where p.id = c.user_id), c.email, '')
    into v_cemail
    from mytrakin.consultants c
   where c.id = ts.consultant_id;

  if p_decision = 'approve' then
    update mytrakin.timesheets
       set status = 'approved', end_client_approved = true, decided_at = now(), reject_reason = null
     where id = ts.id;
    update mytrakin.ts_approval_links set used_at = now() where id = link.id;
    return json_build_object('ok', true, 'status', 'approved', 'week_start', ts.week_start,
                             'tenant_id', link.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', v_client,
                             'consultant_email', v_cemail);
  elsif p_decision = 'return' then
    if p_note is null or length(btrim(p_note)) < 3 then
      return json_build_object('error', 'note_required');
    end if;
    update mytrakin.timesheets
       set status = 'rejected', reject_reason = btrim(p_note), decided_at = now(),
           placed_by_approved = false, end_client_approved = false
     where id = ts.id;
    update mytrakin.ts_approval_links set used_at = now() where id = link.id;
    return json_build_object('ok', true, 'status', 'rejected', 'week_start', ts.week_start,
                             'tenant_id', link.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', v_client,
                             'consultant_email', v_cemail);
  end if;
  return json_build_object('error', 'invalid_decision');
end $$;
revoke all on function mytrakin.ts_client_decide(text, text, text) from public;
grant execute on function mytrakin.ts_client_decide(text, text, text) to mytrakin_api;
