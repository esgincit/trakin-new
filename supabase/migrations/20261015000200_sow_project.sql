-- =============================================================================
-- myTrakIn · 20261015 0200 · SOWs belong to projects (PLAN WF-04)
--
--   Project → SOW → resources (placements). A SOW (client side) or work order (vendor /
--   1099 side) now records its project. Nullable on purpose: SOWs imported or recorded
--   without a project stay valid. Existing SOWs get the project of the placements using them.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.sows add column if not exists project_id uuid references mytrakin.projects (id);
create index if not exists sows_project_idx on mytrakin.sows (project_id);

update mytrakin.sows s set project_id = sub.project_id
  from (select distinct on (sow_id) sow_id, project_id
          from (select ar_sow_id as sow_id, project_id, start_date from mytrakin.placements where ar_sow_id is not null
                union all
                select ap_sow_id, project_id, start_date from mytrakin.placements where ap_sow_id is not null) x
         order by sow_id, start_date) sub
 where sub.sow_id = s.id and s.project_id is null;
