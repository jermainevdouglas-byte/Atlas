"""PropertyManagerHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class PropertyManagerHandlerMixin:
        def _property_manager_get(self, path, u, q):
            u = self._req_role(u, "property_manager", action="manager.portal")
            if not u:
                return
            if path not in ("/property-manager", "/property-manager/search"):
                # Keep paths explicit; deeper tools remain under /manager and /landlord for compatibility.
                return redir(self, "/property-manager")
            c = db()
            run_automated_rent_notifications(c)
            owner_acct = u["account_number"]
            maint_open = to_int(c.execute(
                "SELECT COUNT(1) AS n FROM maintenance_requests m "
                "JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                "JOIN properties p ON p.id=l.property_id "
                "WHERE p.owner_account=? AND m.status IN('open','in_progress')",
                (owner_acct,),
            ).fetchone()["n"], 0)
            checks_due = to_int(c.execute(
                "SELECT COUNT(1) AS n FROM property_checks pc JOIN properties p ON p.id=pc.property_id "
                "WHERE p.owner_account=? AND pc.status IN('requested','scheduled')",
                (owner_acct,),
            ).fetchone()["n"], 0)
            pending_submissions = to_int(c.execute(
                "SELECT COUNT(1) AS n FROM listing_requests lr JOIN properties p ON p.id=lr.property_id "
                "WHERE p.owner_account=? AND lr.status='pending'",
                (owner_acct,),
            ).fetchone()["n"], 0)
            pending_invites = to_int(c.execute(
                "SELECT COUNT(1) AS n FROM tenant_property_invites i JOIN properties p ON p.id=i.property_id "
                "WHERE p.owner_account=? AND i.status='pending'",
                (owner_acct,),
            ).fetchone()["n"], 0)
            total_props = to_int(c.execute(
                "SELECT COUNT(1) AS n FROM properties WHERE owner_account=?",
                (owner_acct,),
            ).fetchone()["n"], 0)
            total_units = to_int(c.execute(
                "SELECT COUNT(1) AS n FROM units u JOIN properties p ON p.id=u.property_id WHERE p.owner_account=?",
                (owner_acct,),
            ).fetchone()["n"], 0)
            occupied_units = to_int(c.execute(
                "SELECT COUNT(1) AS n FROM units u JOIN properties p ON p.id=u.property_id WHERE p.owner_account=? AND u.is_occupied=1",
                (owner_acct,),
            ).fetchone()["n"], 0)
            vacant_units = max(0, total_units - occupied_units)
            monthly_revenue = to_int(c.execute(
                "SELECT COALESCE(SUM(u.rent),0) AS n FROM units u JOIN properties p ON p.id=u.property_id "
                "WHERE p.owner_account=? AND u.is_occupied=1",
                (owner_acct,),
            ).fetchone()["n"], 0)
            month_now = datetime.now(timezone.utc).strftime("%Y-%m")
            month_charges = to_int(c.execute(
                "SELECT COALESCE(SUM(e.amount),0) AS n FROM tenant_ledger_entries e "
                "JOIN tenant_leases l ON l.id=e.lease_id JOIN properties p ON p.id=l.property_id "
                "WHERE p.owner_account=? AND e.statement_month=? "
                "AND e.entry_type IN('charge','late_fee','adjustment') AND e.status!='void'",
                (owner_acct, month_now),
            ).fetchone()["n"], 0)
            month_paid = to_int(c.execute(
                "SELECT COALESCE(SUM(-e.amount),0) AS n FROM tenant_ledger_entries e "
                "JOIN tenant_leases l ON l.id=e.lease_id JOIN properties p ON p.id=l.property_id "
                "WHERE p.owner_account=? AND e.statement_month=? "
                "AND e.entry_type='payment' AND e.status='paid'",
                (owner_acct, month_now),
            ).fetchone()["n"], 0)
            outstanding_rent = max(0, month_charges - month_paid)
            collection_rate = int(round((month_paid / month_charges) * 100.0)) if month_charges > 0 else 100
            recent_rows = c.execute(
                "SELECT created_at,action,details FROM audit_logs WHERE actor_user_id=? ORDER BY id DESC LIMIT 12",
                (u["id"],),
            ).fetchall()
            qtxt = ((q.get("q") or [""])[0]).strip().lower()
            search_results = ""
            if qtxt:
                s = "%" + qtxt + "%"
                pr = c.execute(
                    "SELECT id,name,location FROM properties WHERE owner_account=? AND (LOWER(id) LIKE ? OR LOWER(name) LIKE ? OR LOWER(location) LIKE ?) ORDER BY created_at DESC LIMIT 10",
                    (owner_acct, s, s, s),
                ).fetchall()
                mt = c.execute(
                    "SELECT m.id,m.tenant_account,m.status,m.description,m.created_at,l.property_id,l.unit_label "
                    "FROM maintenance_requests m "
                    "JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                    "JOIN properties p ON p.id=l.property_id "
                    "WHERE p.owner_account=? AND (LOWER(COALESCE(m.tenant_account,'')) LIKE ? OR LOWER(COALESCE(m.description,'')) LIKE ? OR LOWER(COALESCE(l.property_id,'')) LIKE ? OR LOWER(COALESCE(l.unit_label,'')) LIKE ?) "
                    "ORDER BY m.id DESC LIMIT 10",
                    (owner_acct, s, s, s, s),
                ).fetchall()
                lr = c.execute(
                    "SELECT lr.id,lr.title,lr.status,lr.property_id,lr.created_at FROM listing_requests lr "
                    "JOIN properties p ON p.id=lr.property_id "
                    "WHERE p.owner_account=? AND (LOWER(COALESCE(lr.title,'')) LIKE ? OR LOWER(COALESCE(lr.property_id,'')) LIKE ?) "
                    "ORDER BY lr.id DESC LIMIT 10",
                    (owner_acct, s, s),
                ).fetchall()
                tn = c.execute(
                    "SELECT DISTINCT u.account_number,u.full_name,u.email FROM users u "
                    "JOIN tenant_leases l ON l.tenant_account=u.account_number AND l.is_active=1 "
                    "JOIN properties p ON p.id=l.property_id "
                    "WHERE u.role='tenant' AND p.owner_account=? "
                    "AND (LOWER(u.account_number) LIKE ? OR LOWER(u.full_name) LIKE ? OR LOWER(u.email) LIKE ?) "
                    "ORDER BY u.id DESC LIMIT 10",
                    (owner_acct, s, s, s),
                ).fetchall()
                pm = c.execute(
                    "SELECT p.id,p.payer_account,p.payment_type,p.status,p.amount,p.created_at FROM payments p "
                    "WHERE (p.payer_role='tenant' AND EXISTS("
                    "SELECT 1 FROM tenant_leases l JOIN properties pp ON pp.id=l.property_id "
                    "WHERE l.tenant_account=p.payer_account AND pp.owner_account=? ORDER BY l.id DESC LIMIT 1"
                    ")) AND (LOWER(COALESCE(p.payer_account,'')) LIKE ? OR LOWER(COALESCE(p.payment_type,'')) LIKE ? OR LOWER(COALESCE(p.status,'')) LIKE ?) "
                    "ORDER BY p.id DESC LIMIT 10",
                    (owner_acct, s, s, s),
                ).fetchall()
                ins = c.execute(
                    "SELECT i.id,i.property_id,i.unit_label,i.inspection_type,i.status,i.scheduled_date FROM inspections i "
                    "JOIN properties p ON p.id=i.property_id "
                    "WHERE p.owner_account=? AND (LOWER(COALESCE(i.property_id,'')) LIKE ? OR LOWER(COALESCE(i.unit_label,'')) LIKE ? OR LOWER(COALESCE(i.inspection_type,'')) LIKE ?) "
                    "ORDER BY i.id DESC LIMIT 10",
                    (owner_acct, s, s, s),
                ).fetchall()
                prev = c.execute(
                    "SELECT t.id,t.property_id,t.unit_label,t.task,t.status,t.next_due_date FROM preventive_tasks t "
                    "JOIN properties p ON p.id=t.property_id "
                    "WHERE p.owner_account=? AND (LOWER(COALESCE(t.property_id,'')) LIKE ? OR LOWER(COALESCE(t.unit_label,'')) LIKE ? OR LOWER(COALESCE(t.task,'')) LIKE ?) "
                    "ORDER BY t.id DESC LIMIT 10",
                    (owner_acct, s, s, s),
                ).fetchall()
                search_results = "<div style='margin-top:12px;'>"
                search_results += "<h4>Properties</h4>" + ("".join(f"<div class='muted'>{esc(r['id'])} - {esc(r['name'])} ({esc(r['location'])})</div>" for r in pr) or "<div class='muted'>No property matches.</div>")
                search_results += "<h4 style='margin-top:10px;'>Maintenance</h4>" + ("".join(f"<div class='muted'>#{r['id']} [{esc(r['status'])}] {esc(r['property_id'])}/{esc(r['unit_label'])} - {esc((r['description'] or '')[:90])}</div>" for r in mt) or "<div class='muted'>No maintenance matches.</div>")
                search_results += "<h4 style='margin-top:10px;'>Listing Submissions</h4>" + ("".join(f"<div class='muted'>#{r['id']} [{esc(r['status'])}] {esc(r['property_id'])} - {esc(r['title'])}</div>" for r in lr) or "<div class='muted'>No listing matches.</div>")
                search_results += "<h4 style='margin-top:10px;'>Tenants</h4>" + ("".join(f"<div class='muted'>{esc(r['account_number'])} - {esc(r['full_name'])} ({esc(r['email'])})</div>" for r in tn) or "<div class='muted'>No tenant matches.</div>")
                search_results += "<h4 style='margin-top:10px;'>Payments</h4>" + ("".join(f"<div class='muted'>#{r['id']} [{esc(r['status'])}] {esc(r['payer_account'])} - ${to_int(r['amount'],0):,} ({esc(r['payment_type'])})</div>" for r in pm) or "<div class='muted'>No payment matches.</div>")
                search_results += "<h4 style='margin-top:10px;'>Inspections</h4>" + ("".join(f"<div class='muted'>#{r['id']} [{esc(r['status'])}] {esc(r['property_id'])}/{esc(r['unit_label'])} - {esc(r['inspection_type'])} on {esc(r['scheduled_date'])}</div>" for r in ins) or "<div class='muted'>No inspection matches.</div>")
                search_results += "<h4 style='margin-top:10px;'>Preventive Tasks</h4>" + ("".join(f"<div class='muted'>#{r['id']} [{esc(r['status'])}] {esc(r['property_id'])}/{esc(r['unit_label'] or '-')} - {esc(r['task'])} due {esc(r['next_due_date'])}</div>" for r in prev) or "<div class='muted'>No preventive matches.</div>")
                search_results += "</div>"
            c.commit()
            c.close()
            today_queue = (
                "<div class='card' style='margin-top:12px;'>"
                "<h3 style='margin-top:0;'>Today Queue</h3>"
                "<div class='row'>"
                f"<a class='secondary-btn' href='/manager/maintenance'>Open Work Orders ({maint_open})</a>"
                f"<a class='secondary-btn' href='/manager/checks'>Checks Pending ({checks_due})</a>"
                f"<a class='secondary-btn' href='/manager/listing-requests'>Listing Reviews ({pending_submissions})</a>"
                f"<a class='secondary-btn' href='/manager/tenants'>Pending Invites ({pending_invites})</a>"
                "</div>"
                "</div>"
            )
            if recent_rows:
                items = ""
                for r in recent_rows:
                    details = (r["details"] or "").strip()
                    if len(details) > 140:
                        details = details[:137] + "..."
                    items += (
                        "<div style='padding:8px 0;border-bottom:1px solid rgba(255,255,255,.08);'>"
                        f"<div><b>{esc(r['action'])}</b></div>"
                        f"<div class='muted' style='font-size:12px;'>{esc(r['created_at'])} - {esc(details)}</div>"
                        "</div>"
                    )
                recent_feed = "<div class='card' style='margin-top:12px;'><h3 style='margin-top:0;'>Recent Activity</h3>" + items + "</div>"
            else:
                recent_feed = "<div class='card' style='margin-top:12px;'><h3 style='margin-top:0;'>Recent Activity</h3><div class='notice'>No recent actions yet.</div></div>"
            portfolio_kpis = (
                "<div class='card' style='margin-bottom:12px;'>"
                "<h3 style='margin-top:0;'>Portfolio Overview</h3>"
                "<div class='grid-3'>"
                f"<div class='stat'><div class='muted'>Properties</div><div class='stat-num'>{total_props}</div></div>"
                f"<div class='stat'><div class='muted'>Units (Occupied / Vacant)</div><div class='stat-num'>{occupied_units} / {vacant_units}</div></div>"
                f"<div class='stat'><div class='muted'>Monthly Revenue</div><div class='stat-num'>${monthly_revenue:,}</div></div>"
                f"<div class='stat'><div class='muted'>Outstanding ({month_now})</div><div class='stat-num'>${outstanding_rent:,}</div></div>"
                f"<div class='stat'><div class='muted'>Collection Rate ({month_now})</div><div class='stat-num'>{collection_rate}%</div></div>"
                f"<div class='stat'><div class='muted'>Pending Invites</div><div class='stat-num'>{pending_invites}</div></div>"
                "</div>"
                "</div>"
            )
            return send_html(self, render("property_manager_home.html", title="Property Manager Dashboard", nav_right=nav(u, "/property-manager"), nav_menu=nav_menu(u, "/property-manager"), message_box=query_message_box(q), portfolio_kpis=portfolio_kpis, manager_nav_sections=manager_dashboard_sections(u, path), today_queue=today_queue, recent_feed=recent_feed, search_q=esc(qtxt), search_results=search_results))

        def _property_manager_post(self, path, u, f):
            u = self._req_role(u, "property_manager", action="manager.portal")
            if not u:
                return
            return e404(self)



