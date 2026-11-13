"use client";

/* The public marketing homepage for MyTrackIn — dark brand hero in the style of
   the reference design, product overview, the vendor-chain money flow, the
   compliance layer, who uses the platform, and a closing CTA.
   Signed-in people are still forwarded to their own home (dashboard, partner
   view, consultant view or the network feed) exactly as before. */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { isStaff, useSession } from "@/lib/session";
import "./landing.css";

const Car = () => (
  <svg className="car" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round">
    <path d="m6 9 6 6 6-6" />
  </svg>
);
const Arrow = () => (
  <svg className="arr" width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12h14m-6-7 7 7-7 7" />
  </svg>
);
const IcoDollar = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round">
    <circle cx="12" cy="12" r="9" /><path d="M12 6.5v11M14.8 9c-.5-1-1.5-1.5-2.8-1.5-1.6 0-2.8.9-2.8 2.2 0 1.4 1.2 2 2.8 2.3 1.8.3 3 .9 3 2.4 0 1.4-1.3 2.3-3 2.3-1.5 0-2.7-.7-3.1-1.8" />
  </svg>
);
const IcoPeople = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round">
    <circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c.6-3 2.7-4.7 5.5-4.7s4.9 1.7 5.5 4.7" /><circle cx="16.5" cy="9" r="2.6" /><path d="M16.5 14.6c2.2.2 3.8 1.6 4.3 3.9" />
  </svg>
);
const IcoShield = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3 4.5 6v5.5c0 4.6 3.1 8.3 7.5 9.5 4.4-1.2 7.5-4.9 7.5-9.5V6L12 3Z" /><path d="m9 11.6 2.1 2.1L15.4 9.4" />
  </svg>
);
const IcoContract = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="3" width="12" height="18" rx="2" /><path d="M7.5 7.5h5M7.5 10.5h5M7.5 13.5h3" /><path d="m14.5 19.5 4-4 2 2-4 4h-2v-2Z" />
  </svg>
);
const IcoTalent = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4.5" width="13" height="15" rx="2" /><circle cx="8" cy="10" r="2" /><path d="M5.5 15.5c.6-1.9 4.4-1.9 5 0M15.5 9.5h.01" /><circle cx="16.5" cy="13.5" r="3" /><path d="m18.8 15.8 2.2 2.2" />
  </svg>
);
const IcoNet = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="6.5" r="2.4" /><circle cx="6.5" cy="16.5" r="2.4" /><circle cx="17.5" cy="16.5" r="2.4" /><path d="M10.8 8.6 7.6 14.5m5.6-5.9 3.2 5.9M8.9 16.3h6.2" />
  </svg>
);
const IcoPay = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round">
    <rect x="2.5" y="5" width="15" height="11" rx="2" /><path d="M2.5 9h15M5.5 12.5h3.5" /><path d="M16.5 11.5 21 13v3.3c0 2.7-1.8 4.6-4.5 5.2-2.7-.6-4.5-2.5-4.5-5.2V13l4.5-1.5Z" /><path d="M16.5 15v3" />
  </svg>
);

export default function Home() {
  const { ready, session, workspace, me } = useSession();
  const router = useRouter();

  // Same home-routing as always: anyone who already has an account goes
  // straight to their own workspace view; visitors get the landing page.
  useEffect(() => {
    if (!ready || !session) return;
    if (!workspace) return void router.replace(me?.is_platform_admin ? "/platform" : "/network");
    if (workspace.role === "consultant") router.replace("/my");
    else if (!isStaff(workspace.role)) router.replace("/partner");
    else router.replace("/dashboard");
  }, [ready, session, workspace, me, router]);

  return (
    <div className="lp-page">
      {/* ================================================================ nav */}
      <nav className="lp-nav">
        <div className="lp-navin">
          <Link className="lp-logo" href="/">
            <span className="lp-mark"><img src="/logo.png" alt="MyTrackIn" /></span>
            <span className="lp-word"><span className="my" style={{ color: "var(--brand)" }}>My</span>Track<span className="in">In</span></span>
          </Link>

          <div className="lp-menu">
            <div className="lp-item">
              <button type="button">Solutions <Car /></button>
              <div className="lp-drop">
                <Link href="#chain"><span><b>Prime &amp; vendor chains</b><small>Pay your sub-vendors through one chain</small></span></Link>
                <Link href="#roles"><span><b>Client links</b><small>Approve and pay straight from a link</small></span></Link>
                <Link href="#compliance"><span><b>W-2 &amp; 1099 programs</b><small>Offer letters, ICA and payroll checks</small></span></Link>
              </div>
            </div>
            <div className="lp-item">
              <button type="button">Features <Car /></button>
              <div className="lp-drop">
                <Link href="#platform"><span><b>Projects &amp; placements</b><small>Work-chains, SOWs and rates</small></span></Link>
                <Link href="#platform"><span><b>Timesheets &amp; invoices</b><small>Approval gates that cannot be bypassed</small></span></Link>
                <Link href="#platform"><span><b>Payments &amp; payroll</b><small>Batch runs, credit notes, receipts</small></span></Link>
                <Link href="#platform"><span><b>Professional network</b><small>Profiles, invitations and messaging</small></span></Link>
              </div>
            </div>
            <div className="lp-item">
              <button type="button">Industries <Car /></button>
              <div className="lp-drop">
                <Link href="#roles"><span><b>IT staffing</b><small>Prime vendors and tiered sub-vendors</small></span></Link>
                <Link href="#roles"><span><b>Consultancies</b><small>1099, C2C and W-2 engagements</small></span></Link>
                <Link href="#roles"><span><b>Payroll providers</b><small>White-label partner workspaces</small></span></Link>
              </div>
            </div>
            <div className="lp-item"><a href="#compliance">Resources</a></div>
            <div className="lp-item"><a href="#roles">Pricing</a></div>
            <div className="lp-item">
              <button type="button">Company <Car /></button>
              <div className="lp-drop">
                <Link href="/network"><span><b>Community</b><small>Meet consultants and partners</small></span></Link>
                <a href="mailto:support@mytrackin.com"><span><b>Contact support</b><small>support@mytrackin.com</small></span></a>
              </div>
            </div>
            <div className="lp-item"><a className="lp-demo" href="mailto:sales@mytrackin.com">Book Demo</a></div>
          </div>

          <div className="lp-auth">
            <Link className="lp-ghost" href="/create-account"><span className="txt">Create Account</span></Link>
            <Link className="lp-signin" href="/login">Sign In <Car /></Link>
          </div>
        </div>
      </nav>

      {/* ============================================================== hero */}
      <div className="lp-hero">
        <div className="lp-heroin">
          <span className="lp-badge">
            <svg className="spark" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z" /></svg>
            Payments · Timesheets · Compliance
          </span>
          <h1><span className="my">My</span>Track<span className="in">In</span></h1>
          <p className="lp-tag">Vendor-chain payments, timesheets, and compliance—connected to every company.</p>
          <p className="lp-sub">
            MyTrackIn means your whole supply chain on one ledger: unite prime vendors, tiered sub-vendors
            and end clients with projects and placements, offer letters, contracts (MSA, NDA, SOW),
            timesheet approvals, invoices, batch payments, payroll for W-2 teams and self-pay for 1099
            contractors, I-9 / E-Verify / W-9 verification, document expiry tracking, an approval flow
            that cannot be bypassed, role-based workspaces for owners, finance, approvers, recruiters
            and consultants, and a professional network with messaging—all audit-ready in one platform.
          </p>
          <div className="lp-ctas">
            <Link className="lp-cta pri" href="#platform">Explore Platform <Arrow /></Link>
            <Link className="lp-cta wht" href="/create-account">Start Workspace</Link>
            <Link className="lp-cta gst" href="#about">What is MyTrackIn?</Link>
          </div>
        </div>

        {/* the three product cards, as in the reference */}
        <div className="lp-cards" id="platform">
          <div className="lp-card">
            <span className="ico"><IcoDollar /></span>
            <h3>Payments</h3>
            <p>Every hop of the chain invoices, gets approved and gets paid from one workbench — client to
              prime, prime to vendor, vendor to contractor — with credit notes, receipts and a running balance.</p>
            <a className="more" href="#chain">See the money flow →</a>
          </div>
          <div className="lp-card">
            <span className="ico"><IcoPeople /></span>
            <h3>Timesheets</h3>
            <p>Weekly time with per-placement rates and hours split, approvals by every company in the chain,
              and gates that block submission until the offer letter or contract behind it is actually in force.</p>
            <a className="more" href="#about">How approvals work →</a>
          </div>
          <div className="lp-card">
            <span className="ico"><IcoShield /></span>
            <h3>Compliance</h3>
            <p>W-9 / I-9 / E-Verify for companies and consultants, MSA–NDA–SOW lifecycle with expiry tracking,
              and offer letters that are checked at placement time, not at the timesheet.</p>
            <a className="more" href="#compliance">Explore compliance →</a>
          </div>
        </div>
        <div className="lp-herotail" />
      </div>

      {/* ====================================================== what is it */}
      <section className="lp-sec" id="about">
        <div className="lp-secin lp-center">
          <p className="lp-eyebrow">What is MyTrackIn</p>
          <h2>One platform for the whole staffing chain</h2>
          <p className="lead">
            Staffing rarely involves one company. A client awards work to a prime, the prime flows it to a
            vendor, the vendor places a W-2 employee or a 1099 contractor. Every hop needs its own contract,
            its own placement and its own invoice — and every one of those can block a payment.
            MyTrackIn models that reality: each company gets a workspace, the chain becomes a first-class
            object, and every document, timesheet and payment is connected across it.
          </p>
          <div className="lp-chain" id="chain">
            <div className="lp-node"><div className="t">End client</div><div className="n">Company A</div><div className="d">awards the project</div></div>
            <div className="lp-arrow"><b>project</b><svg viewBox="0 0 64 10" fill="none" stroke="currentColor" strokeWidth="2"><path d="M0 5h58m0 0-4-4m4 4-4 4" /></svg></div>
            <div className="lp-node"><div className="t">Prime</div><div className="n">Company B</div><div className="d">MSA + subcontract</div></div>
            <div className="lp-arrow"><b>SOW</b><svg viewBox="0 0 64 10" fill="none" stroke="currentColor" strokeWidth="2"><path d="M0 5h58m0 0-4-4m4 4-4 4" /></svg></div>
            <div className="lp-node"><div className="t">Vendor</div><div className="n">Company C</div><div className="d">placement + offer letter</div></div>
            <div className="lp-arrow"><b>timesheet</b><svg viewBox="0 0 64 10" fill="none" stroke="currentColor" strokeWidth="2"><path d="M0 5h58m0 0-4-4m4 4-4 4" /></svg></div>
            <div className="lp-node esg"><div className="t">Talent</div><div className="n">Consultant</div><div className="d">gets paid</div></div>
          </div>
        </div>
      </section>

      {/* ================================================= four pillars (the butterfly's wings) */}
      <section className="lp-sec alt" id="pillars">
        <div className="lp-secin lp-center">
          <p className="lp-eyebrow">The four wings of the butterfly</p>
          <h2>Four pillars that hold every engagement</h2>
          <p className="lead">MyTrackIn is built on the four wings drawn into its logo. Together they take
            a relationship from first contact to last payment — with nothing lost in between.</p>
          <div className="lp-pillars">
            <div className="lp-tile"><span className="ico"><IcoContract /></span><b>Contracts</b>
              <p>Building stronger business relationships.</p>
              <small>MSAs, NDAs and SOWs drafted, signed and renewed inside the chain — every promise
                written down and alive.</small></div>
            <div className="lp-tile"><span className="ico"><IcoTalent /></span><b>Talent (ATS)</b>
              <p>Discovering and connecting the right people with opportunities.</p>
              <small>Projects match consultants to placements with offer letters, profiles and skills
                on record.</small></div>
            <div className="lp-tile"><span className="ico"><IcoNet /></span><b>Social Networking</b>
              <p>Creating meaningful connections and communities.</p>
              <small>A professional network woven across companies — connections, openings, kudos
                and direct messages.</small></div>
            <div className="lp-tile"><span className="ico"><IcoPay /></span><b>Payments</b>
              <p>Enabling secure and reliable transactions.</p>
              <small>Approval-gated invoices, batch payment runs and receipts keep money moving
                safely through every hop.</small></div>
          </div>
        </div>
      </section>

      {/* ========================================================= features */}
      <section className="lp-sec">
        <div className="lp-secin">
          <p className="lp-eyebrow">The platform</p>
          <h2>Everything between award and payment</h2>
          <p className="lead">Each module knows about the others — a missing NDA blocks the SOW, an expired
            offer letter blocks the timesheet, and an unpaid invoice surfaces in every workspace it belongs to.</p>
          <div className="lp-grid">
            <div className="lp-tile"><span className="ico"><IcoPeople /></span><b>Projects &amp; placements</b><p>Create projects per client, flow SOWs down the chain, place W-2 or 1099
              talent with per-placement rates, and track every hop in a visual work-chain.</p></div>
            <div className="lp-tile"><span className="ico"><IcoShield /></span><b>Contracts &amp; e-sign</b><p>MSA, NDA, SOW and subcontract templates with routing envelopes, signature
              events and renewal reminders — dates are checked live, so “active” never lies.</p></div>
            <div className="lp-tile"><span className="ico"><IcoPeople /></span><b>Timesheets</b><p>Weekly submission with hour splits, multi-company approval, per-placement
              rates and off-day handling; locked once approved, with an audit trail.</p></div>
            <div className="lp-tile"><span className="ico"><IcoDollar /></span><b>Invoices &amp; payments</b><p>Per-company invoices from approved time, batch payment runs, acknowledge
              and receipt flow, credit notes and balances on one ledger.</p></div>
            <div className="lp-tile"><span className="ico"><IcoShield /></span><b>Workforce compliance</b><p>W-9 with TIN checks, I-9 and E-Verify status, work-authorisation expiry,
              onboarding checklists per role and document vault with expiration tracking.</p></div>
            <div className="lp-tile"><span className="ico"><IcoPeople /></span><b>Network &amp; profiles</b><p>LinkedIn-style profiles across companies, connections, job openings and
              direct messages — the people side of the chain, built in.</p></div>
          </div>
        </div>
      </section>

      {/* ======================================================== compliance */}
      <section className="lp-sec alt" id="compliance">
        <div className="lp-secin">
          <p className="lp-eyebrow">Compliance</p>
          <h2>The gate cannot be talked around</h2>
          <p className="lead">
            MyTrackIn checks the paperwork at the moment it matters — not after the damage. Placements
            demand an active offer letter on that consultant in that workspace, timesheets demand the
            contract behind them, and every agreement carries its expiry with it. When something is
            missing, the message names the exact document and what to do about it.
          </p>
          <div className="lp-grid">
            <div className="lp-tile"><b>US staffing documents</b><p>I-9, E-Verify and W-9 record-keeping for people and companies, with status at a glance
              and re-verification reminders before they lapse.</p></div>
            <div className="lp-tile"><b>Agreement expiry</b><p>Agreements keep their stored status until renewed, so the platform checks the dates
              itself and shows “Expired” instead of trusting a stale label.</p></div>
            <div className="lp-tile"><b>Audit-ready trail</b><p>Every acceptance, approval and payment decision is logged with the user, time and
              workspace, and role permissions decide who can see or spend what.</p></div>
          </div>
        </div>
      </section>

      {/* ============================================================= roles */}
      <section className="lp-sec" id="roles">
        <div className="lp-secin lp-center">
          <p className="lp-eyebrow">Role-based workspaces</p>
          <h2>The same platform, the right view for everyone</h2>
          <p className="lead">Every person signs in to their own view. Nothing is shared between companies except
            what the chain requires — and permissions follow the role, not the browser.</p>
          <div className="lp-roles">
            <div className="lp-role"><div className="em">🛡️</div><b>Owner / Admin</b><small>Invites the team, owns settings, companies and billing</small></div>
            <div className="lp-role"><div className="em">💰</div><b>Finance</b><small>Invoices, batch payments, credit notes and balances</small></div>
            <div className="lp-role"><div className="em">✅</div><b>Approver</b><small>Reviews and approves timesheets and invoices</small></div>
            <div className="lp-role"><div className="em">🧭</div><b>Recruiter / Vendor</b><small>Projects, placements, offer letters and documents</small></div>
            <div className="lp-role"><div className="em">🧑‍💻</div><b>Consultant</b><small>Own timesheets, payments and profile</small></div>
            <div className="lp-role"><div className="em">🏢</div><b>Client</b><small>Approve time and pay from a secure link</small></div>
          </div>
        </div>
      </section>

      {/* ============================================================== band */}
      <section className="lp-sec">
        <div className="lp-band">
          <h2>Put your whole chain on one ledger</h2>
          <p>Create a workspace in minutes, invite your vendors and consultants, and let every contract,
            timesheet and payment take care of itself.</p>
          <Link className="lp-cta wht" href="/create-account">Start Workspace</Link>
          <small>No credit card needed · role-based from day one</small>
        </div>
      </section>

      {/* ============================================================ footer */}
      <footer className="lp-footer">
        <div className="lp-footin">
          <Link className="lp-logo" href="/">
            <span className="lp-mark"><img src="/logo.png" alt="MyTrackIn" /></span>
            <span className="lp-word"><span style={{ color: "var(--brand)" }}>My</span>Track<span className="in">In</span></span>
          </Link>
          <div className="lp-flinks">
            <Link href="/login">Sign in</Link>
            <Link href="/create-account">Create account</Link>
            <a href="#platform">Platform</a>
            <a href="#compliance">Compliance</a>
            <a href="mailto:support@mytrackin.com">Support</a>
          </div>
          <span style={{ fontSize: 13 }}>© {new Date().getFullYear()} MyTrackIn</span>
        </div>
      </footer>
    </div>
  );
}
