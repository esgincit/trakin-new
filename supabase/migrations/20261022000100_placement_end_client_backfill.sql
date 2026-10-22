-- Backfill placements.end_client_company_id from the project's client.
-- Rows created before the end-client chain fix (placement on a project another
-- company assigned to us) never got the field set; the project's client_company_id
-- is the original company that initiated the chain (the end client).
update mytrakin.placements p
   set end_client_company_id = pr.client_company_id
  from mytrakin.projects pr
 where pr.id = p.project_id
   and p.end_client_company_id is null
   and pr.client_company_id is not null;

-- Same through one assignment hop (our local project copy keeps the chain in
-- source_project_id when the copy itself still has no client).
update mytrakin.placements p
   set end_client_company_id = src.client_company_id
  from mytrakin.placements p0
   join mytrakin.projects pr on pr.id = p0.project_id
   join mytrakin.projects src on src.id = pr.source_project_id
 where p0.id = p.id
   and p.end_client_company_id is null
   and src.client_company_id is not null;
