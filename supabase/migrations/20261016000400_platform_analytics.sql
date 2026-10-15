-- =============================================================================
-- myTrakIn · P · 0400 · Platform admin: company list / activation queue, platform admins,
-- and platform analytics. Aggregates only (RULE-05 as amended 2026-10-15): every function
-- returns nothing unless the caller is a platform admin.
-- =============================================================================
set search_path = mytrakin, public, extensions;

-- Platform admins manage the list of platform admins.
drop policy if exists platform_admins_manage on platform_admins;
create policy platform_admins_manage on platform_admins for all to mytrakin_api
  using (is_platform_admin()) with check (is_platform_admin());

-- Every company with its owner and onboarding state (the activation queue reads this).
create or replace function platform_companies()
returns table (tenant_id uuid, company_id uuid, name text, kind text, country text, state text, domain text,
               status text, plan text, created_at timestamptz, activated_at timestamptz, decision_note text,
               owner_name text, owner_email text, w9_status text, onboarding_stage smallint)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, c.id, coalesce(c.name, t.name), c.kind, c.country, coalesce(c.state, t.state), c.domain,
         t.status, t.plan, t.created_at, t.activated_at, t.decision_note,
         p.full_name, coalesce(p.email, m.invited_email::text), c.w9_status, c.onboarding_stage
    from tenants t
    left join companies c on c.id = t.company_id
    left join memberships m on m.id = t.owner_membership_id
    left join profiles p on p.id = m.user_id
   where is_platform_admin()
$$;

-- Money moving through each company: totals only, never rows.
create or replace function platform_money_stats()
returns table (tenant_id uuid, ar_invoiced numeric, ar_collected numeric, ap_billed numeric, ap_paid numeric,
               invoiced_30d numeric, collected_30d numeric)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with inv as (
    select i.tenant_id, i.direction, sum(i.amount) as total,
           sum(i.amount) filter (where i.issued_on > current_date - 30) as last30
      from invoices i where i.status not in ('draft', 'void') group by 1, 2),
  pay as (
    select p.tenant_id, i.direction, sum(p.amount) as total,
           sum(p.amount) filter (where p.paid_on > current_date - 30) as last30
      from payments p join invoices i on i.id = p.invoice_id
     where p.status in ('completed', 'confirmed') group by 1, 2)
  select t.id,
         coalesce((select total  from inv where inv.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select total  from pay where pay.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select total  from inv where inv.tenant_id = t.id and direction = 'ap'), 0),
         coalesce((select total  from pay where pay.tenant_id = t.id and direction = 'ap'), 0),
         coalesce((select last30 from inv where inv.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select last30 from pay where pay.tenant_id = t.id and direction = 'ar'), 0)
    from tenants t
   where is_platform_admin()
$$;

-- Client invoicing and collections across the platform, last 12 months.
create or replace function platform_money_trend()
returns table (month text, invoiced numeric, collected numeric)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with months as (select to_char(d, 'YYYY-MM') as month
                    from generate_series(date_trunc('month', now()) - interval '11 months',
                                         date_trunc('month', now()), interval '1 month') d)
  select m.month,
         coalesce((select sum(i.amount) from invoices i where i.direction = 'ar' and i.status not in ('draft', 'void')
                    and to_char(i.issued_on, 'YYYY-MM') = m.month), 0),
         coalesce((select sum(p.amount) from payments p join invoices i on i.id = p.invoice_id
                    where i.direction = 'ar' and p.status in ('completed', 'confirmed')
                      and to_char(p.paid_on, 'YYYY-MM') = m.month), 0)
    from months m
   where is_platform_admin()
   order by m.month
$$;

-- People and the onboarding funnel.
create or replace function platform_overview()
returns table (total_users bigint, new_users_30d bigint, active_users_30d bigint,
               wizards_in_progress bigint, wizards_completed_30d bigint)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (select count(*) from profiles),
         (select count(*) from profiles where created_at > now() - interval '30 days'),
         (select count(distinct user_id) from memberships where last_active_at > now() - interval '30 days'),
         (select count(*) from onboarding_sessions s join tenants t on t.id = s.tenant_id
           where t.status = 'onboarding' and s.status in ('draft', 'email_verified') and s.expires_at > now()),
         (select count(*) from onboarding_sessions s join tenants t on t.id = s.tenant_id
           where t.company_id = s.company_id and s.status = 'complete' and s.created_at > now() - interval '30 days')
   where is_platform_admin()
$$;

revoke all on function platform_companies(), platform_money_stats(), platform_money_trend(), platform_overview() from public;
grant execute on function platform_companies(), platform_money_stats(), platform_money_trend(), platform_overview() to mytrakin_api;
