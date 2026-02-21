"""ManagerHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class ManagerHandlerMixin:
        def _manager_get(self,path,u):
            u=self._req_role(u,"manager",action="manager.portal")
            if not u:return
            nr=nav(u,path)
            q=parse_qs(urlparse(self.path).query)
            if path=="/manager":
                c=db()
                run_automated_rent_notifications(c)
                if u["role"] == "admin":
                    maint_open = to_int(c.execute("SELECT COUNT(1) AS n FROM maintenance_requests WHERE status='open'").fetchone()["n"], 0)
                    maint_progress = to_int(c.execute("SELECT COUNT(1) AS n FROM maintenance_requests WHERE status='in_progress'").fetchone()["n"], 0)
                    checks_due = to_int(c.execute("SELECT COUNT(1) AS n FROM property_checks WHERE status IN ('requested','scheduled')").fetchone()["n"], 0)
                    pending_requests = to_int(c.execute("SELECT COUNT(1) AS n FROM listing_requests WHERE status='pending'").fetchone()["n"], 0)
                    pending_invites = to_int(c.execute("SELECT COUNT(1) AS n FROM tenant_property_invites WHERE status='pending'").fetchone()["n"], 0)
                    feed_rows = c.execute(
                        "SELECT created_at,action,details FROM audit_logs "
                        "WHERE actor_role IN ('property_manager','admin','manager','landlord') ORDER BY id DESC LIMIT 10"
                    ).fetchall()
                else:
                    maint_open = to_int(c.execute(
                        "SELECT COUNT(1) AS n FROM maintenance_requests m "
                        "JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                        "JOIN properties p ON p.id=l.property_id "
                        "WHERE p.owner_account=? AND m.status='open'",
                        (u["account_number"],),
                    ).fetchone()["n"], 0)
                    maint_progress = to_int(c.execute(
                        "SELECT COUNT(1) AS n FROM maintenance_requests m "
                        "JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                        "JOIN properties p ON p.id=l.property_id "
                        "WHERE p.owner_account=? AND m.status='in_progress'",
                        (u["account_number"],),
                    ).fetchone()["n"], 0)
                    checks_due = to_int(c.execute(
                        "SELECT COUNT(1) AS n FROM property_checks pc "
                        "JOIN properties p ON p.id=pc.property_id "
                        "WHERE p.owner_account=? AND pc.status IN ('requested','scheduled')",
                        (u["account_number"],),
                    ).fetchone()["n"], 0)
                    pending_requests = to_int(c.execute(
                        "SELECT COUNT(1) AS n FROM listing_requests lr "
                        "JOIN properties p ON p.id=lr.property_id "
                        "WHERE p.owner_account=? AND lr.status='pending'",
                        (u["account_number"],),
                    ).fetchone()["n"], 0)
                    pending_invites = to_int(c.execute(
                        "SELECT COUNT(1) AS n FROM tenant_property_invites i "
                        "JOIN properties p ON p.id=i.property_id "
                        "WHERE p.owner_account=? AND i.status='pending'",
                        (u["account_number"],),
                    ).fetchone()["n"], 0)
                    feed_rows = c.execute(
                        "SELECT created_at,action,details FROM audit_logs WHERE actor_user_id=? ORDER BY id DESC LIMIT 10",
                        (u["id"],),
                    ).fetchall()
                c.commit()
                c.close()
                today_queue = (
                    "<div class='card' style='margin-top:12px;'>"
                    "<h3 style='margin-top:0;'>Today Queue</h3>"
                    "<div class='row'>"
                    f"<a class='secondary-btn' href='/manager/maintenance?status=open'>Open Maintenance ({maint_open})</a>"
                    f"<a class='secondary-btn' href='/manager/maintenance?status=in_progress'>In Progress ({maint_progress})</a>"
                    f"<a class='secondary-btn' href='/manager/checks?status=requested'>Checks Pending ({checks_due})</a>"
                    f"<a class='secondary-btn' href='/manager/listing-requests'>Listing Reviews ({pending_requests})</a>"
                    f"<a class='secondary-btn' href='/manager/tenants'>Pending Invites ({pending_invites})</a>"
                    "</div>"
                    "</div>"
                )
                if feed_rows:
                    items = ""
                    for r in feed_rows:
                        details = (r["details"] or "").strip()
                        if len(details) > 120:
                            details = details[:117] + "..."
                        items += (
                            "<div style='padding:8px 0;border-bottom:1px solid rgba(255,255,255,.08);'>"
                            f"<div><b>{esc(r['action'])}</b></div>"
                            f"<div class='muted' style='font-size:12px;'>{esc(r['created_at'])} - {esc(details)}</div>"
                            "</div>"
                        )
                    activity_feed = (
                        "<div class='card' style='margin-top:12px;'>"
                        "<h3 style='margin-top:0;'>Recent Activity</h3>"
                        f"{items}"
                        "</div>"
                    )
                else:
                    activity_feed = "<div class='card' style='margin-top:12px;'><h3 style='margin-top:0;'>Recent Activity</h3><div class='notice'>No recent role actions yet.</div></div>"
                return send_html(self,render("manager_home.html",title="Manager Dashboard",nav_right=nr,nav_menu=nav_menu(u,path),manager_nav_sections=manager_dashboard_sections(u, path),today_queue=today_queue,activity_feed=activity_feed))
            if path=="/manager/analytics":
                if not self._req_action(u, "manager.portal"): return
                q2=parse_qs(urlparse(self.path).query)
                c = db()
                if u["role"] == "admin":
                    prop_filter_sql = ""
                    args = []
                else:
                    prop_filter_sql = " AND p.owner_account=? "
                    args = [u["account_number"]]
                occupancy_row = c.execute(
                    "SELECT COUNT(1) AS units_total,COALESCE(SUM(CASE WHEN u.is_occupied=1 THEN 1 ELSE 0 END),0) AS units_occupied "
                    "FROM units u JOIN properties p ON p.id=u.property_id WHERE 1=1 " + prop_filter_sql,
                    tuple(args),
                ).fetchone()
                maint_row = c.execute(
                    "SELECT "
                    "COALESCE(SUM(CASE WHEN m.status='open' THEN 1 ELSE 0 END),0) AS open_cnt,"
                    "COALESCE(SUM(CASE WHEN m.status='in_progress' THEN 1 ELSE 0 END),0) AS prog_cnt,"
                    "COALESCE(SUM(CASE WHEN m.status='closed' THEN 1 ELSE 0 END),0) AS closed_cnt "
                    "FROM maintenance_requests m "
                    "LEFT JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                    "LEFT JOIN properties p ON p.id=l.property_id WHERE 1=1 " + prop_filter_sql,
                    tuple(args),
                ).fetchone()
                open_age = c.execute(
                    "SELECT COALESCE(AVG(julianday('now')-julianday(m.created_at)),0) AS avg_days "
                    "FROM maintenance_requests m "
                    "LEFT JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                    "LEFT JOIN properties p ON p.id=l.property_id "
                    "WHERE m.status IN('open','in_progress') " + prop_filter_sql,
                    tuple(args),
                ).fetchone()
                now_dt = datetime.now(timezone.utc)
                month_now = now_dt.strftime("%Y-%m")
                month_prev = (now_dt.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
                paid_amt = c.execute(
                    "SELECT COALESCE(SUM(pmt.amount),0) AS n FROM payments pmt "
                    "WHERE pmt.status='paid' AND pmt.payer_role='tenant' AND substr(pmt.created_at,1,7)=? AND EXISTS("
                    "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                    "WHERE l.tenant_account=pmt.payer_account AND l.is_active=1" + prop_filter_sql +
                    ")",
                    tuple([month_now] + args),
                ).fetchone()["n"]
                paid_prev = c.execute(
                    "SELECT COALESCE(SUM(pmt.amount),0) AS n FROM payments pmt "
                    "WHERE pmt.status='paid' AND pmt.payer_role='tenant' AND substr(pmt.created_at,1,7)=? AND EXISTS("
                    "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                    "WHERE l.tenant_account=pmt.payer_account AND l.is_active=1" + prop_filter_sql +
                    ")",
                    tuple([month_prev] + args),
                ).fetchone()["n"]
                submitted_amt = c.execute(
                    "SELECT COALESCE(SUM(pmt.amount),0) AS n FROM payments pmt "
                    "WHERE pmt.status='submitted' AND pmt.payer_role='tenant' AND substr(pmt.created_at,1,7)=? AND EXISTS("
                    "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                    "WHERE l.tenant_account=pmt.payer_account AND l.is_active=1" + prop_filter_sql +
                    ")",
                    tuple([month_now] + args),
                ).fetchone()["n"]
                submitted_prev = c.execute(
                    "SELECT COALESCE(SUM(pmt.amount),0) AS n FROM payments pmt "
                    "WHERE pmt.status='submitted' AND pmt.payer_role='tenant' AND substr(pmt.created_at,1,7)=? AND EXISTS("
                    "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                    "WHERE l.tenant_account=pmt.payer_account AND l.is_active=1" + prop_filter_sql +
                    ")",
                    tuple([month_prev] + args),
                ).fetchone()["n"]
                pending_apps = c.execute(
                    "SELECT COUNT(1) AS n FROM applications WHERE status IN('submitted','under_review')"
                ).fetchone()["n"]
                apps_new_now = c.execute(
                    "SELECT COUNT(1) AS n FROM applications WHERE substr(created_at,1,7)=?",
                    (month_now,),
                ).fetchone()["n"]
                apps_new_prev = c.execute(
                    "SELECT COUNT(1) AS n FROM applications WHERE substr(created_at,1,7)=?",
                    (month_prev,),
                ).fetchone()["n"]
                pending_inq = c.execute(
                    "SELECT COUNT(1) AS n FROM inquiries WHERE status IN('new','open')"
                ).fetchone()["n"]
                inq_new_now = c.execute(
                    "SELECT COUNT(1) AS n FROM inquiries WHERE substr(created_at,1,7)=?",
                    (month_now,),
                ).fetchone()["n"]
                inq_new_prev = c.execute(
                    "SELECT COUNT(1) AS n FROM inquiries WHERE substr(created_at,1,7)=?",
                    (month_prev,),
                ).fetchone()["n"]
                pending_listings = c.execute(
                    "SELECT COUNT(1) AS n FROM listing_requests lr "
                    "LEFT JOIN properties p ON p.id=lr.property_id "
                    "WHERE lr.status='pending' " + prop_filter_sql,
                    tuple(args),
                ).fetchone()["n"]
                listings_new_now = c.execute(
                    "SELECT COUNT(1) AS n FROM listing_requests lr LEFT JOIN properties p ON p.id=lr.property_id "
                    "WHERE substr(lr.created_at,1,7)=? " + prop_filter_sql,
                    tuple([month_now] + args),
                ).fetchone()["n"]
                listings_new_prev = c.execute(
                    "SELECT COUNT(1) AS n FROM listing_requests lr LEFT JOIN properties p ON p.id=lr.property_id "
                    "WHERE substr(lr.created_at,1,7)=? " + prop_filter_sql,
                    tuple([month_prev] + args),
                ).fetchone()["n"]
                maint_new_now = c.execute(
                    "SELECT COUNT(1) AS n FROM maintenance_requests m "
                    "LEFT JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                    "LEFT JOIN properties p ON p.id=l.property_id "
                    "WHERE substr(m.created_at,1,7)=? " + prop_filter_sql,
                    tuple([month_now] + args),
                ).fetchone()["n"]
                maint_new_prev = c.execute(
                    "SELECT COUNT(1) AS n FROM maintenance_requests m "
                    "LEFT JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                    "LEFT JOIN properties p ON p.id=l.property_id "
                    "WHERE substr(m.created_at,1,7)=? " + prop_filter_sql,
                    tuple([month_prev] + args),
                ).fetchone()["n"]
                c.close()
                units_total = max(0, to_int(occupancy_row["units_total"] if occupancy_row else 0, 0))
                units_occ = max(0, to_int(occupancy_row["units_occupied"] if occupancy_row else 0, 0))
                occ_rate = int(round((units_occ / units_total) * 100.0)) if units_total > 0 else 0
                avg_open_days = round(float(open_age["avg_days"] if open_age and open_age["avg_days"] is not None else 0.0), 1)
                def _trend_line(cur_val, prev_val, currency=False, note_label="vs previous month"):
                    cur_n = to_int(cur_val, 0)
                    prev_n = to_int(prev_val, 0)
                    delta = cur_n - prev_n
                    cls = "kpi-trend up" if delta > 0 else ("kpi-trend down" if delta < 0 else "kpi-trend")
                    sign = "+" if delta > 0 else ("-" if delta < 0 else "")
                    if currency:
                        delta_txt = f"{sign}${abs(delta):,}" if delta != 0 else "$0"
                    else:
                        delta_txt = f"{delta:+,}" if delta != 0 else "0"
                    return f"<div class='{cls}'>{delta_txt} {esc(note_label)} ({month_prev})</div>"
                kpi_cards = (
                    "<div class='card'><div class='grid-3'>"
                    f"<div class='stat'><div class='muted'>Occupancy</div><div class='stat-num'>{units_occ}/{units_total} ({occ_rate}%)</div></div>"
                    f"<div class='stat'><div class='muted'>Maintenance Open</div><div class='stat-num'>{to_int(maint_row['open_cnt'],0)}</div></div>"
                    f"<div class='stat'><div class='muted'>Maintenance In Progress</div><div class='stat-num'>{to_int(maint_row['prog_cnt'],0)}</div></div>"
                    f"<div class='stat'><div class='muted'>Avg Open Age</div><div class='stat-num'>{avg_open_days}d</div>{_trend_line(maint_new_now, maint_new_prev, note_label='new tickets')}</div>"
                    f"<div class='stat'><div class='muted'>Paid This Month ({month_now})</div><div class='stat-num'>${to_int(paid_amt,0):,}</div>{_trend_line(paid_amt, paid_prev, currency=True)}</div>"
                    f"<div class='stat'><div class='muted'>Submitted This Month</div><div class='stat-num'>${to_int(submitted_amt,0):,}</div>{_trend_line(submitted_amt, submitted_prev, currency=True)}</div>"
                    f"<div class='stat'><div class='muted'>Pending Applications</div><div class='stat-num'>{to_int(pending_apps,0)}</div>{_trend_line(apps_new_now, apps_new_prev, note_label='new applications')}</div>"
                    f"<div class='stat'><div class='muted'>Open Inquiries</div><div class='stat-num'>{to_int(pending_inq,0)}</div>{_trend_line(inq_new_now, inq_new_prev, note_label='new inquiries')}</div>"
                    f"<div class='stat'><div class='muted'>Pending Listing Reviews</div><div class='stat-num'>{to_int(pending_listings,0)}</div>{_trend_line(listings_new_now, listings_new_prev, note_label='new submissions')}</div>"
                    "</div></div>"
                )
                return send_html(self,render("manager_analytics.html",title="Manager Analytics",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),kpi_cards=kpi_cards))
            if path=="/manager/queue":
                if not self._req_action(u, "manager.portal"): return
                q2=parse_qs(urlparse(self.path).query)
                bucket=((q2.get("bucket") or ["all"])[0]).strip().lower()
                if bucket not in ("all","maintenance","payments","checks","inquiries","applications","invites"):
                    bucket = "all"
                c=db()
                items = []
                if u["role"] == "admin":
                    maint_rows = c.execute(
                        "SELECT id,tenant_account,status,description,CAST(julianday('now')-julianday(created_at) AS INT) AS age_days "
                        "FROM maintenance_requests WHERE status IN('open','in_progress') ORDER BY created_at ASC LIMIT 120"
                    ).fetchall()
                    check_rows = c.execute(
                        "SELECT id,property_id,status,CAST(julianday('now')-julianday(created_at) AS INT) AS age_days "
                        "FROM property_checks WHERE status IN('requested','scheduled') ORDER BY created_at ASC LIMIT 120"
                    ).fetchall()
                    invite_rows = c.execute(
                        "SELECT id,tenant_account,property_id,unit_label,CAST(julianday('now')-julianday(created_at) AS INT) AS age_days "
                        "FROM tenant_property_invites WHERE status='pending' ORDER BY created_at ASC LIMIT 120"
                    ).fetchall()
                    pay_rows = c.execute(
                        "SELECT id,payer_account,amount,CAST(julianday('now')-julianday(created_at) AS INT) AS age_days "
                        "FROM payments WHERE status='submitted' ORDER BY created_at ASC LIMIT 120"
                    ).fetchall()
                else:
                    maint_rows = c.execute(
                        "SELECT m.id,m.tenant_account,m.status,m.description,CAST(julianday('now')-julianday(m.created_at) AS INT) AS age_days "
                        "FROM maintenance_requests m "
                        "JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                        "JOIN properties p ON p.id=l.property_id "
                        "WHERE p.owner_account=? AND m.status IN('open','in_progress') "
                        "ORDER BY m.created_at ASC LIMIT 120",
                        (u["account_number"],),
                    ).fetchall()
                    check_rows = c.execute(
                        "SELECT pc.id,pc.property_id,pc.status,CAST(julianday('now')-julianday(pc.created_at) AS INT) AS age_days "
                        "FROM property_checks pc JOIN properties p ON p.id=pc.property_id "
                        "WHERE p.owner_account=? AND pc.status IN('requested','scheduled') "
                        "ORDER BY pc.created_at ASC LIMIT 120",
                        (u["account_number"],),
                    ).fetchall()
                    invite_rows = c.execute(
                        "SELECT i.id,i.tenant_account,i.property_id,i.unit_label,CAST(julianday('now')-julianday(i.created_at) AS INT) AS age_days "
                        "FROM tenant_property_invites i JOIN properties p ON p.id=i.property_id "
                        "WHERE p.owner_account=? AND i.status='pending' "
                        "ORDER BY i.created_at ASC LIMIT 120",
                        (u["account_number"],),
                    ).fetchall()
                    pay_rows = c.execute(
                        "SELECT p.id,p.payer_account,p.amount,CAST(julianday('now')-julianday(p.created_at) AS INT) AS age_days "
                        "FROM payments p WHERE p.status='submitted' AND EXISTS("
                        "SELECT 1 FROM tenant_leases l JOIN properties pp ON pp.id=l.property_id "
                        "WHERE l.tenant_account=p.payer_account AND l.is_active=1 AND pp.owner_account=?"
                        ") ORDER BY p.created_at ASC LIMIT 120",
                        (u["account_number"],),
                    ).fetchall()
                app_rows = c.execute(
                    "SELECT a.id,a.full_name,a.status,CAST(julianday('now')-julianday(a.created_at) AS INT) AS age_days,"
                    "COALESCE(l.title,'(General)') AS listing_title "
                    "FROM applications a LEFT JOIN listings l ON l.id=a.listing_id "
                    "WHERE a.status IN('submitted','under_review') ORDER BY a.created_at ASC LIMIT 120"
                ).fetchall()
                inq_rows = c.execute(
                    "SELECT i.id,i.full_name,i.status,CAST(julianday('now')-julianday(i.created_at) AS INT) AS age_days,"
                    "COALESCE(l.title,'(General)') AS listing_title "
                    "FROM inquiries i LEFT JOIN listings l ON l.id=i.listing_id "
                    "WHERE i.status IN('new','open') ORDER BY i.created_at ASC LIMIT 120"
                ).fetchall()
                c.close()
                def _queue_action_form(kind, item_id, action, label):
                    return (
                        "<form method='POST' action='/manager/queue/action' style='margin:0;'>"
                        f"<input type='hidden' name='item_kind' value='{esc(kind)}'>"
                        f"<input type='hidden' name='item_id' value='{to_int(item_id,0)}'>"
                        f"<input type='hidden' name='action' value='{esc(action)}'>"
                        f"<input type='hidden' name='bucket' value='{esc(bucket)}'>"
                        f"<button class='primary-btn' type='submit'>{esc(label)}</button>"
                        "</form>"
                    )
                for r in maint_rows:
                    st = (r["status"] or "open").strip().lower()
                    quick = _queue_action_form("maintenance", r["id"], ("start" if st == "open" else "close"), ("Start Work" if st == "open" else "Complete"))
                    items.append({"kind":"maintenance","priority":3,"age":max(0,to_int(r["age_days"],0)),"title":f"Maintenance #{r['id']}","desc":f"{r['tenant_account']} - {(r['description'] or '')[:120]}","actions":quick + f"<a class='ghost-btn' href='/manager/maintenance?q={r['id']}'>Open</a>"})
                for r in pay_rows:
                    quick = _queue_action_form("payments", r["id"], "approve", "Approve")
                    items.append({"kind":"payments","priority":2,"age":max(0,to_int(r["age_days"],0)),"title":f"Payment #{r['id']}","desc":f"{r['payer_account']} - ${to_int(r['amount'],0):,} submitted","actions":quick + f"<a class='ghost-btn' href='/manager/payments?q={r['id']}'>Review</a>"})
                for r in check_rows:
                    st = (r["status"] or "requested").strip().lower()
                    quick = _queue_action_form("checks", r["id"], ("schedule" if st == "requested" else "complete"), ("Schedule" if st == "requested" else "Complete"))
                    items.append({"kind":"checks","priority":2,"age":max(0,to_int(r["age_days"],0)),"title":f"Property Check #{r['id']}","desc":f"{r['property_id']} - status: {r['status']}","actions":quick + "<a class='ghost-btn' href='/manager/checks'>Open</a>"})
                for r in inq_rows:
                    st = (r["status"] or "new").strip().lower()
                    quick = _queue_action_form("inquiries", r["id"], ("open" if st == "new" else "close"), ("Open" if st == "new" else "Close"))
                    items.append({"kind":"inquiries","priority":1,"age":max(0,to_int(r["age_days"],0)),"title":f"Inquiry #{r['id']}","desc":f"{r['full_name']} - {r['listing_title']}","actions":quick + f"<a class='ghost-btn' href='/manager/inquiries?q={r['id']}'>Respond</a>"})
                for r in app_rows:
                    st = (r["status"] or "submitted").strip().lower()
                    quick = _queue_action_form("applications", r["id"], ("review" if st == "submitted" else "approve"), ("Mark Review" if st == "submitted" else "Approve"))
                    items.append({"kind":"applications","priority":1,"age":max(0,to_int(r["age_days"],0)),"title":f"Application #{r['id']}","desc":f"{r['full_name']} - {r['listing_title']}","actions":quick + f"<a class='ghost-btn' href='/manager/applications?q={r['id']}'>Open</a>"})
                for r in invite_rows:
                    quick = _queue_action_form("invites", r["id"], "cancel", "Cancel Invite")
                    items.append({"kind":"invites","priority":1,"age":max(0,to_int(r["age_days"],0)),"title":f"Tenant Invite #{r['id']}","desc":f"{r['tenant_account']} - {r['property_id']} / {r['unit_label']}","actions":quick + "<a class='ghost-btn' href='/manager/tenants'>Manage</a>"})
                filtered = [it for it in items if bucket == "all" or it["kind"] == bucket]
                filtered.sort(key=lambda it: (-to_int(it["priority"], 0), -to_int(it["age"], 0), it["kind"]))
                queue_rows = ""
                for it in filtered:
                    pri = "URGENT" if to_int(it["priority"], 0) >= 3 else ("HIGH" if to_int(it["priority"], 0) == 2 else "NORMAL")
                    pri_cls = "badge no" if pri == "URGENT" else ("badge" if pri == "HIGH" else "badge ok")
                    queue_rows += (
                        "<div style='padding:10px 0;border-bottom:1px solid rgba(255,255,255,.08);'>"
                        f"<div class='row' style='justify-content:space-between;align-items:center;'><b>{esc(it['title'])}</b><span class='{pri_cls}'>{pri}</span></div>"
                        f"<div class='muted'>{esc(it['desc'])}</div>"
                        f"<div class='row' style='margin-top:6px;'><span class='muted'>Waiting: {to_int(it['age'],0)} day(s)</span>{it['actions']}</div>"
                        "</div>"
                    )
                if not queue_rows:
                    queue_rows = "<div class='notice'>No queue items for this filter.</div>"
                queue_filters = (
                    "<div class='card' style='margin-bottom:10px;'><form method='GET' action='/manager/queue' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:200px;'><label>Queue Filter</label>"
                    f"<select name='bucket'><option value='all' {'selected' if bucket=='all' else ''}>All</option>"
                    f"<option value='maintenance' {'selected' if bucket=='maintenance' else ''}>Maintenance</option>"
                    f"<option value='payments' {'selected' if bucket=='payments' else ''}>Payments</option>"
                    f"<option value='checks' {'selected' if bucket=='checks' else ''}>Property Checks</option>"
                    f"<option value='inquiries' {'selected' if bucket=='inquiries' else ''}>Inquiries</option>"
                    f"<option value='applications' {'selected' if bucket=='applications' else ''}>Applications</option>"
                    f"<option value='invites' {'selected' if bucket=='invites' else ''}>Invites</option></select></div>"
                    "<button class='primary-btn' type='submit'>Apply</button>"
                    "<a class='ghost-btn' href='/manager/queue'>Reset</a>"
                    "</form></div>"
                )
                return send_html(self,render("manager_queue.html",title="Manager Queue",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),queue_filters=queue_filters,queue_rows=queue_rows))
            if path=="/manager/rent-roll":
                if not self._req_action(u, "manager.portal"): return
                q2=parse_qs(urlparse(self.path).query)
                prop_filter=((q2.get("property") or [""])[0]).strip()
                status_filter=((q2.get("status") or ["all"])[0]).strip().lower()
                if status_filter not in ("all", "current", "late", "vacant"):
                    status_filter = "all"
                search=((q2.get("q") or [""])[0]).strip().lower()
                sort=((q2.get("sort") or ["late_desc"])[0]).strip().lower()
                page, per, offset = parse_page_params(q2, default_per=30, max_per=200)
                month_now = datetime.now(timezone.utc).strftime("%Y-%m")
                today = datetime.now(timezone.utc).date()
                c=db()
                props = c.execute(
                    "SELECT id,name FROM properties " + ("" if u["role"]=="admin" else "WHERE owner_account=? ") + "ORDER BY created_at DESC",
                    tuple() if u["role"]=="admin" else (u["account_number"],),
                ).fetchall()
                sql_units = (
                    "SELECT p.id AS property_id,p.name AS property_name,u.unit_label,u.rent,u.is_occupied,"
                    "l.id AS lease_id,l.tenant_account,l.start_date,uu.full_name AS tenant_name "
                    "FROM units u JOIN properties p ON p.id=u.property_id "
                    "LEFT JOIN tenant_leases l ON l.property_id=u.property_id AND l.unit_label=u.unit_label AND l.is_active=1 "
                    "LEFT JOIN users uu ON uu.account_number=l.tenant_account WHERE 1=1 "
                )
                args_units = []
                if u["role"] != "admin":
                    sql_units += "AND p.owner_account=? "
                    args_units.append(u["account_number"])
                if prop_filter:
                    sql_units += "AND p.id=? "
                    args_units.append(prop_filter)
                sql_units += "ORDER BY p.name,u.unit_label"
                unit_rows = c.execute(sql_units, tuple(args_units)).fetchall()
                roommate_cache = {}
                paid_cache = {}
                last_paid_cache = {}
                rows_data = []
                for r in unit_rows:
                    lease_id = to_int(r["lease_id"], 0)
                    rent_amt = max(0, to_int(r["rent"], 0))
                    tenant_acct = (r["tenant_account"] or "").strip() if lease_id > 0 else ""
                    tenant_name = (r["tenant_name"] or tenant_acct or "").strip()
                    accounts = []
                    if tenant_acct:
                        accounts.append(tenant_acct)
                    if lease_id > 0:
                        if lease_id not in roommate_cache:
                            roommate_cache[lease_id] = [x["tenant_account"] for x in c.execute(
                                "SELECT tenant_account FROM lease_roommates WHERE lease_id=? AND status='active'",
                                (lease_id,),
                            ).fetchall()]
                        for acct in roommate_cache[lease_id]:
                            if acct and acct not in accounts:
                                accounts.append(acct)
                    paid_month = 0
                    last_paid = ""
                    if accounts:
                        key = "|".join(sorted(accounts))
                        if key not in paid_cache:
                            ph = ",".join("?" for _ in accounts)
                            paid_cache[key] = to_int(c.execute(
                                f"SELECT COALESCE(SUM(amount),0) AS n FROM payments WHERE payer_role='tenant' "
                                f"AND payment_type='rent' AND status='paid' AND substr(created_at,1,7)=? AND payer_account IN ({ph})",
                                tuple([month_now] + accounts),
                            ).fetchone()["n"], 0)
                            lp = c.execute(
                                f"SELECT created_at FROM payments WHERE payer_role='tenant' AND payment_type='rent' "
                                f"AND status='paid' AND payer_account IN ({ph}) ORDER BY created_at DESC,id DESC LIMIT 1",
                                tuple(accounts),
                            ).fetchone()
                            last_paid_cache[key] = lp["created_at"] if lp else ""
                        paid_month = paid_cache.get(key, 0)
                        last_paid = last_paid_cache.get(key, "")
                    if lease_id <= 0:
                        row_status = "vacant"
                        days_late = 0
                    else:
                        due_day = 1
                        start_dt = _parse_ymd(r["start_date"] or "")
                        if start_dt:
                            due_day = max(1, min(28, start_dt.day))
                        due_dt = today.replace(day=due_day)
                        if rent_amt <= 0:
                            row_status = "current"
                            days_late = 0
                        elif paid_month >= rent_amt:
                            row_status = "current"
                            days_late = 0
                        else:
                            row_status = "late"
                            days_late = max(0, (today - due_dt).days)
                    hay = " ".join([
                        str(r["property_id"] or ""),
                        str(r["property_name"] or ""),
                        str(r["unit_label"] or ""),
                        tenant_name,
                        tenant_acct,
                    ]).lower()
                    if search and (search not in hay):
                        continue
                    if status_filter != "all" and row_status != status_filter:
                        continue
                    rows_data.append({
                        "property": f"{r['property_name']} ({r['property_id']})",
                        "property_name": r["property_name"] or "",
                        "unit": r["unit_label"] or "-",
                        "tenant": tenant_name or "(Vacant)",
                        "rent": rent_amt,
                        "status": row_status,
                        "days_late": days_late,
                        "last_paid": last_paid or "-",
                        "actions": "<a class='ghost-btn' href='/manager/leases'>Leases</a><a class='ghost-btn' href='/manager/payments'>Payments</a>",
                    })
                c.close()
                if sort == "rent_desc":
                    rows_data.sort(key=lambda x: (-to_int(x["rent"], 0), x["property_name"], x["unit"]))
                elif sort == "rent_asc":
                    rows_data.sort(key=lambda x: (to_int(x["rent"], 0), x["property_name"], x["unit"]))
                elif sort == "alpha":
                    rows_data.sort(key=lambda x: (x["property_name"], x["unit"]))
                else:
                    rows_data.sort(key=lambda x: (-to_int(x["days_late"], 0), x["property_name"], x["unit"]))
                total = len(rows_data)
                page_rows = rows_data[offset:offset + per]
                rent_roll_rows = ""
                current_cnt = 0
                late_cnt = 0
                vacant_cnt = 0
                for r in rows_data:
                    if r["status"] == "current":
                        current_cnt += 1
                    elif r["status"] == "late":
                        late_cnt += 1
                    elif r["status"] == "vacant":
                        vacant_cnt += 1
                for r in page_rows:
                    status_cls = "badge ok" if r["status"] == "current" else ("badge no" if r["status"] == "late" else "badge")
                    rent_roll_rows += (
                        "<tr>"
                        f"<td>{esc(r['property'])}</td>"
                        f"<td>{esc(r['unit'])}</td>"
                        f"<td>{esc(r['tenant'])}</td>"
                        f"<td>${to_int(r['rent'],0):,}</td>"
                        f"<td><span class='{status_cls}'>{esc(r['status'])}</span></td>"
                        f"<td>{to_int(r['days_late'],0)}</td>"
                        f"<td>{esc(r['last_paid'])}</td>"
                        f"<td>{r['actions']}</td>"
                        "</tr>"
                    )
                if not rent_roll_rows:
                    rent_roll_rows = "<tr><td colspan='8' class='muted'>No units matched this filter.</td></tr>"
                prop_opts = "".join(f"<option value='{esc(p['id'])}' {'selected' if prop_filter==p['id'] else ''}>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
                filters_form = (
                    "<div class='card' style='margin-bottom:10px;'><form method='GET' action='/manager/rent-roll' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:220px;'><label>Property</label>"
                    f"<select name='property'><option value=''>All</option>{prop_opts}</select></div>"
                    "<div class='field' style='min-width:160px;'><label>Status</label>"
                    f"<select name='status'><option value='all' {'selected' if status_filter=='all' else ''}>All</option>"
                    f"<option value='current' {'selected' if status_filter=='current' else ''}>Current</option>"
                    f"<option value='late' {'selected' if status_filter=='late' else ''}>Late</option>"
                    f"<option value='vacant' {'selected' if status_filter=='vacant' else ''}>Vacant</option></select></div>"
                    f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='property/unit/tenant'></div>"
                    "<div class='field' style='min-width:170px;'><label>Sort</label>"
                    f"<select name='sort'><option value='late_desc' {'selected' if sort=='late_desc' else ''}>Most Late</option>"
                    f"<option value='alpha' {'selected' if sort=='alpha' else ''}>Property A-Z</option>"
                    f"<option value='rent_desc' {'selected' if sort=='rent_desc' else ''}>Rent high to low</option>"
                    f"<option value='rent_asc' {'selected' if sort=='rent_asc' else ''}>Rent low to high</option></select></div>"
                    "<button class='primary-btn' type='submit'>Apply</button>"
                    "<a class='ghost-btn' href='/manager/rent-roll'>Reset</a>"
                    "</form></div>"
                )
                summary_cards = (
                    "<div class='card' style='margin-bottom:10px;'><div class='grid-3'>"
                    f"<div class='stat'><div class='muted'>Current</div><div class='stat-num'>{current_cnt}</div></div>"
                    f"<div class='stat'><div class='muted'>Late</div><div class='stat-num'>{late_cnt}</div></div>"
                    f"<div class='stat'><div class='muted'>Vacant</div><div class='stat-num'>{vacant_cnt}</div></div>"
                    "</div></div>"
                )
                return send_html(self,render("manager_rent_roll.html",title="Rent Roll",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),filters_form=filters_form,summary_cards=summary_cards,rent_roll_rows=rent_roll_rows,pager_box=pager_html("/manager/rent-roll", q2, page, per, total)))
            if path=="/manager/properties":
                if not self._req_action(u, "manager.property.manage"): return
                search=((q.get("q") or [""])[0]).strip().lower()
                c=db()
                sql_props="SELECT * FROM properties WHERE owner_account=? "
                args_props=[u["account_number"]]
                if search:
                    s="%" + search + "%"
                    sql_props += "AND (LOWER(COALESCE(id,'')) LIKE ? OR LOWER(COALESCE(name,'')) LIKE ? OR LOWER(COALESCE(location,'')) LIKE ?) "
                    args_props.extend([s, s, s])
                sql_props += "ORDER BY created_at DESC"
                props=c.execute(sql_props, tuple(args_props)).fetchall()
                occ_row = c.execute(
                    "SELECT COUNT(1) AS n FROM units uu JOIN properties p ON p.id=uu.property_id "
                    "WHERE p.owner_account=? AND uu.is_occupied=1",
                    (u["account_number"],),
                ).fetchone()
                pen_row = c.execute(
                    "SELECT COUNT(1) AS n FROM listing_requests lr JOIN properties p ON p.id=lr.property_id "
                    "WHERE p.owner_account=? AND lr.status='pending'",
                    (u["account_number"],),
                ).fetchone()
                c.close()
                total_props = len(props)
                total_units = sum(to_int(p["units_count"], 0) for p in props)
                occupied_units = to_int(occ_row["n"], 0) if occ_row else 0
                pending_submissions = to_int(pen_row["n"], 0) if pen_row else 0
                portfolio_summary = (
                    "<div class='card' style='margin-bottom:12px;'>"
                    "<div class='grid-3'>"
                    f"<div class='stat'><div class='muted'>Registered Properties</div><div class='stat-num'>{total_props}</div></div>"
                    f"<div class='stat'><div class='muted'>Units (Occupied / Total)</div><div class='stat-num'>{occupied_units} / {total_units}</div></div>"
                    f"<div class='stat'><div class='muted'>Pending Listing Reviews</div><div class='stat-num'>{pending_submissions}</div></div>"
                    "</div>"
                    "</div>"
                )
                filters_form = (
                    "<div class='card' style='margin-bottom:12px;'>"
                    "<form method='GET' action='/manager/properties' class='row' style='align-items:flex-end;'>"
                    f"<div class='field' style='min-width:260px;flex:1;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='property id, name, location'></div>"
                    "<button class='secondary-btn' type='submit'>Apply</button>"
                    "<a class='ghost-btn' href='/manager/properties'>Reset</a>"
                    "</form>"
                    "</div>"
                )
                cards=""
                for p in props:
                    cards += (
                        f'<a class="prop-item" href="/landlord/property/{esc(p["id"])}" style="text-decoration:none;">'
                        '<div class="thumb"></div>'
                        f'<div><div style="font-weight:1000;">{esc(p["name"])}</div>'
                        f'<div class="muted" style="font-size:12px;">{esc(p["location"])} - {esc(p["property_type"])} - {p["units_count"]} units</div>'
                        f'<div class="muted" style="font-size:12px;">ID: <b>{esc(p["id"])}</b></div></div>'
                        '<div class="badge">Registered</div>'
                        '</a>'
                    )
                np=""if props else'<div class="card"><p class="muted">No properties yet.</p></div>'
                return send_html(self,render("manager_properties.html",title="Manager Properties",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q),properties_cards=cards,no_properties=np,portfolio_summary=portfolio_summary,filters_form=filters_form))
            if path=="/manager/property/new":
                if not self._req_action(u, "manager.property.manage"): return
                return send_html(self,render("manager_property_new.html",title="Register Property",nav_right=nr,nav_menu=nav_menu(u,path),error_box=""))
            if path=="/manager/leases":
                if not self._req_action(u, "manager.leases.manage"): return
                status_filter=((q.get("status") or ["all"])[0]).strip().lower()
                if status_filter not in ("all", "active", "inactive"):
                    status_filter = "all"
                prop_filter=((q.get("property") or [""])[0]).strip()
                search=((q.get("q") or [""])[0]).strip().lower()
                sort=((q.get("sort") or ["newest"])[0]).strip().lower()
                order_sql = "l.created_at ASC,l.id ASC" if sort=="oldest" else "l.created_at DESC,l.id DESC"
                page, per, offset = parse_page_params(q, default_per=30, max_per=200)
                c=db()
                base_sql = (
                    "SELECT l.*, u.full_name AS tenant_name "
                    "FROM tenant_leases l "
                    "JOIN properties p ON p.id=l.property_id "
                    "LEFT JOIN users u ON u.account_number=l.tenant_account "
                    "WHERE p.owner_account=? "
                )
                args=[u["account_number"]]
                if status_filter == "active":
                    base_sql += "AND l.is_active=1 "
                elif status_filter == "inactive":
                    base_sql += "AND l.is_active=0 "
                if prop_filter:
                    base_sql += "AND l.property_id=? "
                    args.append(prop_filter)
                if search:
                    s="%" + search + "%"
                    base_sql += "AND (LOWER(COALESCE(u.full_name,'')) LIKE ? OR LOWER(COALESCE(l.tenant_account,'')) LIKE ? OR LOWER(COALESCE(l.unit_label,'')) LIKE ?) "
                    args.extend([s, s, s])
                total = c.execute("SELECT COUNT(1) AS n FROM (" + base_sql + ") t", tuple(args)).fetchone()["n"]
                leases=c.execute(base_sql + f"ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(args + [per, offset])).fetchall()
                tenants=c.execute("SELECT account_number,full_name FROM users WHERE role='tenant' ORDER BY created_at DESC").fetchall()
                props=c.execute("SELECT id,name FROM properties WHERE owner_account=? ORDER BY created_at DESC",(u["account_number"],)).fetchall()
                c.close()
                c_docs = db()
                to="".join(f'<option value="{esc(t["account_number"])}">{esc(t["full_name"])} ({esc(t["account_number"])})</option>'for t in tenants)
                po="".join(f'<option value="{esc(p["id"])}">{esc(p["name"])} ({esc(p["id"])})</option>'for p in props)
                po_filter="".join(f"<option value='{esc(p['id'])}' {'selected' if prop_filter==p['id'] else ''}>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
                roommate_lease_options = ""
                lr=""
                for l in leases:
                    active = 1 if to_int(l["is_active"], 0) else 0
                    status = '<span class="badge ok">active</span>' if active else '<span class="badge">inactive</span>'
                    lease_doc = lease_doc_for_lease(c_docs, l["id"])
                    doc_cell = f"<a class='ghost-btn' href='{esc(lease_doc['path'])}' target='_blank' rel='noopener'>View PDF</a>" if lease_doc else "<span class='muted'>-</span>"
                    rm_stats = c_docs.execute(
                        "SELECT COUNT(1) AS cnt,COALESCE(SUM(share_percent),0) AS pct FROM lease_roommates WHERE lease_id=? AND status='active'",
                        (l["id"],),
                    ).fetchone()
                    rm_cnt = to_int(rm_stats["cnt"], 0) if rm_stats else 0
                    rm_pct = max(0, min(100, to_int(rm_stats["pct"], 0) if rm_stats else 0))
                    primary_pct = max(0, 100 - rm_pct)
                    split_cell = f"{primary_pct}% primary" + (f" + {rm_cnt} roommate(s)" if rm_cnt else "")
                    mgr_signed = (l["manager_signed_at"] or "").strip() if "manager_signed_at" in l.keys() else ""
                    ten_signed = (l["tenant_signed_at"] or "").strip() if "tenant_signed_at" in l.keys() else ""
                    esign_cell = (
                        f"<div class='muted'>Manager: {esc(mgr_signed or 'pending')}</div>"
                        f"<div class='muted'>Tenant: {esc(ten_signed or 'pending')}</div>"
                    )
                    actions = (
                        "<form method='POST' action='/manager/leases/end' style='margin:0;'>"
                        f"<input type='hidden' name='lease_id' value='{l['id']}'>"
                        "<button class='ghost-btn' type='submit'>End Lease</button>"
                        "</form>"
                    ) if active else "<span class='muted'>-</span>"
                    if active:
                        roommate_lease_options += (
                            f"<option value='{l['id']}'>"
                            f"#{l['id']} - {esc(l['property_id'])} / {esc(l['unit_label'])} ({esc(l['tenant_name'] or l['tenant_account'])})"
                            "</option>"
                        )
                    lr += (
                        "<tr>"
                        f"<td>{esc(l['tenant_name'] or l['tenant_account'])}</td>"
                        f"<td>{esc(l['property_id'])}</td>"
                        f"<td>{esc(l['unit_label'])}</td>"
                        f"<td>{esc(l['start_date'])}</td>"
                        f"<td>{esc(l['end_date'] or '-')}</td>"
                        f"<td>{status}</td>"
                        f"<td>{esc(split_cell)}</td>"
                        f"<td>{esign_cell}</td>"
                        f"<td>{doc_cell}</td>"
                        f"<td>{actions}</td>"
                        "</tr>"
                    )
                roommates = c_docs.execute(
                    "SELECT rm.id,rm.lease_id,rm.tenant_account,rm.share_percent,rm.status,uu.full_name AS tenant_name,"
                    "l.property_id,l.unit_label "
                    "FROM lease_roommates rm "
                    "JOIN tenant_leases l ON l.id=rm.lease_id "
                    "JOIN properties p ON p.id=l.property_id "
                    "LEFT JOIN users uu ON uu.account_number=rm.tenant_account "
                    "WHERE p.owner_account=? "
                    "ORDER BY rm.id DESC LIMIT 200",
                    (u["account_number"],),
                ).fetchall()
                c_docs.close()
                roommate_rows = ""
                for rm in roommates:
                    rm_action = "<span class='muted'>-</span>"
                    if (rm["status"] or "").strip().lower() == "active":
                        rm_action = (
                            "<form method='POST' action='/manager/roommates/remove' style='margin:0;'>"
                            f"<input type='hidden' name='roommate_id' value='{rm['id']}'>"
                            "<button class='ghost-btn' type='submit'>Remove</button>"
                            "</form>"
                        )
                    roommate_rows += (
                        "<tr>"
                        f"<td>#{rm['lease_id']} - {esc(rm['property_id'])} / {esc(rm['unit_label'])}</td>"
                        f"<td>{esc(rm['tenant_name'] or rm['tenant_account'])}</td>"
                        f"<td>{to_int(rm['share_percent'],0)}</td>"
                        f"<td>{status_badge(rm['status'],'review')}</td>"
                        f"<td>{rm_action}</td>"
                        "</tr>"
                    )
                if not roommate_rows:
                    roommate_rows = "<tr><td colspan='5' class='muted'>No roommate splits created yet.</td></tr>"
                if not roommate_lease_options:
                    roommate_lease_options = "<option value=''>No active leases</option>"
                if not lr:
                    lr = "<tr><td colspan='10' class='muted'>No leases found for this filter.</td></tr>"
                filters_form = (
                    "<div class='card' style='margin:10px 0;'>"
                    "<form method='GET' action='/manager/leases' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:160px;'><label>Status</label>"
                    f"<select name='status'><option value='all' {'selected' if status_filter=='all' else ''}>All</option><option value='active' {'selected' if status_filter=='active' else ''}>active</option><option value='inactive' {'selected' if status_filter=='inactive' else ''}>inactive</option></select></div>"
                    "<div class='field' style='min-width:220px;'><label>Property</label>"
                    f"<select name='property'><option value=''>All</option>{po_filter}</select></div>"
                    f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='tenant/unit'></div>"
                    "<div class='field' style='min-width:150px;'><label>Sort</label>"
                    f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                    "<button class='primary-btn' type='submit'>Apply</button>"
                    "<a class='ghost-btn' href='/manager/leases'>Reset</a>"
                    "</form>"
                    "</div>"
                )
                return send_html(self,render("manager_leases.html",title="Assign Leases",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q),filters_form=filters_form,pager_box=pager_html("/manager/leases", q, page, per, total),tenant_options=to,property_options=po,leases_rows=lr,roommate_lease_options=roommate_lease_options,roommate_rows=roommate_rows,scripts='<script src="/static/js/leases.js"></script>'))
            if path=="/manager/inspections":
                if not self._req_action(u, "manager.ops.update"): return
                status_filter=((q.get("status") or ["all"])[0]).strip().lower()
                if status_filter not in ("all","scheduled","completed","cancelled"):
                    status_filter="all"
                type_filter=((q.get("type") or [""])[0]).strip().lower()
                if type_filter not in ("","move_in","move_out"):
                    type_filter=""
                prop_filter=((q.get("property") or [""])[0]).strip()
                search=((q.get("q") or [""])[0]).strip().lower()
                sort=((q.get("sort") or ["newest"])[0]).strip().lower()
                order_sql = "i.scheduled_date ASC,i.id ASC" if sort=="oldest" else "i.scheduled_date DESC,i.id DESC"
                page, per, offset = parse_page_params(q, default_per=25, max_per=200)
                c=db()
                props = c.execute(
                    "SELECT id,name FROM properties " + ("" if u["role"]=="admin" else "WHERE owner_account=? ") + "ORDER BY created_at DESC",
                    tuple() if u["role"]=="admin" else (u["account_number"],),
                ).fetchall()
                base_sql = "FROM inspections i JOIN properties p ON p.id=i.property_id WHERE 1=1 "
                args=[]
                if u["role"] != "admin":
                    base_sql += "AND p.owner_account=? "
                    args.append(u["account_number"])
                if status_filter != "all":
                    base_sql += "AND i.status=? "
                    args.append(status_filter)
                if type_filter:
                    base_sql += "AND i.inspection_type=? "
                    args.append(type_filter)
                if prop_filter:
                    base_sql += "AND i.property_id=? "
                    args.append(prop_filter)
                if search:
                    s = "%" + search + "%"
                    base_sql += "AND (LOWER(COALESCE(i.property_id,'')) LIKE ? OR LOWER(COALESCE(i.unit_label,'')) LIKE ? OR LOWER(COALESCE(i.tenant_account,'')) LIKE ? OR LOWER(COALESCE(i.report_notes,'')) LIKE ?) "
                    args.extend([s, s, s, s])
                total = c.execute("SELECT COUNT(1) AS n " + base_sql, tuple(args)).fetchone()["n"]
                rows_db = c.execute(
                    "SELECT i.* " + base_sql + f"ORDER BY {order_sql} LIMIT ? OFFSET ?",
                    tuple(args + [per, offset]),
                ).fetchall()
                c.close()
                rows = ""
                for r in rows_db:
                    st=(r["status"] or "scheduled").strip().lower()
                    ss='selected' if st=="scheduled" else ""
                    sc='selected' if st=="completed" else ""
                    sx='selected' if st=="cancelled" else ""
                    ck={}
                    try:
                        ck = json.loads(r["checklist_json"] or "{}")
                        if not isinstance(ck, dict):
                            ck = {}
                    except Exception:
                        ck={}
                    ck_items = ", ".join(k.replace("_"," ") for k, v in ck.items() if v) or "-"
                    report_col = f"<div class='muted'>{esc(ck_items)}</div><div class='muted'>{esc(r['report_notes'] or '')}</div>"
                    c1 = "checked" if ck.get("smoke_alarm") else ""
                    c2 = "checked" if ck.get("walls") else ""
                    c3 = "checked" if ck.get("floors") else ""
                    c4 = "checked" if ck.get("fixtures") else ""
                    rows += (
                        "<tr>"
                        f"<td>#{r['id']}</td>"
                        f"<td>{esc(r['inspection_type'])}</td>"
                        f"<td>{esc(r['property_id'])}</td>"
                        f"<td>{esc(r['unit_label'])}</td>"
                        f"<td>{esc(r['tenant_account'] or '-')}</td>"
                        f"<td>{esc(r['scheduled_date'])}</td>"
                        f"<td>{status_badge(st,'review')}</td>"
                        f"<td>{report_col}</td>"
                        "<td>"
                        "<form method='POST' action='/manager/inspections/update' style='display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;'>"
                        f"<input type='hidden' name='inspection_id' value='{r['id']}'>"
                        f"<select name='status'><option value='scheduled' {ss}>scheduled</option><option value='completed' {sc}>completed</option><option value='cancelled' {sx}>cancelled</option></select>"
                        "<label class='muted' style='display:flex;align-items:center;gap:4px;'><input type='checkbox' name='chk_smoke_alarm' value='1' " + c1 + ">smoke</label>"
                        "<label class='muted' style='display:flex;align-items:center;gap:4px;'><input type='checkbox' name='chk_walls' value='1' " + c2 + ">walls</label>"
                        "<label class='muted' style='display:flex;align-items:center;gap:4px;'><input type='checkbox' name='chk_floors' value='1' " + c3 + ">floors</label>"
                        "<label class='muted' style='display:flex;align-items:center;gap:4px;'><input type='checkbox' name='chk_fixtures' value='1' " + c4 + ">fixtures</label>"
                        f"<input name='report_notes' value='{esc((r['report_notes'] or '')[:500])}' placeholder='Report notes' style='min-width:220px;'>"
                        "<button class='secondary-btn' type='submit'>Save</button>"
                        "</form>"
                        "</td>"
                        "</tr>"
                    )
                if not rows:
                    rows = "<tr><td colspan='9' class='muted'>No inspections found.</td></tr>"
                property_options = "".join(f"<option value='{esc(p['id'])}'>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
                prop_opts = "".join(f"<option value='{esc(p['id'])}' {'selected' if prop_filter==p['id'] else ''}>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
                filters_form = (
                    "<div class='card' style='margin-bottom:10px;'>"
                    "<form method='GET' action='/manager/inspections' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:150px;'><label>Status</label>"
                    f"<select name='status'><option value='all' {'selected' if status_filter=='all' else ''}>All</option><option value='scheduled' {'selected' if status_filter=='scheduled' else ''}>scheduled</option><option value='completed' {'selected' if status_filter=='completed' else ''}>completed</option><option value='cancelled' {'selected' if status_filter=='cancelled' else ''}>cancelled</option></select></div>"
                    "<div class='field' style='min-width:150px;'><label>Type</label>"
                    f"<select name='type'><option value=''>All</option><option value='move_in' {'selected' if type_filter=='move_in' else ''}>move_in</option><option value='move_out' {'selected' if type_filter=='move_out' else ''}>move_out</option></select></div>"
                    "<div class='field' style='min-width:220px;'><label>Property</label>"
                    f"<select name='property'><option value=''>All</option>{prop_opts}</select></div>"
                    f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='property/unit/tenant'></div>"
                    "<div class='field' style='min-width:150px;'><label>Sort</label>"
                    f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                    "<button class='primary-btn' type='submit'>Apply</button><a class='ghost-btn' href='/manager/inspections'>Reset</a>"
                    "</form></div>"
                )
                return send_html(self,render("manager_inspections.html",title="Inspections",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q),property_options=property_options,filters_form=filters_form,rows=rows,pager_box=pager_html("/manager/inspections", q, page, per, total)))
            if path=="/manager/preventive":
                if not self._req_action(u, "manager.ops.update"): return
                status_filter=((q.get("status") or ["all"])[0]).strip().lower()
                if status_filter not in ("all","open","completed","cancelled","overdue"):
                    status_filter="all"
                prop_filter=((q.get("property") or [""])[0]).strip()
                search=((q.get("q") or [""])[0]).strip().lower()
                page, per, offset = parse_page_params(q, default_per=25, max_per=200)
                c=db()
                props = c.execute(
                    "SELECT id,name FROM properties " + ("" if u["role"]=="admin" else "WHERE owner_account=? ") + "ORDER BY created_at DESC",
                    tuple() if u["role"]=="admin" else (u["account_number"],),
                ).fetchall()
                staff_rows = c.execute("SELECT id,name FROM maintenance_staff WHERE is_active=1 ORDER BY name,id").fetchall()
                base_sql = (
                    "FROM preventive_tasks t "
                    "JOIN properties p ON p.id=t.property_id "
                    "LEFT JOIN maintenance_staff s ON s.id=t.assigned_staff_id "
                    "WHERE 1=1 "
                )
                args=[]
                if u["role"] != "admin":
                    base_sql += "AND p.owner_account=? "
                    args.append(u["account_number"])
                if status_filter == "overdue":
                    base_sql += "AND t.status='open' AND date(t.next_due_date)<date('now') "
                elif status_filter != "all":
                    base_sql += "AND t.status=? "
                    args.append(status_filter)
                if prop_filter:
                    base_sql += "AND t.property_id=? "
                    args.append(prop_filter)
                if search:
                    s = "%" + search + "%"
                    base_sql += "AND (LOWER(COALESCE(t.task,'')) LIKE ? OR LOWER(COALESCE(t.unit_label,'')) LIKE ? OR LOWER(COALESCE(t.property_id,'')) LIKE ?) "
                    args.extend([s, s, s])
                total = c.execute("SELECT COUNT(1) AS n " + base_sql, tuple(args)).fetchone()["n"]
                rows_db = c.execute(
                    "SELECT t.*,s.name AS staff_name " + base_sql + "ORDER BY date(t.next_due_date) ASC,t.id DESC LIMIT ? OFFSET ?",
                    tuple(args + [per, offset]),
                ).fetchall()
                c.close()
                rows=""
                for r in rows_db:
                    st=(r["status"] or "open").strip()
                    so='selected' if st=="open" else ""
                    sc='selected' if st=="completed" else ""
                    sx='selected' if st=="cancelled" else ""
                    overdue_badge = " <span class='badge no'>overdue</span>" if st=="open" and (r["next_due_date"] or "") < datetime.now(timezone.utc).strftime("%Y-%m-%d") else ""
                    rows += (
                        "<tr>"
                        f"<td>#{r['id']}</td>"
                        f"<td>{esc(r['property_id'])}</td>"
                        f"<td>{esc(r['unit_label'] or '-')}</td>"
                        f"<td>{esc(r['task'])}</td>"
                        f"<td>{to_int(r['frequency_days'],0)}d</td>"
                        f"<td>{esc(r['next_due_date'])}{overdue_badge}</td>"
                        f"<td>{esc(r['staff_name'] or '-')}</td>"
                        f"<td>{esc(st)}</td>"
                        "<td>"
                        "<form method='POST' action='/manager/preventive/update' style='display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;'>"
                        f"<input type='hidden' name='task_id' value='{r['id']}'>"
                        f"<select name='status'><option value='open' {so}>open</option><option value='completed' {sc}>completed</option><option value='cancelled' {sx}>cancelled</option></select>"
                        f"<input type='date' name='next_due_date' value='{esc(r['next_due_date'])}'>"
                        "<button class='secondary-btn' type='submit'>Save</button>"
                        "</form>"
                        "</td>"
                        "</tr>"
                    )
                if not rows:
                    rows = "<tr><td colspan='9'>" + empty_state("P", "No Preventive Tasks", "No preventive tasks matched this filter.") + "</td></tr>"
                property_options = "".join(f"<option value='{esc(p['id'])}'>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
                prop_opts = "".join(f"<option value='{esc(p['id'])}' {'selected' if prop_filter==p['id'] else ''}>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
                staff_options = "".join(f"<option value='{r['id']}'>{esc(r['name'])}</option>" for r in staff_rows)
                filters_form = (
                    "<div class='card' style='margin-bottom:10px;'>"
                    "<form method='GET' action='/manager/preventive' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:170px;'><label>Status</label>"
                    f"<select name='status'><option value='all' {'selected' if status_filter=='all' else ''}>All</option><option value='open' {'selected' if status_filter=='open' else ''}>open</option><option value='completed' {'selected' if status_filter=='completed' else ''}>completed</option><option value='cancelled' {'selected' if status_filter=='cancelled' else ''}>cancelled</option><option value='overdue' {'selected' if status_filter=='overdue' else ''}>overdue</option></select></div>"
                    "<div class='field' style='min-width:220px;'><label>Property</label>"
                    f"<select name='property'><option value=''>All</option>{prop_opts}</select></div>"
                    f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='task/property/unit'></div>"
                    "<button class='primary-btn' type='submit'>Apply</button><a class='ghost-btn' href='/manager/preventive'>Reset</a>"
                    "</form></div>"
                )
                return send_html(self,render("manager_preventive.html",title="Preventive Maintenance",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q),property_options=property_options,staff_options=staff_options,filters_form=filters_form,rows=rows,pager_box=pager_html("/manager/preventive", q, page, per, total)))
            if path=="/manager/batch-notify":
                if not self._req_action(u, "manager.ops.update"): return
                c=db()
                props = c.execute(
                    "SELECT id,name FROM properties " + ("" if u["role"]=="admin" else "WHERE owner_account=? ") + "ORDER BY created_at DESC",
                    tuple() if u["role"]=="admin" else (u["account_number"],),
                ).fetchall()
                c.close()
                property_options = "".join(f"<option value='{esc(p['id'])}'>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
                return send_html(self,render("manager_batch_notify.html",title="Mass Notifications",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q),property_options=property_options))
            if path=="/manager/inspections/export":
                if not self._req_action(u, "manager.ops.update"): return
                c=db()
                sql = (
                    "SELECT i.id,i.property_id,i.unit_label,i.tenant_account,i.inspection_type,i.scheduled_date,i.status,"
                    "i.checklist_json,i.report_notes,i.completed_at,i.created_at "
                    "FROM inspections i JOIN properties p ON p.id=i.property_id WHERE 1=1 "
                )
                args=[]
                if u["role"] != "admin":
                    sql += "AND p.owner_account=? "
                    args.append(u["account_number"])
                rows_db = c.execute(sql + "ORDER BY i.id DESC LIMIT 5000", tuple(args)).fetchall()
                c.close()
                rows=[["id","property_id","unit_label","tenant_account","inspection_type","scheduled_date","status","checklist","report_notes","completed_at","created_at"]]
                for r in rows_db:
                    rows.append([r["id"],r["property_id"],r["unit_label"],r["tenant_account"],r["inspection_type"],r["scheduled_date"],r["status"],r["checklist_json"] or "",r["report_notes"] or "",r["completed_at"] or "",r["created_at"]])
                return send_csv(self, "manager_inspections.csv", rows)
            if path=="/manager/maintenance":
                status_filter = ((q.get("status") or ["all"])[0]).strip().lower()
                if status_filter not in ("all", "open", "in_progress", "closed"):
                    status_filter = "all"
                search = ((q.get("q") or [""])[0]).strip().lower()
                c=db()
                if u["role"] == "admin":
                    base_sql = "FROM maintenance_requests m WHERE 1=1"
                    base_args = []
                else:
                    base_sql = (
                        "FROM maintenance_requests m "
                        "LEFT JOIN tenant_leases l ON l.tenant_account=m.tenant_account AND l.is_active=1 "
                        "LEFT JOIN properties p ON p.id=l.property_id "
                        "WHERE p.owner_account=?"
                    )
                    base_args = [u["account_number"]]
                cnt_open = to_int(c.execute("SELECT COUNT(1) AS n " + base_sql + " AND m.status='open'", tuple(base_args)).fetchone()["n"], 0)
                cnt_prog = to_int(c.execute("SELECT COUNT(1) AS n " + base_sql + " AND m.status='in_progress'", tuple(base_args)).fetchone()["n"], 0)
                cnt_closed = to_int(c.execute("SELECT COUNT(1) AS n " + base_sql + " AND m.status='closed'", tuple(base_args)).fetchone()["n"], 0)
                sql = "SELECT m.*, CAST(julianday('now') - julianday(m.created_at) AS INT) AS age_days " + base_sql
                args = list(base_args)
                if status_filter != "all":
                    sql += " AND m.status=?"
                    args.append(status_filter)
                if search:
                    s = "%" + search + "%"
                    sql += " AND (CAST(m.id AS TEXT) LIKE ? OR LOWER(COALESCE(m.tenant_account,'')) LIKE ? OR LOWER(COALESCE(m.description,'')) LIKE ? OR LOWER(COALESCE(m.assigned_to,'')) LIKE ?)"
                    args.extend([s, s, s, s])
                sql += " ORDER BY m.created_at DESC, m.id DESC LIMIT 300"
                rows=c.execute(sql, tuple(args)).fetchall()
                staff_rows = c.execute("SELECT id,name,email,phone FROM maintenance_staff WHERE is_active=1 ORDER BY name,id").fetchall()
                photo_rows = c.execute(
                    "SELECT related_id,path FROM uploads WHERE kind='maintenance_photo' AND related_table='maintenance_requests' ORDER BY id DESC"
                ).fetchall()
                thread_rows = c.execute(
                    "SELECT id,context_id FROM message_threads WHERE context_type='maintenance' ORDER BY id DESC"
                ).fetchall()
                c.close()
                photo_map = {}
                for ph in photo_rows:
                    rid = to_int(ph["related_id"], 0)
                    if rid <= 0 or rid in photo_map:
                        continue
                    photo_map[rid] = ph["path"]
                thread_map = {}
                for trw in thread_rows:
                    rid = to_int(trw["context_id"], 0)
                    if rid <= 0 or rid in thread_map:
                        continue
                    thread_map[rid] = to_int(trw["id"], 0)
                view_links = (
                    "<div class='row' style='margin-bottom:10px;'>"
                    f"<a class='{'primary-btn' if status_filter=='all' else 'ghost-btn'}' href='/manager/maintenance'>All ({cnt_open+cnt_prog+cnt_closed})</a>"
                    f"<a class='{'primary-btn' if status_filter=='open' else 'ghost-btn'}' href='/manager/maintenance?status=open'>Open ({cnt_open})</a>"
                    f"<a class='{'primary-btn' if status_filter=='in_progress' else 'ghost-btn'}' href='/manager/maintenance?status=in_progress'>In Progress ({cnt_prog})</a>"
                    f"<a class='{'primary-btn' if status_filter=='closed' else 'ghost-btn'}' href='/manager/maintenance?status=closed'>Closed ({cnt_closed})</a>"
                    "<form method='GET' action='/manager/maintenance' class='row' style='margin-left:auto;align-items:flex-end;'>"
                    f"<input type='hidden' name='status' value='{esc(status_filter)}'>"
                    f"<input name='q' value='{esc(search)}' placeholder='id/tenant/description' style='max-width:240px;'>"
                    "<button class='ghost-btn' type='submit'>Search</button>"
                    "</form>"
                    "</div>"
                )
                staff_summary = ("<div class='muted' style='margin-top:8px;'>Active staff: " + ", ".join(esc(s["name"]) for s in staff_rows) + "</div>") if staff_rows else "<div class='muted' style='margin-top:8px;'>No active staff yet.</div>"
                staff_tools = (
                    "<div class='card' style='margin-bottom:10px;'>"
                    "<h3 style='margin-top:0;'>Maintenance Staff</h3>"
                    "<form method='POST' action='/manager/staff/new' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='flex:1;min-width:180px;'><label>Name</label><input name='name' required placeholder='Technician name'></div>"
                    "<div class='field' style='flex:1;min-width:180px;'><label>Email (optional)</label><input name='email' placeholder='tech@atlasbahamas.local'></div>"
                    "<div class='field' style='flex:1;min-width:160px;'><label>Phone (optional)</label><input name='phone' placeholder='242...'></div>"
                    "<button class='secondary-btn' type='submit'>Add Staff</button>"
                    "</form>"
                    + staff_summary +
                    "</div>"
                )
                tr=""
                for r in rows:
                    urgency = (r["urgency"] or "").strip().lower() if "urgency" in r.keys() else ""
                    if urgency in ("normal", "high", "emergency"):
                        priority = urgency
                    else:
                        text = (r["description"] or "").lower()
                        if any(k in text for k in ("urgent", "security", "electrical", "fire", "flood", "smoke")):
                            priority = "high"
                        elif any(k in text for k in ("plumbing", "hvac", "appliance", "leak")):
                            priority = "medium"
                        else:
                            priority = "normal"
                    age_days = max(0, to_int(r["age_days"], 0))
                    so='selected'if r["status"]=="open"else"";sp='selected'if r["status"]=="in_progress"else"";sc='selected'if r["status"]=="closed"else""
                    photo = photo_map.get(to_int(r["id"], 0))
                    photo_html = f"<div style='margin-top:6px;'><a class='ghost-btn' href='{esc(photo)}' target='_blank' rel='noopener'>Photo</a></div>" if photo else ""
                    staff_opts = "<option value=''>Select staff...</option>"
                    for s in staff_rows:
                        sel = "selected" if (r["assigned_to"] or "").strip().lower() == (s["name"] or "").strip().lower() else ""
                        staff_opts += f"<option value='{s['id']}' {sel}>{esc(s['name'])}</option>"
                    pri_cls = "badge no" if priority == "emergency" else ("badge" if priority in ("high", "medium") else "badge ok")
                    tid = to_int(thread_map.get(to_int(r["id"], 0)), 0)
                    thread_action = (
                        f"<a class='ghost-btn' href='/messages?thread={tid}'>Thread</a>"
                        if tid > 0 else
                        "<form method='POST' action='/manager/maintenance/thread' style='margin:0;'>"
                        f"<input type='hidden' name='request_id' value='{r['id']}'>"
                        "<button class='ghost-btn' type='submit'>Start Thread</button>"
                        "</form>"
                    )
                    tr+=(
                        f"<tr><td>#{r['id']}</td><td>{esc(r['tenant_account'])}</td><td><span class='{pri_cls}'>{esc(priority)}</span></td><td>{age_days}d</td><td>{status_badge(r['status'],'maintenance')}</td>"
                        f"<td>{esc(r['assigned_to']or'')}</td><td>{esc(r['description'])}{photo_html}</td>"
                        "<td><form method='POST' action='/manager/maintenance/update' style='display:flex;gap:8px;flex-wrap:wrap;'>"
                        f"<input type='hidden' name='request_id' value='{r['id']}'>"
                        f"<select name='status'><option value='open' {so}>open</option><option value='in_progress' {sp}>in_progress</option><option value='closed' {sc}>closed</option></select>"
                        f"<select name='staff_id'>{staff_opts}</select>"
                        f"<input name='assigned_to' placeholder='Technician' value='{esc(r['assigned_to']or'')}' style='max-width:220px;'>"
                        "<button class='secondary-btn' type='submit'>Save</button></form>"
                        f"<div style='margin-top:6px;'>{thread_action}</div>"
                        "</td></tr>"
                    )
                if not tr:
                    tr = "<tr><td colspan='8' class='muted'>No maintenance requests found.</td></tr>"
                return send_html(self,render("manager_maintenance.html",title="Maintenance",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q),maintenance_rows=tr,view_links=view_links,staff_tools=staff_tools))
            if path=="/manager/checks":
                status_filter = ((q.get("status") or ["all"])[0]).strip().lower()
                if status_filter not in ("all", "requested", "scheduled", "completed", "cancelled"):
                    status_filter = "all"
                c=db()
                if u["role"] == "admin":
                    base_sql = "FROM property_checks pc WHERE 1=1"
                    base_args = []
                else:
                    base_sql = "FROM property_checks pc JOIN properties p ON p.id=pc.property_id WHERE p.owner_account=?"
                    base_args = [u["account_number"]]
                cnt_req = to_int(c.execute("SELECT COUNT(1) AS n " + base_sql + " AND pc.status='requested'", tuple(base_args)).fetchone()["n"], 0)
                cnt_sched = to_int(c.execute("SELECT COUNT(1) AS n " + base_sql + " AND pc.status='scheduled'", tuple(base_args)).fetchone()["n"], 0)
                cnt_done = to_int(c.execute("SELECT COUNT(1) AS n " + base_sql + " AND pc.status='completed'", tuple(base_args)).fetchone()["n"], 0)
                cnt_cancel = to_int(c.execute("SELECT COUNT(1) AS n " + base_sql + " AND pc.status='cancelled'", tuple(base_args)).fetchone()["n"], 0)
                sql = "SELECT pc.* " + base_sql
                args = list(base_args)
                if status_filter != "all":
                    sql += " AND pc.status=?"
                    args.append(status_filter)
                sql += " ORDER BY pc.created_at DESC, pc.id DESC LIMIT 400"
                rows=c.execute(sql, tuple(args)).fetchall()
                tr=""
                for r in rows:
                    st=(r["status"] or "requested").strip()
                    sr='selected' if st=="requested" else ""
                    ss='selected' if st=="scheduled" else ""
                    sc='selected' if st=="completed" else ""
                    sx='selected' if st=="cancelled" else ""
                    tr += (
                        "<tr>"
                        f"<td>#{r['id']}</td>"
                        f"<td>{esc(r['requester_account'])}</td>"
                        f"<td>{esc(r['property_id'])}</td>"
                        f"<td>{esc(r['preferred_date'])}</td>"
                        f"<td>{esc(r['notes'] or '')}</td>"
                        f"<td>{status_badge(st,'review')}</td>"
                        "<td>"
                        "<form method='POST' action='/manager/checks/update' style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;'>"
                        f"<input type='hidden' name='check_id' value='{r['id']}'>"
                        f"<select name='status'><option value='requested' {sr}>requested</option><option value='scheduled' {ss}>scheduled</option><option value='completed' {sc}>completed</option><option value='cancelled' {sx}>cancelled</option></select>"
                        "<button class='secondary-btn' type='submit'>Save</button>"
                        "</form>"
                        "</td>"
                        "</tr>"
                    )
                c.close()
                if not tr:
                    tr = "<tr><td colspan='7'>" + empty_state("C", "No Property Checks", "No property check requests found for this view.") + "</td></tr>"
                view_links = (
                    "<div class='row' style='margin-bottom:10px;'>"
                    f"<a class='{'primary-btn' if status_filter=='all' else 'ghost-btn'}' href='/manager/checks'>All ({cnt_req+cnt_sched+cnt_done+cnt_cancel})</a>"
                    f"<a class='{'primary-btn' if status_filter=='requested' else 'ghost-btn'}' href='/manager/checks?status=requested'>Requested ({cnt_req})</a>"
                    f"<a class='{'primary-btn' if status_filter=='scheduled' else 'ghost-btn'}' href='/manager/checks?status=scheduled'>Scheduled ({cnt_sched})</a>"
                    f"<a class='{'primary-btn' if status_filter=='completed' else 'ghost-btn'}' href='/manager/checks?status=completed'>Completed ({cnt_done})</a>"
                    f"<a class='{'primary-btn' if status_filter=='cancelled' else 'ghost-btn'}' href='/manager/checks?status=cancelled'>Cancelled ({cnt_cancel})</a>"
                    "</div>"
                )
                return send_html(self,render("manager_checks.html",title="Property Checks",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q),checks_rows=tr,view_links=view_links))
            if path=="/manager/calendar":
                c=db()
                if u["role"] == "admin":
                    check_rows = c.execute(
                        "SELECT id,property_id,preferred_date,status,notes FROM property_checks ORDER BY preferred_date ASC,id DESC LIMIT 400"
                    ).fetchall()
                    lease_rows = c.execute(
                        "SELECT id,property_id,unit_label,start_date,tenant_account,is_active FROM tenant_leases ORDER BY start_date ASC,id DESC LIMIT 400"
                    ).fetchall()
                else:
                    check_rows = c.execute(
                        "SELECT pc.id,pc.property_id,pc.preferred_date,pc.status,pc.notes "
                        "FROM property_checks pc JOIN properties p ON p.id=pc.property_id "
                        "WHERE p.owner_account=? ORDER BY pc.preferred_date ASC,pc.id DESC LIMIT 400",
                        (u["account_number"],),
                    ).fetchall()
                    lease_rows = c.execute(
                        "SELECT l.id,l.property_id,l.unit_label,l.start_date,l.tenant_account,l.is_active "
                        "FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                        "WHERE p.owner_account=? ORDER BY l.start_date ASC,l.id DESC LIMIT 400",
                        (u["account_number"],),
                    ).fetchall()
                c.close()
                events = []
                for r in check_rows:
                    dt = (r["preferred_date"] or "").strip()
                    events.append((dt, "Property Check", f"#{r['id']} - {r['property_id']} ({r['status']})", r["notes"] or ""))
                for r in lease_rows:
                    dt = (r["start_date"] or "").strip()
                    lease_state = "active" if to_int(r["is_active"], 0) else "ended"
                    events.append((dt, "Lease Start", f"#{r['id']} - {r['property_id']} / {r['unit_label']}", f"Tenant {r['tenant_account']} ({lease_state})"))

                def _event_sort_key(item):
                    try:
                        return datetime.strptime((item[0] or "")[:10], "%Y-%m-%d")
                    except Exception:
                        return datetime.max

                events.sort(key=_event_sort_key)
                if events:
                    rows = "".join(
                        "<tr>"
                        f"<td>{esc(e[0] or '-')}</td>"
                        f"<td>{esc(e[1])}</td>"
                        f"<td>{esc(e[2])}</td>"
                        f"<td>{esc(e[3] or '-')}</td>"
                        "</tr>"
                        for e in events
                    )
                    calendar_rows = "<table class='table'><thead><tr><th>Date</th><th>Type</th><th>Reference</th><th>Notes</th></tr></thead><tbody>" + rows + "</tbody></table>"
                else:
                    calendar_rows = "<div class='notice'>No calendar events found for this role.</div>"
                return send_html(self,render("manager_calendar.html",title="Calendar View",nav_right=nr,nav_menu=nav_menu(u,path),calendar_rows=calendar_rows))
            if path=="/manager/payments":
                q2=parse_qs(urlparse(self.path).query)
                status_filter=((q2.get("status") or [""])[0]).strip().lower()
                if status_filter not in ("", "submitted", "paid", "failed"):
                    status_filter = ""
                type_filter=((q2.get("type") or [""])[0]).strip().lower()
                if type_filter not in ("", "rent", "bill"):
                    type_filter = ""
                role_filter=((q2.get("role") or [""])[0]).strip().lower()
                if role_filter not in ("", "tenant", "property_manager", "landlord", "manager"):
                    role_filter = ""
                search=((q2.get("q") or [""])[0]).strip().lower()
                sort=((q2.get("sort") or ["newest"])[0]).strip().lower()
                order_sql = {
                    "oldest": "p.created_at ASC,p.id ASC",
                    "amount_desc": "p.amount DESC,p.id DESC",
                    "amount_asc": "p.amount ASC,p.id ASC",
                }.get(sort, "p.created_at DESC,p.id DESC")
                page, per, offset = parse_page_params(q2, default_per=30, max_per=200)
                c=db()
                sql = "SELECT p.* FROM payments p WHERE 1=1 "
                args = []
                if u["role"] != "admin":
                    sql += (
                        "AND ("
                        "(p.payer_role IN ('property_manager','landlord','manager') AND p.payer_account=?) "
                        "OR (p.payer_role='tenant' AND EXISTS("
                        "SELECT 1 FROM tenant_leases l JOIN properties pp ON pp.id=l.property_id "
                        "WHERE l.tenant_account=p.payer_account AND pp.owner_account=? ORDER BY l.id DESC LIMIT 1"
                        "))"
                        ") "
                    )
                    args.extend([u["account_number"], u["account_number"]])
                if status_filter:
                    sql += "AND p.status=? "
                    args.append(status_filter)
                if type_filter:
                    sql += "AND p.payment_type=? "
                    args.append(type_filter)
                if role_filter:
                    sql += "AND p.payer_role=? "
                    args.append(role_filter)
                if search:
                    s = "%" + search + "%"
                    sql += (
                        "AND (CAST(p.id AS TEXT) LIKE ? OR LOWER(COALESCE(p.payer_account,'')) LIKE ? "
                        "OR LOWER(COALESCE(p.provider,'')) LIKE ? OR LOWER(COALESCE(p.payment_type,'')) LIKE ? OR LOWER(COALESCE(p.status,'')) LIKE ?) "
                    )
                    args.extend([s, s, s, s, s])
                total = c.execute("SELECT COUNT(1) AS n FROM (" + sql + ") t", tuple(args)).fetchone()["n"]
                rows=c.execute(sql + f"ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(args + [per, offset])).fetchall()
                stats = c.execute(
                    "SELECT "
                    "COALESCE(SUM(amount),0) AS total_amt,"
                    "COALESCE(SUM(CASE WHEN status='paid' THEN amount ELSE 0 END),0) AS paid_amt,"
                    "COALESCE(SUM(CASE WHEN status='submitted' THEN amount ELSE 0 END),0) AS submitted_amt,"
                    "COALESCE(SUM(CASE WHEN status='failed' THEN amount ELSE 0 END),0) AS failed_amt "
                    "FROM (" + sql + ") fx",
                    tuple(args),
                ).fetchone()
                c.close()
                tr=""
                for p in rows:
                    st=(p["status"] or "submitted").strip()
                    ss='selected' if st=="submitted" else ""
                    sp='selected' if st=="paid" else ""
                    sf='selected' if st=="failed" else ""
                    tr += (
                        "<tr>"
                        f"<td>{esc(p['created_at'])}</td>"
                        f"<td>{esc(p['payer_account'])}</td>"
                        f"<td>{esc(p['payer_role'])}</td>"
                        f"<td>{esc(p['payment_type'])}</td>"
                        f"<td>{esc(p['provider']or'')}</td>"
                        f"<td>${p['amount']:,}</td>"
                        f"<td>{status_badge(st,'payment')}</td>"
                        "<td>"
                        "<form method='POST' action='/manager/payments/update' style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;'>"
                        f"<input type='hidden' name='payment_id' value='{p['id']}'>"
                        f"<select name='status'><option value='submitted' {ss}>submitted</option><option value='paid' {sp}>paid</option><option value='failed' {sf}>failed</option></select>"
                        "<button class='secondary-btn' type='submit'>Save</button>"
                        "</form>"
                        "</td>"
                        "</tr>"
                    )
                if not tr:
                    tr = "<tr><td colspan='8'>" + empty_state("$", "No Payments Found", "No payments matched the current filters.") + "</td></tr>"
                filters_form = (
                    "<div class='card' style='margin-bottom:10px;'>"
                    "<form method='GET' action='/manager/payments' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:140px;'><label>Status</label>"
                    f"<select name='status'><option value=''>All</option><option value='submitted' {'selected' if status_filter=='submitted' else ''}>submitted</option><option value='paid' {'selected' if status_filter=='paid' else ''}>paid</option><option value='failed' {'selected' if status_filter=='failed' else ''}>failed</option></select></div>"
                    "<div class='field' style='min-width:140px;'><label>Type</label>"
                    f"<select name='type'><option value=''>All</option><option value='rent' {'selected' if type_filter=='rent' else ''}>rent</option><option value='bill' {'selected' if type_filter=='bill' else ''}>bill</option></select></div>"
                    "<div class='field' style='min-width:140px;'><label>Payer Role</label>"
                    f"<select name='role'><option value=''>All</option><option value='tenant' {'selected' if role_filter=='tenant' else ''}>tenant</option><option value='property_manager' {'selected' if role_filter=='property_manager' else ''}>property_manager</option><option value='landlord' {'selected' if role_filter=='landlord' else ''}>landlord</option><option value='manager' {'selected' if role_filter=='manager' else ''}>manager</option></select></div>"
                    f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='id/payer/provider/status'></div>"
                    "<div class='field' style='min-width:170px;'><label>Sort</label>"
                    f"<select name='sort'><option value='newest' {'selected' if sort not in ('oldest','amount_desc','amount_asc') else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option><option value='amount_desc' {'selected' if sort=='amount_desc' else ''}>Amount high to low</option><option value='amount_asc' {'selected' if sort=='amount_asc' else ''}>Amount low to high</option></select></div>"
                    "<button class='primary-btn' type='submit'>Apply</button>"
                    "<a class='ghost-btn' href='/manager/payments'>Reset</a>"
                    "</form>"
                    "</div>"
                )
                summary_cards = (
                    "<div class='card' style='margin-bottom:10px;'><div class='grid-3'>"
                    f"<div class='stat'><div class='muted'>Paid</div><div class='stat-num'>${to_int(stats['paid_amt'],0):,}</div></div>"
                    f"<div class='stat'><div class='muted'>Submitted</div><div class='stat-num'>${to_int(stats['submitted_amt'],0):,}</div></div>"
                    f"<div class='stat'><div class='muted'>Failed</div><div class='stat-num'>${to_int(stats['failed_amt'],0):,}</div></div>"
                    "</div></div>"
                )
                pager_box = pager_html("/manager/payments", q2, page, per, total)
                export_q = urlencode(query_without_page(q2))
                export_filtered_url = "/manager/payments/export" + (f"?{export_q}" if export_q else "")
                return send_html(self,render("manager_payments.html",title="Payments",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),filters_form=filters_form,summary_cards=summary_cards,payments_rows=tr,pager_box=pager_box,export_filtered_url=export_filtered_url))
            if path=="/manager/tenants":
                return self._manager_tenants_get(u)
            if path=="/manager/listing-requests":
                if not self._req_action(u, "manager.listing.submit"): return
                st_filter=((q.get("status") or [""])[0]).strip().lower()
                if st_filter not in ("", "pending", "approved", "rejected"):
                    st_filter = ""
                prop_filter=((q.get("property") or [""])[0]).strip()
                search=((q.get("q") or [""])[0]).strip().lower()
                sort=((q.get("sort") or ["newest"])[0]).strip().lower()
                order_sql = "r.created_at ASC, r.id ASC" if sort=="oldest" else "r.created_at DESC, r.id DESC"
                page, per, offset = parse_page_params(q, default_per=30, max_per=200)
                c=db()
                base_sql=(
                    """SELECT r.*, p.name AS prop_name, uu.unit_label AS unit_label
                       FROM listing_requests r
                       LEFT JOIN properties p ON p.id=r.property_id
                       LEFT JOIN units uu ON uu.id=r.unit_id
                       WHERE (r.submitted_by_user_id=? OR p.owner_account=?) """
                )
                args=[u["id"], u["account_number"]]
                if st_filter:
                    base_sql += "AND r.status=? "
                    args.append(st_filter)
                if prop_filter:
                    base_sql += "AND r.property_id=? "
                    args.append(prop_filter)
                if search:
                    s = "%" + search + "%"
                    base_sql += "AND (LOWER(COALESCE(r.title,'')) LIKE ? OR LOWER(COALESCE(p.name,'')) LIKE ? OR LOWER(COALESCE(r.property_id,'')) LIKE ?) "
                    args.extend([s, s, s])
                total = c.execute("SELECT COUNT(1) AS n FROM (" + base_sql + ") t", tuple(args)).fetchone()["n"]
                rows=c.execute(base_sql + f"ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(args + [per, offset])).fetchall()
                tr=""
                for r in rows:
                    st=(r["status"] or "pending").strip().lower()
                    cls="badge"
                    if st=="approved":
                        cls="badge ok"
                    elif st=="rejected":
                        cls="badge no"
                    note = esc((r["approval_note"] or "").strip()) if "approval_note" in r.keys() else ""
                    tr += (
                        "<tr>"
                        f"<td>#{r['id']}</td>"
                        f"<td>{esc(r['prop_name'] or r['property_id'])}</td>"
                        f"<td>{esc(r['unit_label'] or '-')}</td>"
                        f"<td>{esc(r['title'])}</td>"
                        f"<td>${int(r['price']):,}</td>"
                        f"<td><span class='{cls}'>{esc(st)}</span></td>"
                        f"<td>{note}</td>"
                        f"<td>{esc(r['created_at'])}</td>"
                        "</tr>"
                    )
                props = c.execute("SELECT id,name FROM properties WHERE owner_account=? ORDER BY created_at DESC",(u["account_number"],)).fetchall()
                c.close()
                empty_box="" if rows else '<div class="notice" style="margin-top:10px;">No listing submissions yet.</div>'
                prop_opts="".join(f"<option value='{esc(p['id'])}' {'selected' if prop_filter==p['id'] else ''}>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
                filters_form = (
                    "<div class='card' style='margin-bottom:10px;'>"
                    "<form method='GET' action='/manager/listing-requests' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:150px;'><label>Status</label>"
                    f"<select name='status'><option value=''>All</option><option value='pending' {'selected' if st_filter=='pending' else ''}>pending</option><option value='approved' {'selected' if st_filter=='approved' else ''}>approved</option><option value='rejected' {'selected' if st_filter=='rejected' else ''}>rejected</option></select></div>"
                    "<div class='field' style='min-width:220px;'><label>Property</label>"
                    f"<select name='property'><option value=''>All</option>{prop_opts}</select></div>"
                    f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='title/property'></div>"
                    "<div class='field' style='min-width:150px;'><label>Sort</label>"
                    f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                    "<button class='primary-btn' type='submit'>Apply</button>"
                    "<a class='ghost-btn' href='/manager/listing-requests'>Reset</a>"
                    "</form>"
                    "</div>"
                )
                export_q = urlencode(query_without_page(q))
                export_filtered_url = "/manager/listing-requests/export" + (f"?{export_q}" if export_q else "")
                return send_html(self,render("manager_listing_requests.html",title="Listing Submissions",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q),filters_form=filters_form,export_filtered_url=export_filtered_url,requests_rows=tr,empty_box=empty_box,pager_box=pager_html("/manager/listing-requests", q, page, per, total)))
        
            if path=="/manager/listings":
                if u["role"] != "admin":
                    return redir(self,"/manager/listing-requests")
                c=db()
                rows=c.execute("SELECT * FROM listings ORDER BY created_at DESC, id DESC LIMIT 500").fetchall()
                c.close()
                trs=""
                for r in rows:
                    keys = set(r.keys())
                    appr_raw = r["is_approved"] if "is_approved" in keys else 1
                    av_raw = r["is_available"] if "is_available" in keys else 1
                    appr_yes = 1 if to_int(appr_raw, 1) else 0
                    av_yes = 1 if to_int(av_raw, 1) else 0
                    appr_badge = '<span class="badge %s">%s</span>' % (("ok" if appr_yes else "no"), ("Yes" if appr_yes else "No"))
                    av_badge = '<span class="badge %s">%s</span>' % (("ok" if av_yes else "no"), ("Yes" if av_yes else "No"))
                    actions = (
                        '<div class="row" style="gap:8px;flex-wrap:wrap;">'
                          f'<a class="pill" href="/manager/listings/edit?id={r["id"]}">Edit</a>'
                          '<form method="POST" action="/manager/listings/action" style="margin:0;">'
                            f'<input type="hidden" name="listing_id" value="{r["id"]}">'
                            '<input type="hidden" name="action" value="approve">'
                            '<button class="pill" type="submit">Approve</button>'
                          '</form>'
                          '<form method="POST" action="/manager/listings/action" style="margin:0;">'
                            f'<input type="hidden" name="listing_id" value="{r["id"]}">'
                            '<input type="hidden" name="action" value="reject">'
                            '<button class="pill" type="submit">Reject</button>'
                          '</form>'
                          '<form method="POST" action="/manager/listings/action" style="margin:0;">'
                            f'<input type="hidden" name="listing_id" value="{r["id"]}">'
                            '<input type="hidden" name="action" value="toggle_available">'
                            '<button class="pill" type="submit">Toggle Available</button>'
                          '</form>'
                        '</div>'
                    )
                    trs += f"<tr><td>{r['id']}</td><td>{esc(r['title'])}</td><td>{esc(r['location'])}</td><td>${int(r['price']):,}</td><td>{appr_badge}</td><td>{av_badge}</td><td>{actions}</td></tr>"
                return send_html(self,render("manager_listings.html",title="Manage Listings",nav_right=nr,nav_menu=nav_menu(u,path),listings_rows=trs))

            if path=="/manager/listings/edit":
                if u["role"] != "admin":
                    return redir(self,"/manager/listing-requests")
                lid=to_int((parse_qs(urlparse(self.path).query).get("id")or["0"])[0], 0)
                if lid<=0:return redir(self,"/manager/listings")
                c=db()
                r=c.execute("SELECT * FROM listings WHERE id=?",(lid,)).fetchone()
                if not r:
                    c.close()
                    return redir(self,"/manager/listings")
                photos=listing_photos(c,lid)
                admin=""
                if photos:
                    admin += '<div class="gallery" style="margin-top:8px;"><div class="thumbs">'
                    for p in photos:
                        admin += (
                            '<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;">'
                              f'<a class="thumb" href="{esc(p["path"])}" target="_blank"><img src="{esc(p["path"])}" alt=""></a>'
                              '<div class="row" style="gap:8px;flex-wrap:wrap;">'
                                '<form method="POST" action="/manager/listings/thumbnail" style="margin:0;">'
                                  f'<input type="hidden" name="listing_id" value="{lid}">'
                                  f'<input type="hidden" name="path" value="{esc(p["path"])}">'
                                  '<button class="pill" type="submit">Set Thumbnail</button>'
                                '</form>'
                                '<form method="POST" action="/manager/listings/photo_delete" style="margin:0;">'
                                  f'<input type="hidden" name="listing_id" value="{lid}">'
                                  f'<input type="hidden" name="upload_id" value="{p["id"]}">'
                                  '<button class="pill" type="submit">Delete</button>'
                                '</form>'
                              '</div>'
                            '</div>'
                        )
                    admin += '</div></div>'
                else:
                    admin = '<div class="muted">No photos uploaded yet.</div>'
                cat = r["category"]
                c.close()
                return send_html(self,render("manager_listing_edit.html",title=f"Edit Listing #{lid}",nav_right=nr,nav_menu=nav_menu(u,path),
                                             listing_id=str(lid),
                                             listing_title=esc(r["title"]),
                                             price=str(r["price"]),
                                             location=esc(r["location"]),
                                             beds=str(r["beds"]),
                                             baths=str(r["baths"]),
                                             description=esc(r["description"]),
                                             cat_short="selected" if cat=="Short Term Rental" else "",
                                             cat_long="selected" if cat=="Long Term Rental" else "",
                                             cat_vehicle="selected" if cat=="Vehicle Rental" else "",
                                             cat_sell="selected" if cat=="Sell Your Property to Us" else "",
                                             photos_admin=admin))
            return e404(self)

        def _manager_post(self,path,u,f):
            u=self._req_role(u,"manager",action="manager.portal")
            if not u:return
            if path=="/manager/queue/action":
                if not self._req_action(u, "manager.ops.update"): return
                kind = (f.get("item_kind") or "").strip().lower()
                item_id = to_int(f.get("item_id"), 0)
                action = (f.get("action") or "").strip().lower()
                bucket = (f.get("bucket") or "all").strip().lower()
                if bucket not in ("all","maintenance","payments","checks","inquiries","applications","invites"):
                    bucket = "all"
                queue_path = f"/manager/queue?bucket={bucket}"
                if item_id <= 0 or kind not in ("maintenance","payments","checks","inquiries","applications","invites"):
                    return redir(self, with_msg(queue_path, "Queue action request was invalid.", True))
                c = db()
                if kind == "maintenance":
                    row = c.execute("SELECT tenant_account,status,assigned_to FROM maintenance_requests WHERE id=?", (item_id,)).fetchone()
                    if not row:
                        c.close()
                        return redir(self, with_msg(queue_path, "Maintenance request was not found.", True))
                    if u["role"] != "admin":
                        own = c.execute(
                            "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                            "WHERE l.tenant_account=? AND p.owner_account=? ORDER BY l.id DESC LIMIT 1",
                            (row["tenant_account"], u["account_number"]),
                        ).fetchone()
                        if not own:
                            c.close()
                            return e403(self)
                    new_status = "in_progress" if action == "start" else ("closed" if action == "close" else "")
                    if new_status not in ("in_progress", "closed"):
                        c.close()
                        return redir(self, with_msg(queue_path, "Unsupported maintenance queue action.", True))
                    assigned_to = (row["assigned_to"] or "").strip()
                    c.execute("UPDATE maintenance_requests SET status=?,assigned_to=?,updated_at=datetime('now') WHERE id=?", (new_status, assigned_to, item_id))
                    tgt = c.execute("SELECT id FROM users WHERE account_number=?", (row["tenant_account"],)).fetchone()
                    if tgt:
                        create_notification(c, tgt["id"], f"Maintenance request #{item_id} updated to {new_status}", "/tenant/maintenance")
                    audit_log(c, u, "maintenance_queue_action", "maintenance_requests", item_id, f"action={action};status={new_status};assigned_to={assigned_to}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg(queue_path, f"Maintenance #{item_id} set to {new_status}."))
                if kind == "payments":
                    row = c.execute("SELECT payer_account,payer_role,status FROM payments WHERE id=?", (item_id,)).fetchone()
                    if not row:
                        c.close()
                        return redir(self, with_msg(queue_path, "Payment record was not found.", True))
                    if u["role"] != "admin":
                        allowed = False
                        if row["payer_role"] in ("property_manager", "landlord", "manager"):
                            allowed = (row["payer_account"] == u["account_number"])
                        else:
                            own = c.execute(
                                "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                                "WHERE l.tenant_account=? AND p.owner_account=? ORDER BY l.id DESC LIMIT 1",
                                (row["payer_account"], u["account_number"]),
                            ).fetchone()
                            allowed = bool(own)
                        if not allowed:
                            c.close()
                            return e403(self)
                    new_status = "paid" if action == "approve" else ("failed" if action == "fail" else "")
                    if new_status not in ("paid", "failed"):
                        c.close()
                        return redir(self, with_msg(queue_path, "Unsupported payment queue action.", True))
                    c.execute("UPDATE payments SET status=? WHERE id=?", (new_status, item_id))
                    if (row["payer_role"] or "").strip() == "tenant":
                        sync_ledger_from_payments(c, payment_id=item_id)
                        reconcile_tenant_ledger(c, row["payer_account"])
                    tgt = c.execute("SELECT id FROM users WHERE account_number=?", (row["payer_account"],)).fetchone()
                    if tgt:
                        create_notification(c, tgt["id"], f"Payment #{item_id} status: {new_status}", "/notifications")
                    audit_log(c, u, "payment_queue_action", "payments", item_id, f"action={action};status={new_status}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg(queue_path, f"Payment #{item_id} set to {new_status}."))
                if kind == "checks":
                    row = c.execute("SELECT requester_account,status,property_id FROM property_checks WHERE id=?", (item_id,)).fetchone()
                    if not row:
                        c.close()
                        return redir(self, with_msg(queue_path, "Property check was not found.", True))
                    if u["role"] != "admin":
                        own = c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?", (row["property_id"], u["account_number"])).fetchone()
                        if not own:
                            c.close()
                            return e403(self)
                    new_status = "scheduled" if action == "schedule" else ("completed" if action == "complete" else "")
                    if new_status not in ("scheduled", "completed"):
                        c.close()
                        return redir(self, with_msg(queue_path, "Unsupported property-check queue action.", True))
                    c.execute("UPDATE property_checks SET status=? WHERE id=?", (new_status, item_id))
                    tgt = c.execute("SELECT id FROM users WHERE account_number=?", (row["requester_account"],)).fetchone()
                    if tgt:
                        create_notification(c, tgt["id"], f"Property check #{item_id} status updated to {new_status}", "/landlord/checks")
                    audit_log(c, u, "property_check_queue_action", "property_checks", item_id, f"action={action};status={new_status}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg(queue_path, f"Property check #{item_id} set to {new_status}."))
                if kind == "inquiries":
                    row = c.execute("SELECT status FROM inquiries WHERE id=?", (item_id,)).fetchone()
                    if not row:
                        c.close()
                        return redir(self, with_msg(queue_path, "Inquiry was not found.", True))
                    new_status = "open" if action == "open" else ("closed" if action == "close" else "")
                    if new_status not in ("open", "closed"):
                        c.close()
                        return redir(self, with_msg(queue_path, "Unsupported inquiry queue action.", True))
                    c.execute("UPDATE inquiries SET status=? WHERE id=?", (new_status, item_id))
                    audit_log(c, u, "inquiry_queue_action", "inquiries", item_id, f"action={action};status={new_status}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg(queue_path, f"Inquiry #{item_id} set to {new_status}."))
                if kind == "applications":
                    row = c.execute("SELECT applicant_user_id,status FROM applications WHERE id=?", (item_id,)).fetchone()
                    if not row:
                        c.close()
                        return redir(self, with_msg(queue_path, "Application was not found.", True))
                    new_status = "under_review" if action == "review" else ("approved" if action == "approve" else "")
                    if new_status not in ("under_review", "approved"):
                        c.close()
                        return redir(self, with_msg(queue_path, "Unsupported application queue action.", True))
                    c.execute("UPDATE applications SET status=?, updated_at=datetime('now') WHERE id=?", (new_status, item_id))
                    if row["applicant_user_id"]:
                        create_notification(c, row["applicant_user_id"], f"Your application status: {new_status.replace('_',' ')}", "/notifications")
                    audit_log(c, u, "application_queue_action", "applications", item_id, f"action={action};status={new_status}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg(queue_path, f"Application #{item_id} set to {new_status}."))
                if kind == "invites":
                    row = c.execute(
                        "SELECT i.id,i.tenant_user_id,i.status,i.property_id,i.unit_label,p.owner_account "
                        "FROM tenant_property_invites i JOIN properties p ON p.id=i.property_id WHERE i.id=?",
                        (item_id,),
                    ).fetchone()
                    if not row:
                        c.close()
                        return redir(self, with_msg(queue_path, "Invite was not found.", True))
                    if u["role"] != "admin" and row["owner_account"] != u["account_number"]:
                        c.close()
                        return e403(self)
                    if (row["status"] or "").strip().lower() != "pending":
                        c.close()
                        return redir(self, with_msg(queue_path, f"Invite #{item_id} is no longer pending.", True))
                    if action != "cancel":
                        c.close()
                        return redir(self, with_msg(queue_path, "Unsupported invite queue action.", True))
                    c.execute(
                        "UPDATE tenant_property_invites SET status='cancelled', responded_at=datetime('now'), revoke_reason='cancelled_from_queue' WHERE id=?",
                        (item_id,),
                    )
                    if row["tenant_user_id"]:
                        create_notification(c, row["tenant_user_id"], f"Invite cancelled: {row['property_id']} / {row['unit_label']}", "/tenant/invites")
                    audit_log(c, u, "tenant_invite_queue_cancelled", "tenant_property_invites", item_id, f"{row['property_id']}/{row['unit_label']}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg(queue_path, f"Invite #{item_id} cancelled."))
                c.close()
                return redir(self, with_msg(queue_path, "Queue action was not processed.", True))
            if path=="/manager/staff/new":
                if not self._req_action(u, "manager.ops.update"): return
                name = (f.get("name") or "").strip()
                email = (f.get("email") or "").strip()
                phone = (f.get("phone") or "").strip()
                if len(name) < 2:
                    return redir(self, with_msg("/manager/maintenance", "Staff name is required.", True))
                c = db()
                c.execute(
                    "INSERT INTO maintenance_staff(name,email,phone,is_active)VALUES(?,?,?,1)",
                    (name[:120], email[:180], phone[:60]),
                )
                sid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                audit_log(c, u, "maintenance_staff_added", "maintenance_staff", sid, name[:120])
                c.commit();c.close()
                return redir(self, with_msg("/manager/maintenance", f"Staff member added: {name[:120]}"))
            if path=="/manager/maintenance/thread":
                if not self._req_action(u, "manager.ops.update"): return
                rid = to_int(f.get("request_id"), 0)
                if rid <= 0:
                    return redir(self, with_msg("/manager/maintenance", "Maintenance request was not found.", True))
                c = db()
                row = c.execute("SELECT tenant_account FROM maintenance_requests WHERE id=?", (rid,)).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/manager/maintenance", "Maintenance request was not found.", True))
                if u["role"] != "admin":
                    own = c.execute(
                        "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                        "WHERE l.tenant_account=? AND p.owner_account=? ORDER BY l.id DESC LIMIT 1",
                        (row["tenant_account"], u["account_number"]),
                    ).fetchone()
                    if not own:
                        c.close()
                        return e403(self)
                tid = ensure_maintenance_message_thread(c, u, rid)
                c.commit()
                c.close()
                if tid > 0:
                    return redir(self, with_msg(f"/messages?thread={tid}", f"Maintenance thread ready for request #{rid}."))
                return redir(self, with_msg("/manager/maintenance", "Could not start maintenance thread.", True))
            if path=="/manager/roommates/add":
                if not self._req_action(u, "manager.leases.manage"): return
                lease_id = to_int(f.get("lease_id"), 0)
                acct = (f.get("roommate_account") or "").strip()
                share = to_int(f.get("share_percent"), 0)
                if lease_id <= 0 or not acct or share <= 0 or share > 100:
                    return redir(self, with_msg("/manager/leases", "Lease, roommate tenant, and share percent are required.", True))
                c = db()
                lease = c.execute(
                    "SELECT l.id,l.tenant_account,l.property_id,l.unit_label,l.is_active FROM tenant_leases l "
                    "JOIN properties p ON p.id=l.property_id WHERE l.id=? AND p.owner_account=?",
                    (lease_id, u["account_number"]),
                ).fetchone()
                if not lease:
                    c.close()
                    return redir(self, with_msg("/manager/leases", "Lease was not found for your portfolio.", True))
                if (lease["tenant_account"] or "").strip() == acct:
                    c.close()
                    return redir(self, with_msg("/manager/leases", "Primary tenant cannot be added as a roommate split.", True))
                tenant = c.execute("SELECT id FROM users WHERE account_number=? AND role='tenant'", (acct,)).fetchone()
                if not tenant:
                    c.close()
                    return redir(self, with_msg("/manager/leases", "Roommate tenant account was not found.", True))
                other_active = c.execute(
                    "SELECT 1 FROM tenant_leases WHERE tenant_account=? AND is_active=1 AND id<>?",
                    (acct, lease_id),
                ).fetchone()
                if other_active:
                    c.close()
                    return redir(self, with_msg("/manager/leases", "This tenant already has another active lease.", True))
                existing = c.execute(
                    "SELECT id,status FROM lease_roommates WHERE lease_id=? AND tenant_account=?",
                    (lease_id, acct),
                ).fetchone()
                cur_sum = to_int(c.execute(
                    "SELECT COALESCE(SUM(share_percent),0) AS n FROM lease_roommates WHERE lease_id=? AND status='active'",
                    (lease_id,),
                ).fetchone()["n"], 0)
                if existing and (existing["status"] or "").strip().lower() == "active":
                    c.close()
                    return redir(self, with_msg("/manager/leases", "This roommate split already exists.", True))
                if cur_sum + share > 100:
                    c.close()
                    return redir(self, with_msg("/manager/leases", "Total roommate share cannot exceed 100%.", True))
                if existing:
                    c.execute("UPDATE lease_roommates SET share_percent=?,status='active' WHERE id=?", (share, existing["id"]))
                    rm_id = existing["id"]
                else:
                    c.execute(
                        "INSERT INTO lease_roommates(lease_id,tenant_account,share_percent,status)VALUES(?,?,?,'active')",
                        (lease_id, acct, share),
                    )
                    rm_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                tgt = c.execute("SELECT id FROM users WHERE account_number=?", (acct,)).fetchone()
                if tgt:
                    create_notification(c, tgt["id"], f"Roommate split assigned: {lease['property_id']} / {lease['unit_label']} ({share}%)", "/tenant/pay-rent")
                audit_log(c, u, "lease_roommate_added", "lease_roommates", rm_id, f"lease={lease_id};tenant={acct};share={share}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/leases", "Roommate split added."))
            if path=="/manager/roommates/remove":
                if not self._req_action(u, "manager.leases.manage"): return
                roommate_id = to_int(f.get("roommate_id"), 0)
                if roommate_id <= 0:
                    return redir(self, with_msg("/manager/leases", "Roommate record was not found.", True))
                c = db()
                row = c.execute(
                    "SELECT rm.id,rm.tenant_account,rm.lease_id,l.property_id,l.unit_label,p.owner_account "
                    "FROM lease_roommates rm "
                    "JOIN tenant_leases l ON l.id=rm.lease_id "
                    "JOIN properties p ON p.id=l.property_id "
                    "WHERE rm.id=?",
                    (roommate_id,),
                ).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/manager/leases", "Roommate record was not found.", True))
                if row["owner_account"] != u["account_number"] and u["role"] != "admin":
                    c.close()
                    return e403(self)
                c.execute("UPDATE lease_roommates SET status='removed' WHERE id=?", (roommate_id,))
                tgt = c.execute("SELECT id FROM users WHERE account_number=?", (row["tenant_account"],)).fetchone()
                if tgt:
                    create_notification(c, tgt["id"], f"Roommate split removed: {row['property_id']} / {row['unit_label']}", "/tenant/pay-rent")
                audit_log(c, u, "lease_roommate_removed", "lease_roommates", roommate_id, f"lease={row['lease_id']};tenant={row['tenant_account']}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/leases", "Roommate split removed."))
            if path=="/manager/inspections/new":
                if not self._req_action(u, "manager.ops.update"): return
                pid=(f.get("property_id") or "").strip()
                ul=(f.get("unit_label") or "").strip()
                typ=(f.get("inspection_type") or "").strip()
                dt=(f.get("scheduled_date") or "").strip()
                ta=(f.get("tenant_account") or "").strip()
                if not pid or len(ul)<2 or typ not in ("move_in","move_out") or len(dt)<8:
                    return redir(self, with_msg("/manager/inspections", "Property, unit, type, and date are required.", True))
                c=db()
                own = c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?", (pid, u["account_number"])).fetchone() if u["role"]!="admin" else c.execute("SELECT 1 FROM properties WHERE id=?", (pid,)).fetchone()
                if not own:
                    c.close()
                    return redir(self, with_msg("/manager/inspections", "Property was not found for your account.", True))
                if ta:
                    tenant_ok = c.execute("SELECT 1 FROM users WHERE account_number=? AND role='tenant'", (ta,)).fetchone()
                    if not tenant_ok:
                        c.close()
                        return redir(self, with_msg("/manager/inspections", "Tenant account was not found.", True))
                c.execute(
                    "INSERT INTO inspections(property_id,unit_label,tenant_account,inspection_type,scheduled_date,status,created_by_user_id)"
                    "VALUES(?,?,?,?,?,'scheduled',?)",
                    (pid, ul, ta or None, typ, dt[:10], u["id"]),
                )
                iid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                if ta:
                    tgt = c.execute("SELECT id FROM users WHERE account_number=?", (ta,)).fetchone()
                    if tgt:
                        create_notification(c, tgt["id"], f"Inspection scheduled: {pid} / {ul} on {dt[:10]}", "/tenant/maintenance")
                audit_log(c, u, "inspection_scheduled", "inspections", iid, f"{pid}/{ul};{typ};{dt[:10]}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/inspections", "Inspection scheduled."))
            if path=="/manager/inspections/update":
                if not self._req_action(u, "manager.ops.update"): return
                iid=to_int(f.get("inspection_id"), 0)
                st=(f.get("status") or "scheduled").strip().lower()
                notes=(f.get("report_notes") or "").strip()[:1000]
                if iid<=0 or st not in ("scheduled","completed","cancelled"):
                    return redir(self, with_msg("/manager/inspections", "Invalid inspection update request.", True))
                checklist = {
                    "smoke_alarm": f.get("chk_smoke_alarm") in ("1","on","true","yes"),
                    "walls": f.get("chk_walls") in ("1","on","true","yes"),
                    "floors": f.get("chk_floors") in ("1","on","true","yes"),
                    "fixtures": f.get("chk_fixtures") in ("1","on","true","yes"),
                }
                c=db()
                row = c.execute(
                    "SELECT i.id,i.tenant_account,i.property_id,p.owner_account,i.status FROM inspections i "
                    "JOIN properties p ON p.id=i.property_id WHERE i.id=?",
                    (iid,),
                ).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/manager/inspections", "Inspection was not found.", True))
                if u["role"]!="admin" and row["owner_account"] != u["account_number"]:
                    c.close()
                    return e403(self)
                done_at = "datetime('now')" if st=="completed" else "NULL"
                c.execute(
                    "UPDATE inspections SET status=?,checklist_json=?,report_notes=?,completed_at=" + done_at + " WHERE id=?",
                    (st, json.dumps(checklist), notes, iid),
                )
                if row["tenant_account"]:
                    tgt = c.execute("SELECT id FROM users WHERE account_number=?", (row["tenant_account"],)).fetchone()
                    if tgt:
                        create_notification(c, tgt["id"], f"Inspection #{iid} updated to {st}", "/notifications")
                audit_log(c, u, "inspection_updated", "inspections", iid, f"status={st}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/inspections", f"Inspection #{iid} updated."))
            if path=="/manager/preventive/new":
                if not self._req_action(u, "manager.ops.update"): return
                pid=(f.get("property_id") or "").strip()
                ul=(f.get("unit_label") or "").strip()
                task=(f.get("task") or "").strip()
                freq=to_int(f.get("frequency_days"), 0)
                due=(f.get("next_due_date") or "").strip()
                staff_id=to_int(f.get("staff_id"), 0)
                if not pid or len(task)<3 or freq<1 or len(due)<8:
                    return redir(self, with_msg("/manager/preventive", "Property, task, frequency, and due date are required.", True))
                c=db()
                own = c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?", (pid, u["account_number"])).fetchone() if u["role"]!="admin" else c.execute("SELECT 1 FROM properties WHERE id=?", (pid,)).fetchone()
                if not own:
                    c.close()
                    return redir(self, with_msg("/manager/preventive", "Property was not found for your account.", True))
                sid = None
                if staff_id > 0:
                    srow = c.execute("SELECT id FROM maintenance_staff WHERE id=? AND is_active=1", (staff_id,)).fetchone()
                    if srow:
                        sid = srow["id"]
                c.execute(
                    "INSERT INTO preventive_tasks(property_id,unit_label,task,frequency_days,next_due_date,status,assigned_staff_id,created_by_user_id)"
                    "VALUES(?,?,?,?,?,'open',?,?)",
                    (pid, ul or None, task[:240], freq, due[:10], sid, u["id"]),
                )
                tid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                audit_log(c, u, "preventive_task_created", "preventive_tasks", tid, f"{pid}/{ul};freq={freq};due={due[:10]}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/preventive", "Preventive task created."))
            if path=="/manager/preventive/update":
                if not self._req_action(u, "manager.ops.update"): return
                tid=to_int(f.get("task_id"), 0)
                st=(f.get("status") or "open").strip().lower()
                next_due=(f.get("next_due_date") or "").strip()
                if tid<=0 or st not in ("open","completed","cancelled"):
                    return redir(self, with_msg("/manager/preventive", "Invalid preventive task update request.", True))
                c=db()
                row = c.execute(
                    "SELECT t.id,t.frequency_days,t.property_id,p.owner_account FROM preventive_tasks t "
                    "JOIN properties p ON p.id=t.property_id WHERE t.id=?",
                    (tid,),
                ).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/manager/preventive", "Preventive task was not found.", True))
                if u["role"]!="admin" and row["owner_account"] != u["account_number"]:
                    c.close()
                    return e403(self)
                due = next_due[:10] if len(next_due) >= 8 else None
                if st == "completed":
                    base = datetime.now(timezone.utc).date()
                    due = (base + timedelta(days=max(1, to_int(row["frequency_days"], 30)))).strftime("%Y-%m-%d")
                    c.execute(
                        "UPDATE preventive_tasks SET status='open',last_completed_at=datetime('now'),next_due_date=? WHERE id=?",
                        (due, tid),
                    )
                    note_status = "completed+rolled"
                else:
                    if due:
                        c.execute("UPDATE preventive_tasks SET status=?,next_due_date=? WHERE id=?", (st, due, tid))
                    else:
                        c.execute("UPDATE preventive_tasks SET status=? WHERE id=?", (st, tid))
                    note_status = st
                audit_log(c, u, "preventive_task_updated", "preventive_tasks", tid, f"status={note_status};next_due={due or '-'}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/preventive", "Preventive task updated."))
            if path=="/manager/batch-notify":
                if not self._req_action(u, "manager.ops.update"): return
                pid=(f.get("property_id") or "").strip()
                subj=(f.get("subject") or "").strip()
                body=(f.get("body") or "").strip()
                if not pid or len(subj)<3 or len(body)<5:
                    return redir(self, with_msg("/manager/batch-notify", "Property, subject, and message are required.", True))
                c=db()
                own = c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?", (pid, u["account_number"])).fetchone() if u["role"]!="admin" else c.execute("SELECT 1 FROM properties WHERE id=?", (pid,)).fetchone()
                if not own:
                    c.close()
                    return redir(self, with_msg("/manager/batch-notify", "Property was not found for your account.", True))
                accts = [r["tenant_account"] for r in c.execute("SELECT DISTINCT tenant_account FROM tenant_leases WHERE property_id=? AND is_active=1", (pid,)).fetchall()]
                accts += [r["tenant_account"] for r in c.execute(
                    "SELECT DISTINCT rm.tenant_account FROM lease_roommates rm "
                    "JOIN tenant_leases l ON l.id=rm.lease_id AND l.is_active=1 "
                    "WHERE l.property_id=? AND rm.status='active'",
                    (pid,),
                ).fetchall()]
                sent = 0
                msg_text = f"{subj}: {body[:180]}"
                for acct in sorted(set(a for a in accts if a)):
                    tgt = c.execute("SELECT id FROM users WHERE account_number=?", (acct,)).fetchone()
                    if not tgt:
                        continue
                    create_notification(c, tgt["id"], msg_text, "/notifications")
                    sent += 1
                audit_log(c, u, "batch_notification_sent", "properties", pid, f"subject={subj[:80]};recipients={sent}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/batch-notify", f"Notification sent to {sent} tenant account(s)."))
            if path=="/manager/tenant/invite":
                if not self._req_action(u, "manager.tenant_sync.manage"): return
                return self._manager_tenant_invite(f,u)
            if path=="/manager/tenant/invite/cancel":
                if not self._req_action(u, "manager.tenant_sync.manage"): return
                invite_id = to_int(f.get("invite_id"), 0)
                revoke_reason = (f.get("revoke_reason") or "revoked_by_manager").strip()[:120]
                if invite_id <= 0:
                    return redir(self, with_msg("/manager/tenants", "Invite was not found.", True))
                c = db()
                cleanup_expired_invites(c)
                row = c.execute(
                    "SELECT i.*, p.owner_account FROM tenant_property_invites i "
                    "JOIN properties p ON p.id=i.property_id WHERE i.id=?",
                    (invite_id,),
                ).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/manager/tenants", "Invite was not found.", True))
                if u["role"] != "admin" and row["owner_account"] != u["account_number"]:
                    c.close()
                    return e403(self)
                st = (row["status"] or "").strip().lower()
                if st != "pending":
                    c.close()
                    return redir(self, with_msg("/manager/tenants", "Invite has already been responded to.", True))
                c.execute(
                    "UPDATE tenant_property_invites SET status='cancelled', responded_at=datetime('now'), revoke_reason=? WHERE id=?",
                    (revoke_reason, invite_id),
                )
                if row["tenant_user_id"]:
                    create_notification(c, row["tenant_user_id"], f"Invite cancelled: {row['property_id']} / {row['unit_label']}", "/tenant/invites")
                audit_log(c, u, "tenant_invite_cancelled", "tenant_property_invites", invite_id, f"{row['property_id']}/{row['unit_label']};reason={revoke_reason}")
                c.commit()
                c.close()
                return redir(self, with_msg("/manager/tenants", "Invite cancelled."))
            if path=="/manager/tenant/invite/resend":
                if not self._req_action(u, "manager.tenant_sync.manage"): return
                invite_id = to_int(f.get("invite_id"), 0)
                if invite_id <= 0:
                    return redir(self, with_msg("/manager/tenants", "Invite was not found.", True))
                c = db()
                row = c.execute(
                    "SELECT i.*, p.owner_account FROM tenant_property_invites i "
                    "JOIN properties p ON p.id=i.property_id WHERE i.id=?",
                    (invite_id,),
                ).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/manager/tenants", "Invite was not found.", True))
                if u["role"] != "admin" and row["owner_account"] != u["account_number"]:
                    c.close()
                    return e403(self)
                ok, note = create_tenant_property_invite(
                    c,
                    u,
                    row["tenant_account"],
                    row["property_id"],
                    row["unit_label"],
                    message=(row["message"] or ""),
                    owner_account=u["account_number"],
                )
                if ok:
                    c.commit()
                c.close()
                return redir(self, with_msg("/manager/tenants", note, err=(not ok)))
            if path=="/manager/property/new":
                if not self._req_action(u, "manager.property.manage"): return
                nm=(f.get("name")or"").strip()
                loc=(f.get("location")or"").strip()
                pt=f.get("property_type")or"Apartment"
                uc=to_int(f.get("units_count"), 0)
                property_code = (f.get("property_code") or "").strip().upper()
                unit_labels_raw = (f.get("unit_labels") or "").strip()
                invite_tenant_ident = (f.get("invite_tenant_ident") or "").strip()
                invite_unit_label = (f.get("invite_unit_label") or "").strip()
                invite_message = (f.get("invite_message") or "").strip()
                if pt not in("House","Apartment") or len(nm)<2 or len(loc)<2:
                    return send_html(self,render("manager_property_new.html",title="Register Property",nav_right=nav(u,"/manager/property/new"),nav_menu=nav_menu(u,"/manager/property/new"),error_box='<div class="notice err"><b>Error:</b> Check fields.</div>'))
                unit_labels = []
                if unit_labels_raw:
                    seen = set()
                    for tok in re.split(r"[\r\n,]+", unit_labels_raw):
                        label = (tok or "").strip()
                        if len(label) < 2:
                            continue
                        if len(label) > 40:
                            label = label[:40]
                        if label.lower() in seen:
                            continue
                        seen.add(label.lower())
                        unit_labels.append(label)
                if not unit_labels:
                    if uc < 1:
                        return send_html(self,render("manager_property_new.html",title="Register Property",nav_right=nav(u,"/manager/property/new"),nav_menu=nav_menu(u,"/manager/property/new"),error_box='<div class="notice err"><b>Error:</b> Add at least one unit.</div>'))
                    unit_labels = [f"Unit {i}" for i in range(1, uc + 1)]
                uc = len(unit_labels)
                code_clean = re.sub(r"[^A-Z0-9-]+", "", property_code).strip("-")
                c=db()
                if code_clean:
                    base_pid = f"{u['account_number']}-{code_clean}"
                else:
                    base_pid = f"{u['account_number']}-{int(datetime.now(timezone.utc).timestamp())}"
                pid = base_pid
                if c.execute("SELECT 1 FROM properties WHERE id=?", (pid,)).fetchone():
                    n = 2
                    while c.execute("SELECT 1 FROM properties WHERE id=?", (f"{base_pid}-{n}",)).fetchone():
                        n += 1
                    pid = f"{base_pid}-{n}"
                c.execute("INSERT INTO properties(id,owner_account,name,property_type,units_count,location)VALUES(?,?,?,?,?,?)",(pid,u["account_number"],nm,pt,uc,loc))
                for lbl in unit_labels:
                    c.execute("INSERT INTO units(property_id,unit_label)VALUES(?,?)",(pid,lbl))
                files=getattr(self,"_files",{}) or {}
                photos=files.get("photos")
                if photos:
                    photo_items = photos if isinstance(photos, list) else [photos]
                    for fi in photo_items[:12]:
                        save_image_upload(c, u["id"], "properties", None, "property_photo", fi, related_key=pid)
                invite_note = ""
                if invite_tenant_ident:
                    if not invite_unit_label and unit_labels:
                        invite_unit_label = unit_labels[0]
                    ok, note = create_tenant_property_invite(
                        c,
                        u,
                        invite_tenant_ident,
                        pid,
                        invite_unit_label,
                        message=invite_message,
                        owner_account=u["account_number"],
                    )
                    invite_note = note if ok else f"Invite not sent: {note}"
                audit_log(c, u, "manager_property_registered", "properties", pid, f"units={uc};type={pt}")
                c.commit();c.close()
                msg = f"Property registered: {pid}"
                if invite_note:
                    msg += f". {invite_note}"
                return redir(self, with_msg("/manager/properties", msg))
            if path=="/manager/listing/submit_all":
                if not self._req_action(u, "manager.listing.submit"): return
                pid=(f.get("property_id") or "").strip()
                cat=(f.get("category") or "Long Term Rental").strip()
                mode=(f.get("mode") or "submit").strip().lower()
                unit_ids_raw = (f.get("unit_ids") or "").strip()
                unit_ids = []
                if unit_ids_raw:
                    for tok in unit_ids_raw.split(","):
                        uid = to_int(tok, 0)
                        if uid > 0 and uid not in unit_ids:
                            unit_ids.append(uid)
                overrides = {}
                for uid in unit_ids:
                    sel_key = f"sel_{uid}"
                    selected = str(f.get(sel_key) or "").strip().lower() in ("1", "true", "yes", "on")
                    overrides[uid] = {
                        "selected": selected,
                        "title": (f.get(f"title_{uid}") or "").strip(),
                        "price": max(0, to_int(f.get(f"price_{uid}"), 0)),
                        "beds": max(0, to_int(f.get(f"beds_{uid}"), 0)),
                        "baths": max(0, to_int(f.get(f"baths_{uid}"), 0)),
                        "description": (f.get(f"description_{uid}") or "").strip()[:2000],
                    }
                c=db()
                if u["role"] == "admin":
                    pr = c.execute("SELECT id FROM properties WHERE id=?", (pid,)).fetchone()
                else:
                    pr = c.execute("SELECT id FROM properties WHERE id=? AND owner_account=?", (pid, u["account_number"])).fetchone()
                if not pr:
                    c.close()
                    return redir(self, with_msg("/manager/tenants", "Property was not found for your account.", True))
                if mode == "save":
                    saved = 0
                    for uid in unit_ids:
                        ov = overrides.get(uid) or {}
                        row = c.execute("SELECT id,is_occupied FROM units WHERE id=? AND property_id=?", (uid, pid)).fetchone()
                        if not row:
                            continue
                        if to_int(row["is_occupied"], 0):
                            continue
                        c.execute(
                            "UPDATE units SET rent=?,beds=?,baths=? WHERE id=? AND property_id=?",
                            (
                                max(0, to_int(ov.get("price"), 0)),
                                max(0, to_int(ov.get("beds"), 0)),
                                max(0, to_int(ov.get("baths"), 0)),
                                uid,
                                pid,
                            ),
                        )
                        saved += 1
                    audit_log(c, u, "manager_listing_values_saved", "properties", pid, f"units={saved}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg("/manager/tenants", f"Saved listing values for {saved} unit(s)."))
                created, skipped, err = create_bulk_listing_requests(
                    c,
                    u,
                    pid,
                    cat,
                    owner_account=(None if u["role"] == "admin" else u["account_number"]),
                    unit_overrides=(overrides or None),
                )
                if not err:
                    audit_log(c, u, "manager_submit_all_units", "properties", pid, f"created={created};skipped={skipped};category={cat}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg("/manager/tenants", f"Submitted {created} unit(s) for approval. Skipped {skipped}."))
                c.close()
                return redir(self, with_msg("/manager/tenants", err, True))
            if path=="/manager/leases":
                if not self._req_action(u, "manager.leases.manage"): return
                ta=(f.get("tenant_account")or"").strip();pid=(f.get("property_id")or"").strip();ul=(f.get("unit_label")or"").strip();sd=(f.get("start_date")or"").strip()
                if len(ta)<2 or len(pid)<5 or len(ul)<2 or len(sd)<8:
                    return redir(self, with_msg("/manager/leases", "Please complete tenant, property, unit, and start date.", True))
                c=db();t=c.execute("SELECT id FROM users WHERE account_number=? AND role='tenant'",(ta,)).fetchone();pr=c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?",(pid,u["account_number"])).fetchone();uu=c.execute("SELECT 1 FROM units WHERE property_id=? AND unit_label=? AND is_occupied=0",(pid,ul)).fetchone()
                if not t or not pr or not uu:
                    c.close()
                    return redir(self, with_msg("/manager/leases", "Lease assignment failed. Tenant, property, or vacant unit was not valid.", True))
                prev=c.execute("SELECT property_id,unit_label FROM tenant_leases WHERE tenant_account=? AND is_active=1",(ta,)).fetchall()
                for p in prev:c.execute("UPDATE units SET is_occupied=0 WHERE property_id=? AND unit_label=?",(p["property_id"],p["unit_label"]))
                c.execute("UPDATE tenant_leases SET is_active=0,end_date=date('now') WHERE tenant_account=? AND is_active=1",(ta,))
                c.execute(
                    "INSERT INTO tenant_leases(tenant_account,property_id,unit_label,start_date,is_active,manager_signed_at,tenant_signed_at,esign_ip)"
                    "VALUES(?,?,?,?,1,datetime('now'),NULL,NULL)",
                    (ta,pid,ul,sd),
                )
                lease_id = to_int(c.execute("SELECT last_insert_rowid()").fetchone()[0], 0)
                c.execute("UPDATE units SET is_occupied=1 WHERE property_id=? AND unit_label=?",(pid,ul))
                files=getattr(self,"_files",{}) or {}
                lease_up=files.get("lease_pdf")
                if isinstance(lease_up, list):
                    lease_up = lease_up[0] if lease_up else None
                if lease_up:
                    try:
                        save_pdf_upload(c, u["id"], "tenant_leases", lease_id, "lease_doc", lease_up)
                    except ValueError as e:
                        c.close()
                        return redir(self, with_msg("/manager/leases", str(e), True))
                create_notification(c,t["id"],f"Lease assigned: {pid} / {ul}", "/tenant/lease")
                audit_log(c, u, "lease_assigned", "tenant_leases", lease_id, f"{ta}->{pid}/{ul}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/leases", "Lease assigned successfully."))
            if path=="/manager/leases/end":
                if not self._req_action(u, "manager.leases.manage"): return
                lease_id=to_int(f.get("lease_id"), 0)
                if lease_id<=0:return redir(self, with_msg("/manager/leases", "Lease ID is missing.", True))
                c=db()
                row=c.execute(
                    "SELECT l.* FROM tenant_leases l JOIN properties p ON p.id=l.property_id WHERE l.id=? AND p.owner_account=?",
                    (lease_id,u["account_number"])
                ).fetchone()
                if row and to_int(row["is_active"],0):
                    c.execute("UPDATE tenant_leases SET is_active=0,end_date=date('now') WHERE id=?",(lease_id,))
                    c.execute("UPDATE lease_roommates SET status='removed' WHERE lease_id=? AND status='active'", (lease_id,))
                    c.execute("UPDATE units SET is_occupied=0 WHERE property_id=? AND unit_label=?",(row["property_id"],row["unit_label"]))
                    tgt=c.execute("SELECT id FROM users WHERE account_number=?",(row["tenant_account"],)).fetchone()
                    if tgt:
                        create_notification(c,tgt["id"],f"Lease ended: {row['property_id']} / {row['unit_label']}", "/tenant/lease")
                    audit_log(c, u, "lease_ended", "tenant_leases", lease_id, f"{row['property_id']}/{row['unit_label']}")
                c.commit();c.close()
                if not row:
                    return redir(self, with_msg("/manager/leases", "Lease was not found.", True))
                if not to_int(row["is_active"],0):
                    return redir(self, with_msg("/manager/leases", "Lease is already inactive.", True))
                return redir(self, with_msg("/manager/leases", "Lease ended successfully."))
            if path=="/manager/maintenance/update":
                if not self._req_action(u, "manager.ops.update"): return
                rid=int(f.get("request_id")or"0")if(f.get("request_id")or"").isdigit()else 0;st=f.get("status")or"open";at=(f.get("assigned_to")or"").strip()
                staff_id = to_int(f.get("staff_id"), 0)
                if rid<=0 or st not in("open","in_progress","closed"):return redir(self, with_msg("/manager/maintenance", "Invalid maintenance update request.", True))
                c=db()
                prev=c.execute("SELECT tenant_account,status,assigned_to FROM maintenance_requests WHERE id=?",(rid,)).fetchone()
                if not prev:
                    c.close()
                    return redir(self, with_msg("/manager/maintenance", "Maintenance request was not found.", True))
                if u["role"] != "admin":
                    own = c.execute(
                        "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                        "WHERE l.tenant_account=? AND p.owner_account=? ORDER BY l.id DESC LIMIT 1",
                        (prev["tenant_account"], u["account_number"]),
                    ).fetchone()
                    if not own:
                        c.close()
                        return e403(self)
                if staff_id > 0:
                    staff = c.execute("SELECT name FROM maintenance_staff WHERE id=? AND is_active=1", (staff_id,)).fetchone()
                    if staff:
                        at = (staff["name"] or "").strip()
                c.execute("UPDATE maintenance_requests SET status=?,assigned_to=?,updated_at=datetime('now') WHERE id=?",(st,at,rid))
                if prev and (st != (prev["status"] or "") or at != (prev["assigned_to"] or "")):
                    tgt=c.execute("SELECT id FROM users WHERE account_number=?",(prev["tenant_account"],)).fetchone()
                    if tgt:
                        create_notification(c,tgt["id"],f"Maintenance request #{rid} updated to {st}", "/tenant/maintenance")
                audit_log(c, u, "maintenance_updated", "maintenance_requests", rid, f"status={st};assigned_to={at}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/maintenance", f"Maintenance request #{rid} updated."))
            if path=="/manager/checks/update":
                if not self._req_action(u, "manager.ops.update"): return
                cid=to_int(f.get("check_id"), 0);st=(f.get("status") or "requested").strip()
                if cid<=0 or st not in ("requested","scheduled","completed","cancelled"):return redir(self, with_msg("/manager/checks", "Invalid property-check update request.", True))
                c=db()
                row=c.execute("SELECT requester_account,status,property_id FROM property_checks WHERE id=?",(cid,)).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/manager/checks", "Property check was not found.", True))
                if u["role"] != "admin":
                    own = c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?",(row["property_id"],u["account_number"])).fetchone()
                    if not own:
                        c.close()
                        return e403(self)
                c.execute("UPDATE property_checks SET status=? WHERE id=?",(st,cid))
                if st != (row["status"] or ""):
                    tgt=c.execute("SELECT id FROM users WHERE account_number=?",(row["requester_account"],)).fetchone()
                    if tgt:
                        create_notification(c,tgt["id"],f"Property check #{cid} status updated to {st}", "/landlord/checks")
                audit_log(c, u, "property_check_updated", "property_checks", cid, f"status={st}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/checks", f"Property check #{cid} updated to {st}."))
            if path=="/manager/payments/update":
                if not self._req_action(u, "manager.ops.update"): return
                pay_id=to_int(f.get("payment_id"), 0);st=(f.get("status") or "submitted").strip()
                if pay_id<=0 or st not in ("submitted","paid","failed"):return redir(self, with_msg("/manager/payments", "Invalid payment update request.", True))
                c=db()
                row=c.execute("SELECT payer_account,payer_role,status FROM payments WHERE id=?",(pay_id,)).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/manager/payments", "Payment record was not found.", True))
                if u["role"] != "admin":
                    allowed = False
                    if row["payer_role"] in ("property_manager", "landlord", "manager"):
                        allowed = (row["payer_account"] == u["account_number"])
                    else:
                        own = c.execute(
                            "SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                            "WHERE l.tenant_account=? AND p.owner_account=? ORDER BY l.id DESC LIMIT 1",
                            (row["payer_account"], u["account_number"]),
                        ).fetchone()
                        allowed = bool(own)
                    if not allowed:
                        c.close()
                        return e403(self)
                c.execute("UPDATE payments SET status=? WHERE id=?",(st,pay_id))
                if (row["payer_role"] or "").strip() == "tenant":
                    sync_ledger_from_payments(c, payment_id=pay_id)
                    reconcile_tenant_ledger(c, row["payer_account"])
                if st != (row["status"] or ""):
                    tgt=c.execute("SELECT id FROM users WHERE account_number=?",(row["payer_account"],)).fetchone()
                    if tgt:
                        create_notification(c,tgt["id"],f"Payment #{pay_id} status: {st}", "/notifications")
                audit_log(c, u, "payment_status_updated", "payments", pay_id, f"status={st}")
                c.commit();c.close()
                return redir(self, with_msg("/manager/payments", f"Payment #{pay_id} updated to {st}."))

            if path=="/manager/listings/action":
                if u["role"] != "admin":
                    return redir(self,"/manager/listing-requests")
                lid=int(f.get("listing_id")or"0")if(str(f.get("listing_id")or"0")).isdigit()else 0
                act=(f.get("action")or"").strip()
                if lid>0:
                    c=db()
                    if act=="approve":
                        c.execute("UPDATE listings SET is_approved=1 WHERE id=?",(lid,))
                    elif act=="reject":
                        c.execute("UPDATE listings SET is_approved=0 WHERE id=?",(lid,))
                    elif act=="toggle_available":
                        row=c.execute("SELECT is_available FROM listings WHERE id=?",(lid,)).fetchone()
                        if row:
                            nv=0 if int(row["is_available"]) else 1
                            c.execute("UPDATE listings SET is_available=? WHERE id=?",(nv,lid))
                    c.commit();c.close()
                return redir(self,"/manager/listings")

            if path=="/manager/listings/edit":
                if u["role"] != "admin":
                    return redir(self,"/manager/listing-requests")
                lid=int(f.get("listing_id")or"0")if(str(f.get("listing_id")or"0")).isdigit()else 0
                if lid<=0:return redir(self,"/manager/listings")
                title=(f.get("title")or"").strip()
                loc=(f.get("location")or"").strip()
                cat=(f.get("category")or"").strip()
                desc=(f.get("description")or"").strip()
                price=int(f.get("price")or"0") if str(f.get("price")or"0").isdigit() else 0
                beds=int(f.get("beds")or"0") if str(f.get("beds")or"0").isdigit() else 0
                baths=int(f.get("baths")or"0") if str(f.get("baths")or"0").isdigit() else 0
                if not title or not loc or not desc or price<=0 or beds<=0 or baths<=0:
                    return redir(self,f"/manager/listings/edit?id={lid}")
                c=db()
                c.execute("UPDATE listings SET title=?,price=?,location=?,beds=?,baths=?,category=?,description=? WHERE id=?",
                          (title,price,loc,beds,baths,cat,desc,lid))
                c.commit();c.close()
                return redir(self,f"/manager/listings/edit?id={lid}")

            if path=="/manager/listings/photos":
                if u["role"] != "admin":
                    return redir(self,"/manager/listing-requests")
                lid=int(f.get("listing_id")or"0")if(str(f.get("listing_id")or"0")).isdigit()else 0
                if lid<=0:return redir(self,"/manager/listings")
                c=db()
                # Save up to 5 uploaded photos.
                for k in ("photo1","photo2","photo3","photo4","photo5"):
                    up=getattr(self,"_files",{}).get(k)
                    rp = save_listing_photo(c, u["id"], lid, up)
                    if rp:
                        # If listing has no thumbnail yet, set it.
                        row=c.execute("SELECT image_url FROM listings WHERE id=?",(lid,)).fetchone()
                        if row and (not (row["image_url"] or "").strip()):
                            c.execute("UPDATE listings SET image_url=? WHERE id=?",(rp,lid))
                c.commit();c.close()
                return redir(self,f"/manager/listings/edit?id={lid}")

            if path=="/manager/listings/thumbnail":
                if u["role"] != "admin":
                    return redir(self,"/manager/listing-requests")
                lid=int(f.get("listing_id")or"0")if(str(f.get("listing_id")or"0")).isdigit()else 0
                pth=(f.get("path")or"").strip()
                if lid>0 and pth.startswith("/uploads/"):
                    c=db()
                    c.execute("UPDATE listings SET image_url=? WHERE id=?",(pth,lid))
                    c.commit();c.close()
                return redir(self,f"/manager/listings/edit?id={lid}")

            if path=="/manager/listings/photo_delete":
                if u["role"] != "admin":
                    return redir(self,"/manager/listing-requests")
                lid=int(f.get("listing_id")or"0")if(str(f.get("listing_id")or"0")).isdigit()else 0
                uid=int(f.get("upload_id")or"0")if(str(f.get("upload_id")or"0")).isdigit()else 0
                if lid>0 and uid>0:
                    c=db()
                    row=c.execute("SELECT id,path FROM uploads WHERE id=? AND kind='listing_photo' AND related_table='listings' AND related_id=?",(uid,lid)).fetchone()
                    if row:
                        # delete file if present
                        rel=row["path"].replace("/uploads/","",1)
                        fp=UPLOAD_DIR/rel
                        try:
                            if fp.exists() and fp.is_file():
                                fp.unlink()
                        except: 
                            pass
                        c.execute("DELETE FROM uploads WHERE id=?",(uid,))
                        # if this was thumbnail, set to latest remaining or keep existing
                        th=c.execute("SELECT image_url FROM listings WHERE id=?",(lid,)).fetchone()
                        if th and th["image_url"]==row["path"]:
                            rem=c.execute("SELECT path FROM uploads WHERE kind='listing_photo' AND related_table='listings' AND related_id=? ORDER BY created_at DESC, id DESC LIMIT 1",(lid,)).fetchone()
                            c.execute("UPDATE listings SET image_url=? WHERE id=?",(rem["path"] if rem else "/static/img/listing1.svg", lid))
                    c.commit();c.close()
                return redir(self,f"/manager/listings/edit?id={lid}")

            return e404(self)

        def _manager_tenants_get(self, u):
            q = parse_qs(urlparse(self.path).query)
            msg = (q.get("msg") or [""])[0].strip()
            err = (q.get("err") or ["0"])[0] == "1"
            search = (q.get("q") or [""])[0].strip()
            status_filter = (q.get("status") or [""])[0].strip().lower()
            if status_filter not in ("", "pending", "accepted", "declined", "cancelled"):
                status_filter = ""
            sort = (q.get("sort") or ["newest"])[0].strip().lower()
            order = "DESC" if sort != "oldest" else "ASC"
            page, per, offset = parse_page_params(q, default_per=20, max_per=100)
            message_box = ""
            if msg:
                klass = "notice err" if err else "notice"
                message_box = f'<div class="{klass}" style="margin-bottom:10px;">{esc(msg)}</div>'

            c = db()
            cleanup_expired_invites(c)
            if u["role"] == "admin":
                props = c.execute("SELECT id,name FROM properties ORDER BY created_at DESC").fetchall()
                active = c.execute(
                    "SELECT l.id,l.tenant_account,l.property_id,l.unit_label,l.start_date,uu.full_name AS tenant_name,p.name AS property_name "
                    "FROM tenant_leases l "
                    "LEFT JOIN users uu ON uu.account_number=l.tenant_account "
                    "LEFT JOIN properties p ON p.id=l.property_id "
                    "WHERE l.is_active=1 "
                    "ORDER BY l.created_at DESC,l.id DESC"
                ).fetchall()
                invites_sql = (
                    "SELECT i.*, tu.full_name AS tenant_name,p.name AS property_name "
                    "FROM tenant_property_invites i "
                    "LEFT JOIN users tu ON tu.id=i.tenant_user_id "
                    "LEFT JOIN properties p ON p.id=i.property_id "
                    "WHERE 1=1 "
                )
                invites_args = []
            else:
                props = c.execute("SELECT id,name FROM properties WHERE owner_account=? ORDER BY created_at DESC",(u["account_number"],)).fetchall()
                active = c.execute(
                    "SELECT l.id,l.tenant_account,l.property_id,l.unit_label,l.start_date,uu.full_name AS tenant_name,p.name AS property_name "
                    "FROM tenant_leases l "
                    "LEFT JOIN users uu ON uu.account_number=l.tenant_account "
                    "LEFT JOIN properties p ON p.id=l.property_id "
                    "WHERE l.is_active=1 AND p.owner_account=? "
                    "ORDER BY l.created_at DESC,l.id DESC",
                    (u["account_number"],)
                ).fetchall()
                invites_sql = (
                    "SELECT i.*, tu.full_name AS tenant_name,p.name AS property_name "
                    "FROM tenant_property_invites i "
                    "LEFT JOIN users tu ON tu.id=i.tenant_user_id "
                    "LEFT JOIN properties p ON p.id=i.property_id "
                    "WHERE p.owner_account=? "
                )
                invites_args = [u["account_number"]]
            if status_filter:
                invites_sql += "AND i.status=? "
                invites_args.append(status_filter)
            if search:
                s = "%" + search.lower() + "%"
                invites_sql += "AND (LOWER(COALESCE(i.tenant_account,'')) LIKE ? OR LOWER(COALESCE(i.property_id,'')) LIKE ? OR LOWER(COALESCE(i.unit_label,'')) LIKE ? OR LOWER(COALESCE(p.name,'')) LIKE ? OR LOWER(COALESCE(tu.full_name,'')) LIKE ?) "
                invites_args.extend([s, s, s, s, s])
            invites_count = c.execute("SELECT COUNT(1) AS n FROM (" + invites_sql + ") t", tuple(invites_args)).fetchone()["n"]
            invites = c.execute(
                invites_sql + f"ORDER BY i.created_at {order}, i.id {order} LIMIT ? OFFSET ?",
                tuple(invites_args + [per, offset]),
            ).fetchall()
            c.close()

            property_options = "".join(
                f'<option value="{esc(p["id"])}">{esc(p["name"])} ({esc(p["id"])})</option>'
                for p in props
            )
            active_rows = ""
            for r in active:
                active_rows += (
                    "<tr>"
                    f"<td>{esc(r['tenant_name'] or '-')}</td>"
                    f"<td>{esc(r['tenant_account'])}</td>"
                    f"<td>{esc(r['property_name'] or r['property_id'])}</td>"
                    f"<td>{esc(r['unit_label'])}</td>"
                    f"<td>{esc(r['start_date'])}</td>"
                    "<td>"
                    "<form method='POST' action='/manager/leases/end' style='margin:0;'>"
                    f"<input type='hidden' name='lease_id' value='{r['id']}'>"
                    "<button class='ghost-btn' type='submit'>Remove</button>"
                    "</form>"
                    "</td>"
                    "</tr>"
                )
            active_empty = "" if active else '<div class="notice" style="margin-top:10px;">No active tenant links yet.</div>'

            invite_rows = ""
            for r in invites:
                st = (r["status"] or "").strip().lower()
                cls = "badge"
                if st == "accepted":
                    cls = "badge ok"
                elif st in ("declined", "cancelled"):
                    cls = "badge no"
                action_html = "<span class='muted'>-</span>"
                if st == "pending":
                    action_html = (
                        "<form method='POST' action='/manager/tenant/invite/cancel' style='margin:0;'>"
                        f"<input type='hidden' name='invite_id' value='{r['id']}'>"
                        "<button class='ghost-btn' type='submit'>Cancel</button>"
                        "</form>"
                    )
                elif st in ("declined", "cancelled"):
                    action_html = (
                        "<form method='POST' action='/manager/tenant/invite/resend' style='margin:0;'>"
                        f"<input type='hidden' name='invite_id' value='{r['id']}'>"
                        "<button class='ghost-btn' type='submit'>Resend</button>"
                        "</form>"
                    )
                invite_rows += (
                    "<tr>"
                    f"<td>#{r['id']}</td>"
                    f"<td>{esc(r['tenant_name'] or r['tenant_account'])}</td>"
                    f"<td>{esc(r['property_name'] or r['property_id'])}</td>"
                    f"<td>{esc(r['unit_label'])}</td>"
                    f"<td><span class='{cls}'>{esc(st)}</span></td>"
                    f"<td>{esc(r['created_at'])}</td>"
                    f"<td>{esc(r['responded_at'] or '-')}</td>"
                    f"<td>{action_html}</td>"
                    "</tr>"
                )
            invite_empty = "" if invites else '<div class="notice" style="margin-top:10px;">No invites sent yet.</div>'
            invite_empty += pager_html("/manager/tenants", q, page, per, invites_count)

            return send_html(
                self,
                render(
                    "manager_tenants.html",
                    title="Tenant Sync",
                    nav_right=nav(u, "/manager/tenants"),
                    nav_menu=nav_menu(u, "/manager/tenants"),
                    message_box=message_box,
                    property_options=property_options,
                    active_rows=active_rows,
                    active_empty=active_empty,
                    invite_rows=invite_rows,
                    invite_empty=invite_empty,
                    scripts="""
<script>(function(){
function escHtml(v){
  return String(v||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
}
function fetchUnits(pid, done){
  if(!pid){ done([]); return; }
  fetch("/api/units?property_id="+encodeURIComponent(pid))
    .then(function(r){ return r.json(); })
    .then(function(d){ if(!d || !d.ok){ done([]); return; } done(Array.isArray(d.units)?d.units:[]); })
    .catch(function(){ done([]); });
}
function loadInviteUnits(){
  var p=document.getElementById("managerTenantPropertySelect");
  var u=document.getElementById("managerTenantUnitSelect");
  if(!p||!u){ return; }
  var pid=p.value||"";
  u.innerHTML='<option value="">Select...</option>';
  fetchUnits(pid, function(units){
    units.forEach(function(x){
      var o=document.createElement("option");
      o.value=String(x.unit_label||"");
      o.textContent=String(x.unit_label||"") + (x.is_occupied ? " (occupied)" : "");
      o.disabled=!!x.is_occupied;
      u.appendChild(o);
    });
  });
}
function loadListingRows(){
  var p=document.getElementById("managerListingPropertySelect");
  var body=document.getElementById("managerListingRows");
  var unitIds=document.getElementById("managerListingUnitIds");
  if(!p||!body||!unitIds){ return; }
  var pid=p.value||"";
  body.innerHTML='<tr><td colspan="7" class="muted">Loading units...</td></tr>';
  unitIds.value="";
  if(!pid){
    body.innerHTML='<tr><td colspan="7" class="muted">Select a property to load units.</td></tr>';
    return;
  }
  fetchUnits(pid, function(units){
    var ids=[];
    var rows=[];
    units.forEach(function(x){
      var uid = Number(x.unit_id||0);
      if(!uid){ return; }
      ids.push(String(uid));
      var label = String(x.unit_label||("Unit "+uid));
      var occupied = !!x.is_occupied;
      var checked = occupied ? "" : "checked";
      var disabled = occupied ? "disabled" : "";
      var title = pid + " - " + label;
      var desc = label + " at " + pid + ".";
      rows.push(
        "<tr>" +
        "<td><input type='checkbox' name='sel_"+uid+"' value='1' "+checked+" "+disabled+"></td>" +
        "<td>"+escHtml(label)+(occupied ? " <span class='badge'>occupied</span>" : "")+"</td>" +
        "<td><input name='title_"+uid+"' value='"+escHtml(title)+"' "+disabled+"></td>" +
        "<td><input type='number' min='0' name='price_"+uid+"' value='"+Number(x.rent||0)+"' style='width:110px;' "+disabled+"></td>" +
        "<td><input type='number' min='0' name='beds_"+uid+"' value='"+Number(x.beds||0)+"' style='width:90px;' "+disabled+"></td>" +
        "<td><input type='number' min='0' name='baths_"+uid+"' value='"+Number(x.baths||0)+"' style='width:90px;' "+disabled+"></td>" +
        "<td><input name='description_"+uid+"' value='"+escHtml(desc)+"' "+disabled+"></td>" +
        "</tr>"
      );
    });
    unitIds.value = ids.join(",");
    body.innerHTML = rows.length ? rows.join("") : '<tr><td colspan="7" class="muted">No units found for this property.</td></tr>';
  });
}
document.addEventListener("DOMContentLoaded", function(){
  var p=document.getElementById("managerTenantPropertySelect");
  if(p){ p.addEventListener("change", loadInviteUnits); }
  var lp=document.getElementById("managerListingPropertySelect");
  if(lp){ lp.addEventListener("change", loadListingRows); }
  loadInviteUnits();
  loadListingRows();
});
})();</script>
""",
                ),
            )

        def _manager_tenant_invite(self, f, u):
            tenant_ident = (f.get("tenant_ident") or "").strip()
            pid = (f.get("property_id") or "").strip()
            unit_label = (f.get("unit_label") or "").strip()
            message = (f.get("message") or "").strip()
            auto_unit = str(f.get("auto_unit") or "").strip().lower() in ("1", "true", "yes", "on")
            c = db()
            if not unit_label and auto_unit and len(pid) >= 5:
                row = c.execute(
                    "SELECT u.unit_label FROM units u "
                    "WHERE u.property_id=? AND u.is_occupied=0 "
                    "AND NOT EXISTS("
                    "  SELECT 1 FROM tenant_leases l WHERE l.property_id=u.property_id AND l.unit_label=u.unit_label AND l.is_active=1"
                    ") ORDER BY u.id LIMIT 1",
                    (pid,),
                ).fetchone()
                if row:
                    unit_label = (row["unit_label"] or "").strip()
            if not unit_label:
                c.close()
                return redir(self, with_msg("/manager/tenants", "Select a unit label or enable auto-select.", True))
            ok, note = create_tenant_property_invite(
                c,
                u,
                tenant_ident,
                pid,
                unit_label,
                message=message,
                owner_account=(None if u["role"] == "admin" else u["account_number"]),
            )
            if ok:
                c.commit()
            c.close()
            return redir(self, with_msg("/manager/tenants", note, err=(not ok)))

        def _manager_inquiries_get(self, u):
            u=self._req_role(u,"manager",action="manager.portal")
            if not u:return
            q = parse_qs(urlparse(self.path).query)
            status_filter = ((q.get("status") or [""])[0]).strip().lower()
            if status_filter not in ("", "new", "open", "closed"):
                status_filter = ""
            search = ((q.get("q") or [""])[0]).strip().lower()
            sort = ((q.get("sort") or ["newest"])[0]).strip().lower()
            order_sql = "i.created_at ASC, i.id ASC" if sort == "oldest" else "i.created_at DESC, i.id DESC"
            page, per, offset = parse_page_params(q, default_per=20, max_per=200)
            sql = (
                "SELECT i.*, COALESCE(l.title,'(General)') AS listing_title "
                "FROM inquiries i LEFT JOIN listings l ON l.id=i.listing_id "
                "WHERE 1=1 "
            )
            args = []
            if status_filter:
                sql += "AND i.status=? "
                args.append(status_filter)
            if search:
                s = "%" + search + "%"
                sql += (
                    "AND (CAST(i.id AS TEXT) LIKE ? OR LOWER(COALESCE(i.full_name,'')) LIKE ? OR LOWER(COALESCE(i.email,'')) LIKE ? OR "
                    "LOWER(COALESCE(i.subject,'')) LIKE ? OR LOWER(COALESCE(i.body,'')) LIKE ? OR LOWER(COALESCE(l.title,'')) LIKE ?) "
                )
                args.extend([s, s, s, s, s, s])
            c=db()
            total = c.execute("SELECT COUNT(1) AS n FROM (" + sql + ") t", tuple(args)).fetchone()["n"]
            rows=c.execute(sql + f"ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(args + [per, offset])).fetchall()
            html=""
            for r in rows:
                html += f'''
                <div class="card">
                  <div class="row between">
                    <div><b>{esc(r["full_name"])}</b> â€¢ {esc(r["email"])} â€¢ {esc(r["phone"] or "")}</div>
                    <div class="muted">{esc(r["created_at"])}</div>
                  </div>
                  <div class="muted">Listing: {esc(r["listing_title"])}</div>
                  <div class="muted">Subject: {esc(r["subject"] or "")}</div>
                  <div style="margin-top:8px;">{esc(r["body"])}</div>
                  <form method="POST" action="/manager/inquiries/update" class="row" style="margin-top:10px;gap:8px;">
                    <input type="hidden" name="id" value="{r["id"]}">
                    <select name="status">
                      <option value="new" {"selected" if r["status"]=="new" else ""}>new</option>
                      <option value="open" {"selected" if r["status"]=="open" else ""}>open</option>
                      <option value="closed" {"selected" if r["status"]=="closed" else ""}>closed</option>
                    </select>
                    <button class="btn" type="submit">Update</button>
                  </form>
                </div>'''
            c.close()
            if not html:
                html = '<div class="notice">No inquiries found for this filter.</div>'
            filters_form = (
                "<div class='card' style='margin-bottom:10px;'>"
                "<form method='GET' action='/manager/inquiries' class='row' style='align-items:flex-end;'>"
                "<div class='field' style='min-width:140px;'><label>Status</label>"
                f"<select name='status'><option value=''>All</option><option value='new' {'selected' if status_filter=='new' else ''}>new</option>"
                f"<option value='open' {'selected' if status_filter=='open' else ''}>open</option><option value='closed' {'selected' if status_filter=='closed' else ''}>closed</option></select></div>"
                f"<div class='field' style='min-width:240px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='id/name/email/subject/listing'></div>"
                "<div class='field' style='min-width:150px;'><label>Sort</label>"
                f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                "<button class='primary-btn' type='submit'>Apply</button>"
                "<a class='ghost-btn' href='/manager/inquiries'>Reset</a>"
                "</form>"
                "</div>"
            )
            export_q = urlencode(query_without_page(q))
            export_filtered_url = "/manager/inquiries/export" + (f"?{export_q}" if export_q else "")
            return send_html(
                self,
                render(
                    "manager_inquiries.html",
                    title="Inquiries",
                    nav_right=nav(u,"/manager/inquiries"),
                    nav_menu=nav_menu(u,"/manager/inquiries"),
                    message_box=query_message_box(q),
                    filters_form=filters_form,
                    inquiries_html=html,
                    pager_box=pager_html("/manager/inquiries", q, page, per, total),
                    export_filtered_url=export_filtered_url,
                ),
            )

        def _manager_inquiries_update(self, f, u):
            u=self._req_role(u,"manager",action="manager.ops.update")
            if not u:return
            iid=to_int(f.get("id"), 0)
            if iid <= 0:return redir(self, with_msg("/manager/inquiries", "Inquiry ID is missing.", True))
            st=(f.get("status") or "new").strip()
            if st not in ("new","open","closed"): st="new"
            c=db()
            row = c.execute("SELECT id FROM inquiries WHERE id=?", (iid,)).fetchone()
            if not row:
                c.close()
                return redir(self, with_msg("/manager/inquiries", "Inquiry was not found.", True))
            c.execute("UPDATE inquiries SET status=? WHERE id=?",(st,iid))
            audit_log(c, u, "inquiry_status_updated", "inquiries", iid, f"status={st}")
            c.commit();c.close()
            return redir(self, with_msg("/manager/inquiries", f"Inquiry #{iid} updated to {st}."))

        def _manager_applications_get(self, u):
            u=self._req_role(u,"manager",action="manager.portal")
            if not u:return
            q = parse_qs(urlparse(self.path).query)
            status_filter = ((q.get("status") or [""])[0]).strip().lower()
            if status_filter not in ("", "submitted", "under_review", "approved", "denied"):
                status_filter = ""
            search = ((q.get("q") or [""])[0]).strip().lower()
            sort = ((q.get("sort") or ["newest"])[0]).strip().lower()
            order_sql = "a.created_at ASC, a.id ASC" if sort == "oldest" else "a.created_at DESC, a.id DESC"
            page, per, offset = parse_page_params(q, default_per=20, max_per=200)
            sql = (
                "SELECT a.*, l.title AS listing_title FROM applications a "
                "JOIN listings l ON l.id=a.listing_id WHERE 1=1 "
            )
            args = []
            if status_filter:
                sql += "AND a.status=? "
                args.append(status_filter)
            if search:
                s = "%" + search + "%"
                sql += (
                    "AND (CAST(a.id AS TEXT) LIKE ? OR LOWER(COALESCE(a.full_name,'')) LIKE ? OR LOWER(COALESCE(a.email,'')) LIKE ? OR "
                    "LOWER(COALESCE(a.notes,'')) LIKE ? OR LOWER(COALESCE(l.title,'')) LIKE ?) "
                )
                args.extend([s, s, s, s, s])
            c=db()
            total = c.execute("SELECT COUNT(1) AS n FROM (" + sql + ") t", tuple(args)).fetchone()["n"]
            rows=c.execute(sql + f"ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(args + [per, offset])).fetchall()
            html=""
            for r in rows:
                html += f'''
                <div class="card">
                  <div class="row between">
                    <div><b>{esc(r["full_name"])}</b> â€¢ {esc(r["email"])} â€¢ {esc(r["phone"] or "")}</div>
                    <div class="muted">{esc(r["created_at"])}</div>
                  </div>
                  <div class="muted">Listing: {esc(r["listing_title"])}</div>
                  <div class="muted">Income: {esc(r["income"] or "")}</div>
                  <div style="margin-top:8px;">{esc(r["notes"] or "")}</div>
                  <form method="POST" action="/manager/applications/update" class="row" style="margin-top:10px;gap:8px;">
                    <input type="hidden" name="id" value="{r["id"]}">
                    <select name="status">
                      <option value="submitted" {"selected" if r["status"]=="submitted" else ""}>submitted</option>
                      <option value="under_review" {"selected" if r["status"]=="under_review" else ""}>under_review</option>
                      <option value="approved" {"selected" if r["status"]=="approved" else ""}>approved</option>
                      <option value="denied" {"selected" if r["status"]=="denied" else ""}>denied</option>
                    </select>
                    <button class="btn" type="submit">Update</button>
                  </form>
                </div>'''
            c.close()
            if not html:
                html = '<div class="notice">No applications found for this filter.</div>'
            filters_form = (
                "<div class='card' style='margin-bottom:10px;'>"
                "<form method='GET' action='/manager/applications' class='row' style='align-items:flex-end;'>"
                "<div class='field' style='min-width:170px;'><label>Status</label>"
                f"<select name='status'><option value=''>All</option><option value='submitted' {'selected' if status_filter=='submitted' else ''}>submitted</option>"
                f"<option value='under_review' {'selected' if status_filter=='under_review' else ''}>under_review</option>"
                f"<option value='approved' {'selected' if status_filter=='approved' else ''}>approved</option>"
                f"<option value='denied' {'selected' if status_filter=='denied' else ''}>denied</option></select></div>"
                f"<div class='field' style='min-width:240px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='id/name/email/listing'></div>"
                "<div class='field' style='min-width:150px;'><label>Sort</label>"
                f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                "<button class='primary-btn' type='submit'>Apply</button>"
                "<a class='ghost-btn' href='/manager/applications'>Reset</a>"
                "</form>"
                "</div>"
            )
            export_q = urlencode(query_without_page(q))
            export_filtered_url = "/manager/applications/export" + (f"?{export_q}" if export_q else "")
            return send_html(
                self,
                render(
                    "manager_applications.html",
                    title="Applications",
                    nav_right=nav(u,"/manager/applications"),
                    nav_menu=nav_menu(u,"/manager/applications"),
                    message_box=query_message_box(q),
                    filters_form=filters_form,
                    applications_html=html,
                    pager_box=pager_html("/manager/applications", q, page, per, total),
                    export_filtered_url=export_filtered_url,
                ),
            )

        def _manager_applications_update(self, f, u):
            u=self._req_role(u,"manager",action="manager.ops.update")
            if not u:return
            aid=to_int(f.get("id"), 0)
            if aid <= 0:return redir(self, with_msg("/manager/applications", "Application ID is missing.", True))
            st=(f.get("status") or "submitted").strip()
            if st not in ("submitted","under_review","approved","denied"): st="submitted"
            c=db()
            row=c.execute("SELECT applicant_user_id FROM applications WHERE id=?",(aid,)).fetchone()
            if not row:
                c.close()
                return redir(self, with_msg("/manager/applications", "Application was not found.", True))
            c.execute("UPDATE applications SET status=?, updated_at=datetime('now') WHERE id=?",(st,aid))
            if row and row["applicant_user_id"]:
                create_notification(c,row["applicant_user_id"],f"Your application status: {st.replace('_',' ')}", "/notifications")
            audit_log(c, u, "application_status_updated", "applications", aid, f"status={st}")
            c.commit();c.close()
            return redir(self, with_msg("/manager/applications", f"Application #{aid} updated to {st}."))

        def _manager_inquiries_export(self, u):
            u=self._req_role(u,"manager",action="manager.portal")
            if not u:return
            q = parse_qs(urlparse(self.path).query)
            status_filter = ((q.get("status") or [""])[0]).strip().lower()
            if status_filter not in ("", "new", "open", "closed"):
                status_filter = ""
            search = ((q.get("q") or [""])[0]).strip().lower()
            sort = ((q.get("sort") or ["newest"])[0]).strip().lower()
            order_sql = "i.created_at ASC, i.id ASC" if sort == "oldest" else "i.created_at DESC, i.id DESC"
            sql = (
                "SELECT i.id,i.created_at,i.status,COALESCE(l.title,'(General)') AS listing_title,i.full_name,i.email,"
                "COALESCE(i.phone,'') AS phone,COALESCE(i.subject,'') AS subject,COALESCE(i.body,'') AS body "
                "FROM inquiries i LEFT JOIN listings l ON l.id=i.listing_id WHERE 1=1 "
            )
            args = []
            if status_filter:
                sql += "AND i.status=? "
                args.append(status_filter)
            if search:
                s = "%" + search + "%"
                sql += (
                    "AND (LOWER(COALESCE(i.full_name,'')) LIKE ? OR LOWER(COALESCE(i.email,'')) LIKE ? OR "
                    "LOWER(COALESCE(i.subject,'')) LIKE ? OR LOWER(COALESCE(i.body,'')) LIKE ? OR LOWER(COALESCE(l.title,'')) LIKE ?) "
                )
                args.extend([s, s, s, s, s])
            c = db()
            rows_db = c.execute(sql + f"ORDER BY {order_sql} LIMIT 5000", tuple(args)).fetchall()
            c.close()
            rows = [["id", "created_at", "status", "listing", "full_name", "email", "phone", "subject", "body"]]
            for r in rows_db:
                rows.append([r["id"], r["created_at"], r["status"], r["listing_title"], r["full_name"], r["email"], r["phone"], r["subject"], r["body"]])
            return send_csv(self, "atlasbahamas_inquiries.csv", rows)

        def _manager_applications_export(self, u):
            u=self._req_role(u,"manager",action="manager.portal")
            if not u:return
            q = parse_qs(urlparse(self.path).query)
            status_filter = ((q.get("status") or [""])[0]).strip().lower()
            if status_filter not in ("", "submitted", "under_review", "approved", "denied"):
                status_filter = ""
            search = ((q.get("q") or [""])[0]).strip().lower()
            sort = ((q.get("sort") or ["newest"])[0]).strip().lower()
            order_sql = "a.created_at ASC, a.id ASC" if sort == "oldest" else "a.created_at DESC, a.id DESC"
            sql = (
                "SELECT a.id,a.created_at,a.updated_at,a.status,l.title AS listing_title,a.full_name,a.email,"
                "COALESCE(a.phone,'') AS phone,COALESCE(a.income,'') AS income,COALESCE(a.notes,'') AS notes "
                "FROM applications a JOIN listings l ON l.id=a.listing_id WHERE 1=1 "
            )
            args = []
            if status_filter:
                sql += "AND a.status=? "
                args.append(status_filter)
            if search:
                s = "%" + search + "%"
                sql += (
                    "AND (LOWER(COALESCE(a.full_name,'')) LIKE ? OR LOWER(COALESCE(a.email,'')) LIKE ? OR "
                    "LOWER(COALESCE(a.notes,'')) LIKE ? OR LOWER(COALESCE(l.title,'')) LIKE ?) "
                )
                args.extend([s, s, s, s])
            c = db()
            rows_db = c.execute(sql + f"ORDER BY {order_sql} LIMIT 5000", tuple(args)).fetchall()
            c.close()
            rows = [["id", "created_at", "updated_at", "status", "listing", "full_name", "email", "phone", "income", "notes"]]
            for r in rows_db:
                rows.append([r["id"], r["created_at"], r["updated_at"], r["status"], r["listing_title"], r["full_name"], r["email"], r["phone"], r["income"], r["notes"]])
            return send_csv(self, "atlasbahamas_applications.csv", rows)

        def _manager_export_properties(self, u):
            u = self._req_role(u, "manager", action="manager.property.manage")
            if not u:
                return
            q = parse_qs(urlparse(self.path).query)
            search = ((q.get("q") or [""])[0]).strip().lower()
            sql = (
                "SELECT p.id,p.name,p.location,p.property_type,p.units_count,p.created_at,"
                "COALESCE(SUM(CASE WHEN u2.is_occupied=1 THEN 1 ELSE 0 END),0) AS occupied_units "
                "FROM properties p "
                "LEFT JOIN units u2 ON u2.property_id=p.id "
                "WHERE p.owner_account=? "
            )
            args = [u["account_number"]]
            if search:
                s = "%" + search + "%"
                sql += "AND (LOWER(COALESCE(p.id,'')) LIKE ? OR LOWER(COALESCE(p.name,'')) LIKE ? OR LOWER(COALESCE(p.location,'')) LIKE ?) "
                args.extend([s, s, s])
            sql += "GROUP BY p.id,p.name,p.location,p.property_type,p.units_count,p.created_at ORDER BY p.created_at DESC,p.id DESC"
            c = db()
            rows_db = c.execute(sql, tuple(args)).fetchall()
            c.close()
            rows = [["property_id", "name", "location", "property_type", "units_total", "occupied_units", "vacant_units", "created_at"]]
            for r in rows_db:
                total = to_int(r["units_count"], 0)
                occ = to_int(r["occupied_units"], 0)
                rows.append([r["id"], r["name"], r["location"], r["property_type"], total, occ, max(0, total - occ), r["created_at"]])
            return send_csv(self, "atlasbahamas_manager_properties.csv", rows)

        def _manager_listing_requests_export(self, u):
            u = self._req_role(u, "manager", action="manager.listing.submit")
            if not u:
                return
            q = parse_qs(urlparse(self.path).query)
            status_filter = ((q.get("status") or [""])[0]).strip().lower()
            if status_filter not in ("", "pending", "approved", "rejected"):
                status_filter = ""
            property_filter = ((q.get("property") or [""])[0]).strip()
            search = ((q.get("q") or [""])[0]).strip().lower()
            sql = (
                "SELECT r.id,r.property_id,COALESCE(p.name,'') AS property_name,COALESCE(uu.unit_label,'') AS unit_label,"
                "r.title,r.price,r.status,r.created_at,COALESCE(r.approval_note,'') AS approval_note "
                "FROM listing_requests r "
                "LEFT JOIN properties p ON p.id=r.property_id "
                "LEFT JOIN units uu ON uu.id=r.unit_id "
                "WHERE (r.submitted_by_user_id=? OR p.owner_account=?) "
            )
            args = [u["id"], u["account_number"]]
            if status_filter:
                sql += "AND r.status=? "
                args.append(status_filter)
            if property_filter:
                sql += "AND r.property_id=? "
                args.append(property_filter)
            if search:
                s = "%" + search + "%"
                sql += "AND (LOWER(COALESCE(r.title,'')) LIKE ? OR LOWER(COALESCE(p.name,'')) LIKE ? OR LOWER(COALESCE(r.property_id,'')) LIKE ?) "
                args.extend([s, s, s])
            c = db()
            rows_db = c.execute(sql + "ORDER BY r.created_at DESC,r.id DESC LIMIT 5000", tuple(args)).fetchall()
            c.close()
            rows = [["request_id", "property_id", "property_name", "unit_label", "title", "price", "status", "submitted_at", "review_note"]]
            for r in rows_db:
                rows.append([r["id"], r["property_id"], r["property_name"], r["unit_label"], r["title"], to_int(r["price"], 0), r["status"], r["created_at"], r["approval_note"]])
            return send_csv(self, "atlasbahamas_manager_listing_requests.csv", rows)

        def _manager_payments_export(self, u):
            u = self._req_role(u, "manager", action="manager.portal")
            if not u:
                return
            q = parse_qs(urlparse(self.path).query)
            status_filter=((q.get("status") or [""])[0]).strip().lower()
            if status_filter not in ("", "submitted", "paid", "failed"):
                status_filter = ""
            type_filter=((q.get("type") or [""])[0]).strip().lower()
            if type_filter not in ("", "rent", "bill"):
                type_filter = ""
            role_filter=((q.get("role") or [""])[0]).strip().lower()
            if role_filter not in ("", "tenant", "property_manager", "landlord", "manager"):
                role_filter = ""
            search=((q.get("q") or [""])[0]).strip().lower()
            sort=((q.get("sort") or ["newest"])[0]).strip().lower()
            order_sql = {
                "oldest": "p.created_at ASC,p.id ASC",
                "amount_desc": "p.amount DESC,p.id DESC",
                "amount_asc": "p.amount ASC,p.id ASC",
            }.get(sort, "p.created_at DESC,p.id DESC")
            sql = "SELECT p.created_at,p.payer_account,p.payer_role,p.payment_type,COALESCE(p.provider,'') AS provider,p.amount,p.status FROM payments p WHERE 1=1 "
            args = []
            if u["role"] != "admin":
                sql += (
                    "AND ("
                    "(p.payer_role IN ('property_manager','landlord','manager') AND p.payer_account=?) "
                    "OR (p.payer_role='tenant' AND EXISTS("
                    "SELECT 1 FROM tenant_leases l JOIN properties pp ON pp.id=l.property_id "
                    "WHERE l.tenant_account=p.payer_account AND pp.owner_account=? ORDER BY l.id DESC LIMIT 1"
                    "))"
                    ") "
                )
                args.extend([u["account_number"], u["account_number"]])
            if status_filter:
                sql += "AND p.status=? "
                args.append(status_filter)
            if type_filter:
                sql += "AND p.payment_type=? "
                args.append(type_filter)
            if role_filter:
                sql += "AND p.payer_role=? "
                args.append(role_filter)
            if search:
                s = "%" + search + "%"
                sql += "AND (LOWER(COALESCE(p.payer_account,'')) LIKE ? OR LOWER(COALESCE(p.provider,'')) LIKE ?) "
                args.extend([s, s])
            c = db()
            rows_db = c.execute(sql + f"ORDER BY {order_sql} LIMIT 5000", tuple(args)).fetchall()
            c.close()
            rows = [["created_at", "payer_account", "payer_role", "payment_type", "provider", "amount", "status"]]
            for r in rows_db:
                rows.append([r["created_at"], r["payer_account"], r["payer_role"], r["payment_type"], r["provider"], to_int(r["amount"], 0), r["status"]])
            return send_csv(self, "atlasbahamas_payments.csv", rows)



