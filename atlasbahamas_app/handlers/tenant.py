"""TenantHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class TenantHandlerMixin:
        def _tenant_get(self,path,u):
            u=self._req_role(u,"tenant",action="tenant.portal")
            if not u:return
            nr=nav(u,path)
            if path=="/tenant":
                c=db()
                cleanup_expired_invites(c)
                run_automated_rent_notifications(c)
                due=tenant_rent_due(c,u["account_number"])
                lease = active_lease_with_rent(c, u["account_number"])
                pending=c.execute("SELECT * FROM tenant_property_invites WHERE tenant_account=? AND status='pending' ORDER BY created_at DESC LIMIT 5",(u["account_number"],)).fetchall()
                c.commit()
                c.close()
                if due:
                    if to_int(due.get("amount"), 0) <= 0 and (due.get("status") or "") == "paid":
                        rent_due_card = (
                            "<div class='card' style='margin-top:12px;'>"
                            "<h3 style='margin-top:0;'>Rent Due</h3>"
                            f"<div class='row' style='justify-content:space-between;align-items:center;'><div><b>$0</b> balance for {esc(due['property_id'])} / {esc(due['unit_label'])}<div class='muted'>Due date: {esc(due['due_date'])}</div></div>"
                            "<div><span class='badge ok'>paid</span></div></div>"
                            "</div>"
                        )
                    else:
                        state_badge = "badge no" if due["status"]=="late" else "badge ok"
                        split_text = f" ({to_int(due.get('share_percent'), 100)}% share)" if to_int(due.get("share_percent"), 100) < 100 else ""
                        rent_due_card = (
                            "<div class='card' style='margin-top:12px;'>"
                            "<h3 style='margin-top:0;'>Rent Due</h3>"
                            f"<div class='row' style='justify-content:space-between;align-items:center;'><div><b>${due['amount']:,}</b>{split_text} for {esc(due['property_id'])} / {esc(due['unit_label'])}<div class='muted'>Due date: {esc(due['due_date'])}</div></div>"
                            f"<div><span class='{state_badge}'>{esc(due['status'])}</span> <a class='primary-btn' href='/tenant/pay-rent?quick=1'>Pay now</a></div></div>"
                            "</div>"
                        )
                else:
                    rent_due_card = '<div class="card" style="margin-top:12px;"><div class="notice err"><b>No active lease.</b> Rent due card appears after property sync.</div></div>'
                if lease:
                    end_date = (lease.get("end_date") or "").strip()
                    end_dt = _parse_ymd(end_date)
                    if end_dt:
                        days_left = (end_dt.date() - datetime.now(timezone.utc).date()).days
                        if days_left >= 0:
                            lease_timing = f"{days_left} day(s) remaining"
                        else:
                            lease_timing = f"Expired {abs(days_left)} day(s) ago"
                        end_text = end_dt.strftime("%Y-%m-%d")
                    else:
                        lease_timing = "Lease end date not set."
                        end_text = "Not set"
                    lease_summary_card = (
                        "<div class='card' style='margin-top:12px;'>"
                        "<h3 style='margin-top:0;'>Lease at a Glance</h3>"
                        f"<div><b>Unit:</b> {esc(lease['property_id'])} / {esc(lease['unit_label'])}</div>"
                        f"<div><b>Monthly Share:</b> ${to_int(lease.get('rent'),0):,}</div>"
                        f"<div><b>Lease Ends:</b> {esc(end_text)}</div>"
                        f"<div class='muted'>{esc(lease_timing)}</div>"
                        "<div style='margin-top:8px;'><a class='ghost-btn' href='/tenant/lease'>View Full Lease</a></div>"
                        "</div>"
                    )
                else:
                    lease_summary_card = "<div class='card' style='margin-top:12px;'><h3 style='margin-top:0;'>Lease at a Glance</h3><div class='notice'>No lease is currently assigned.</div></div>"
                if pending:
                    pending_rows=""
                    for p in pending:
                        pending_rows += (
                            "<div class='row' style='justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,.1);padding:8px 0;'>"
                            f"<div><b>{esc(p['property_id'])}</b> / {esc(p['unit_label'])}<div class='muted'>{esc(p['created_at'])}</div></div>"
                            "<div class='row'>"
                            "<form method='post' action='/tenant/invite/respond' style='margin:0;'>"
                            f"<input type='hidden' name='invite_id' value='{p['id']}'><input type='hidden' name='action' value='accept'>"
                            "<button class='primary-btn' type='submit'>Accept</button></form>"
                            "<form method='post' action='/tenant/invite/respond' style='margin:0;'>"
                            f"<input type='hidden' name='invite_id' value='{p['id']}'><input type='hidden' name='action' value='decline'>"
                            "<button class='ghost-btn' type='submit'>Decline</button></form>"
                            "</div></div>"
                        )
                    alerts_widget = f"<div class='card' style='margin-top:12px;'><h3 style='margin-top:0;'>Pending Alerts</h3>{pending_rows}<div style='margin-top:8px;'><a class='ghost-btn' href='/notifications'>Open All Alerts</a></div></div>"
                else:
                    alerts_widget = "<div class='card' style='margin-top:12px;'><h3 style='margin-top:0;'>Pending Alerts</h3><div class='notice'>No pending invite actions.</div></div>"
                return send_html(self,render("tenant_home.html",title="Tenant Dashboard",nav_right=nr,nav_menu=nav_menu(u,path),rent_due_card=rent_due_card,lease_summary_card=lease_summary_card,alerts_widget=alerts_widget))
            m_receipt=re.match(r"^/tenant/payment/receipt$",path)
            if m_receipt:
                q=parse_qs(urlparse(self.path).query);pid=to_int((q.get("id") or ["0"])[0],0)
                if pid<=0:return e404(self)
                c=db();p=c.execute("SELECT * FROM payments WHERE id=? AND payer_account=?",(pid,u["account_number"])).fetchone();c.close()
                if not p:return e404(self)
                msg_box = query_message_box(q)
                body=(
                    "<section class='public'><div class='public-inner'><div class='card' style='max-width:760px;'>"
                    f"{msg_box}"
                    f"<h2>Payment Receipt #{p['id']}</h2>"
                    f"<div class='muted'>Date: {esc(p['created_at'])}</div>"
                    f"<div style='margin-top:10px;'><b>Type:</b> {esc(p['payment_type'])}</div>"
                    f"<div><b>Provider:</b> {esc(p['provider'] or '-')}</div>"
                    f"<div><b>Amount:</b> ${int(p['amount']):,}</div>"
                    f"<div><b>Status:</b> {status_badge(p['status'], 'payment')}</div>"
                    "<div class='row' style='margin-top:14px;'><a class='primary-btn' href='/tenant/payments'>Back to Payments</a><a class='ghost-btn' href='/tenant'>Back to Dashboard</a><button class='ghost-btn' type='button' onclick='window.print()'>Print</button></div>"
                    "</div></div></section>"
                ).encode("utf-8")
                return send_html(self,body)
            if path=="/tenant/payment/confirmation":
                q2=parse_qs(urlparse(self.path).query)
                pid=to_int((q2.get("id") or ["0"])[0],0)
                if pid<=0:
                    return redir(self, "/tenant/payments")
                c=db()
                p = c.execute("SELECT * FROM payments WHERE id=? AND payer_account=?",(pid,u["account_number"])).fetchone()
                c.close()
                if not p:
                    return redir(self, "/tenant/payments")
                return send_html(
                    self,
                    render(
                        "tenant_payment_confirmation.html",
                        title="Payment Confirmation",
                        nav_right=nr,
                        nav_menu=nav_menu(u,path),
                        message_box=query_message_box(q2),
                        payment_id=str(p["id"]),
                        amount=f"${to_int(p['amount'],0):,}",
                        payment_type=esc(p["payment_type"]),
                        provider=esc(p["provider"] or "manual"),
                        created_at=esc(p["created_at"]),
                        status_badge=status_badge(p["status"], "payment"),
                    ),
                )
            if path=="/tenant/maintenance/confirmation":
                q2=parse_qs(urlparse(self.path).query)
                rid=to_int((q2.get("id") or ["0"])[0],0)
                if rid<=0:
                    return redir(self, "/tenant/maintenance")
                c=db()
                row = c.execute("SELECT * FROM maintenance_requests WHERE id=? AND tenant_account=?",(rid,u["account_number"])).fetchone()
                c.close()
                if not row:
                    return redir(self, "/tenant/maintenance")
                return send_html(
                    self,
                    render(
                        "tenant_maintenance_confirmation.html",
                        title=f"Maintenance #{rid}",
                        nav_right=nr,
                        nav_menu=nav_menu(u,path),
                        message_box=query_message_box(q2),
                        request_id=str(rid),
                        urgency_badge=status_badge((row["urgency"] or "normal"), "priority"),
                        status_badge=status_badge((row["status"] or "open"), "maintenance"),
                        created_at=esc(row["created_at"]),
                        description=esc((row["description"] or "")[:220]),
                    ),
                )
            if path=="/tenant/pay-rent":
                q2=parse_qs(urlparse(self.path).query)
                message_box = query_message_box(q2)
                c=db()
                ls=active_lease_with_rent(c, u["account_number"])
                ledger=ensure_tenant_ledger_current(c, u["account_number"]) if ls else {"balance": 0}
                methods = tenant_saved_methods(c, u["id"])
                autopay = c.execute(
                    "SELECT * FROM tenant_autopay WHERE tenant_user_id=? LIMIT 1",
                    (u["id"],),
                ).fetchone()
                c.commit()
                c.close()
                default_amount = "0"
                payment_method_options = "<option value=''>Manual entry (no saved method)</option>"
                for m in methods:
                    payment_method_options += (
                        f"<option value='{m['id']}' {'selected' if to_int(m['is_default'],0) else ''}>"
                        f"{esc(format_payment_method_label(m))}</option>"
                    )
                if methods:
                    saved_method_box = "<div class='notice' style='margin-top:10px;'><b>Saved methods:</b> " + ", ".join(esc(format_payment_method_label(m)) for m in methods[:3]) + "</div>"
                else:
                    saved_method_box = "<div class='notice err' style='margin-top:10px;'><b>No saved methods.</b> Add one in Payment Methods for faster checkout.</div>"
                if autopay and to_int(autopay["is_enabled"], 0):
                    saved_method_box += "<div class='notice' style='margin-top:8px;'>Autopay is currently enabled for this account.</div>"
                if ls:
                    split_text = f" ({to_int(ls.get('share_percent'), 100)}% share)" if to_int(ls.get("share_percent"), 100) < 100 else ""
                    today = datetime.now(timezone.utc).date()
                    due_date = today.replace(day=1).isoformat()
                    due_status = "late" if (today > today.replace(day=1) and to_int(ledger.get("balance"), 0) > 0) else ("paid" if to_int(ledger.get("balance"), 0) <= 0 else "due")
                    due_row = f"<div class='muted'>Due: {esc(due_date)} - Status: {esc(due_status)}</div>"
                    box = (
                        f'<div class="notice"><b>Active lease:</b> {esc(ls["property_id"])} - {esc(ls["unit_label"])}{split_text}'
                        f"<div class='muted'>Suggested rent payment: ${to_int(ls.get('rent'),0):,}</div>"
                        f"{due_row}"
                        f"<div class='muted'>Ledger balance: ${to_int(ledger.get('balance'),0):,}</div>"
                        "</div>"
                    )
                    default_amount = str(max(0, to_int(ls.get("rent"), 0)))
                else:
                    box = '<div class="notice err"><b>No active lease.</b> Property Manager must assign first.</div>'
                return send_html(self,render("tenant_pay_rent.html",title="Pay Rent",nav_right=nr,nav_menu=nav_menu(u,path),message_box=message_box,lease_box=box,saved_method_box=saved_method_box,payment_method_options=payment_method_options,default_amount=default_amount))
            if path=="/tenant/pay-bills":
                q2=parse_qs(urlparse(self.path).query)
                return send_html(self,render("tenant_pay_bills.html",title="Pay Bill",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2)))
            if path=="/tenant/payments":
                q2=parse_qs(urlparse(self.path).query)
                status_filter=((q2.get("status") or [""])[0]).strip().lower()
                if status_filter not in ("", "submitted", "paid", "failed"):
                    status_filter = ""
                type_filter=((q2.get("type") or [""])[0]).strip().lower()
                if type_filter not in ("", "rent", "bill"):
                    type_filter = ""
                search=((q2.get("q") or [""])[0]).strip().lower()
                sort=((q2.get("sort") or ["newest"])[0]).strip().lower()
                order_sql = {
                    "oldest": "created_at ASC,id ASC",
                    "amount_desc": "amount DESC,id DESC",
                    "amount_asc": "amount ASC,id ASC",
                }.get(sort, "created_at DESC,id DESC")
                page, per, offset = parse_page_params(q2, default_per=20, max_per=100)
                c=db()
                ledger_totals = ensure_tenant_ledger_current(c, u["account_number"])
                sql="SELECT * FROM payments WHERE payer_account=? "
                args=[u["account_number"]]
                if status_filter:
                    sql += "AND status=? "
                    args.append(status_filter)
                if type_filter:
                    sql += "AND payment_type=? "
                    args.append(type_filter)
                if search:
                    s = "%" + search + "%"
                    sql += "AND (LOWER(COALESCE(provider,'')) LIKE ? OR LOWER(COALESCE(payment_type,'')) LIKE ? OR LOWER(COALESCE(status,'')) LIKE ?) "
                    args.extend([s, s, s])
                total = c.execute("SELECT COUNT(1) AS n FROM (" + sql + ") t", tuple(args)).fetchone()["n"]
                rows=c.execute(sql + f"ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(args + [per, offset])).fetchall()
                stats = c.execute(
                    "SELECT "
                    "COALESCE(SUM(amount),0) AS total_amt,"
                    "COALESCE(SUM(CASE WHEN status='paid' THEN amount ELSE 0 END),0) AS paid_amt,"
                    "COALESCE(SUM(CASE WHEN status='submitted' THEN amount ELSE 0 END),0) AS submitted_amt,"
                    "COALESCE(SUM(CASE WHEN status='failed' THEN amount ELSE 0 END),0) AS failed_amt "
                    "FROM payments WHERE payer_account=?",
                    (u["account_number"],),
                ).fetchone()
                c.close()
                tr="".join(
                    f"<tr><td>{esc(p['created_at'])}</td><td>{esc(p['payment_type'])}</td><td>{esc(p['provider']or'')}</td><td>${p['amount']:,}</td><td>{status_badge(p['status'],'payment')}</td><td><a class='ghost-btn' href='/tenant/payment/receipt?id={p['id']}'>View</a></td></tr>"
                    for p in rows
                )
                if not tr:
                    tr = "<tr><td colspan='6'>" + empty_state("$", "No Payments Yet", "You have not submitted payments yet.", "Pay Rent", "/tenant/pay-rent") + "</td></tr>"
                filters_form = (
                    "<div class='card' style='margin-bottom:10px;'>"
                    "<form method='GET' action='/tenant/payments' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:140px;'><label>Status</label>"
                    f"<select name='status'><option value=''>All</option><option value='submitted' {'selected' if status_filter=='submitted' else ''}>submitted</option><option value='paid' {'selected' if status_filter=='paid' else ''}>paid</option><option value='failed' {'selected' if status_filter=='failed' else ''}>failed</option></select></div>"
                    "<div class='field' style='min-width:140px;'><label>Type</label>"
                    f"<select name='type'><option value=''>All</option><option value='rent' {'selected' if type_filter=='rent' else ''}>rent</option><option value='bill' {'selected' if type_filter=='bill' else ''}>bill</option></select></div>"
                    f"<div class='field' style='min-width:200px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='provider/type/status'></div>"
                    "<div class='field' style='min-width:170px;'><label>Sort</label>"
                    f"<select name='sort'><option value='newest' {'selected' if sort not in ('oldest','amount_desc','amount_asc') else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option><option value='amount_desc' {'selected' if sort=='amount_desc' else ''}>Amount high to low</option><option value='amount_asc' {'selected' if sort=='amount_asc' else ''}>Amount low to high</option></select></div>"
                    "<button class='primary-btn' type='submit'>Apply</button>"
                    "<a class='ghost-btn' href='/tenant/payments'>Reset</a>"
                    "</form>"
                    "</div>"
                )
                summary_cards = (
                    "<div class='card' style='margin-bottom:10px;'><div class='grid-3'>"
                    f"<div class='stat'><div class='muted'>Paid Payments</div><div class='stat-num'>${to_int(stats['paid_amt'],0):,}</div></div>"
                    f"<div class='stat'><div class='muted'>Submitted Payments</div><div class='stat-num'>${to_int(stats['submitted_amt'],0):,}</div></div>"
                    f"<div class='stat'><div class='muted'>Ledger Balance</div><div class='stat-num'>${to_int(ledger_totals['balance'],0):,}</div></div>"
                    "</div></div>"
                )
                pager_box = pager_html("/tenant/payments", q2, page, per, total)
                return send_html(self,render("tenant_payments.html",title="Payments",nav_right=nr,nav_menu=nav_menu(u,path),payments_rows=tr,filters_form=filters_form,summary_cards=summary_cards,pager_box=pager_box))
            if path=="/tenant/ledger":
                q2=parse_qs(urlparse(self.path).query)
                month=((q2.get("month") or [""])[0]).strip()
                if month and not re.fullmatch(r"\d{4}-\d{2}", month):
                    month = ""
                sort=((q2.get("sort") or ["newest"])[0]).strip().lower()
                order = "DESC" if sort != "oldest" else "ASC"
                page, per, offset = parse_page_params(q2, default_per=30, max_per=200)
                c=db()
                totals = ensure_tenant_ledger_current(c, u["account_number"])
                sql = "SELECT * FROM tenant_ledger_entries WHERE tenant_account=? "
                args=[u["account_number"]]
                if month:
                    sql += "AND statement_month=? "
                    args.append(month)
                total = c.execute("SELECT COUNT(1) AS n FROM (" + sql + ") t", tuple(args)).fetchone()["n"]
                rows = c.execute(
                    sql + f"ORDER BY COALESCE(due_date,created_at) {order}, id {order} LIMIT ? OFFSET ?",
                    tuple(args + [per, offset]),
                ).fetchall()
                months = c.execute(
                    "SELECT DISTINCT statement_month FROM tenant_ledger_entries "
                    "WHERE tenant_account=? AND COALESCE(statement_month,'')!='' "
                    "ORDER BY statement_month DESC LIMIT 36",
                    (u["account_number"],),
                ).fetchall()
                month_stats = totals
                if month:
                    charge_total = to_int(c.execute(
                        "SELECT COALESCE(SUM(amount),0) AS n FROM tenant_ledger_entries "
                        "WHERE tenant_account=? AND statement_month=? AND entry_type IN('charge','late_fee','adjustment') AND status!='void'",
                        (u["account_number"], month),
                    ).fetchone()["n"], 0)
                    paid_total = to_int(c.execute(
                        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
                        "WHERE tenant_account=? AND statement_month=? AND entry_type='payment' AND status='paid'",
                        (u["account_number"], month),
                    ).fetchone()["n"], 0)
                    sub_total = to_int(c.execute(
                        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
                        "WHERE tenant_account=? AND statement_month=? AND entry_type='payment' AND status='submitted'",
                        (u["account_number"], month),
                    ).fetchone()["n"], 0)
                    fail_total = to_int(c.execute(
                        "SELECT COALESCE(SUM(-amount),0) AS n FROM tenant_ledger_entries "
                        "WHERE tenant_account=? AND statement_month=? AND entry_type='payment' AND status='failed'",
                        (u["account_number"], month),
                    ).fetchone()["n"], 0)
                    month_stats = {"charges": charge_total, "paid": paid_total, "submitted": sub_total, "failed": fail_total, "balance": max(0, charge_total - paid_total)}
                lease_for_split = active_lease_with_rent(c, u["account_number"])
                roommate_box = ""
                if lease_for_split:
                    split_month = month or datetime.now(timezone.utc).strftime("%Y-%m")
                    unit_rent_row = c.execute(
                        "SELECT COALESCE(rent,0) AS rent FROM units WHERE property_id=? AND unit_label=? LIMIT 1",
                        (lease_for_split["property_id"], lease_for_split["unit_label"]),
                    ).fetchone()
                    total_unit_rent = max(0, to_int(unit_rent_row["rent"], 0) if unit_rent_row else 0)
                    primary_row = c.execute(
                        "SELECT l.tenant_account,u.full_name FROM tenant_leases l "
                        "LEFT JOIN users u ON u.account_number=l.tenant_account WHERE l.id=? LIMIT 1",
                        (lease_for_split["id"],),
                    ).fetchone()
                    roommate_rows_db = c.execute(
                        "SELECT rm.tenant_account,rm.share_percent,rm.status,u.full_name "
                        "FROM lease_roommates rm LEFT JOIN users u ON u.account_number=rm.tenant_account "
                        "WHERE rm.lease_id=? ORDER BY rm.id",
                        (lease_for_split["id"],),
                    ).fetchall()
                    total_rm_pct = sum(max(0, to_int(rm["share_percent"], 0)) for rm in roommate_rows_db if (rm["status"] or "").strip().lower() == "active")
                    primary_pct = max(0, 100 - total_rm_pct)
                    participants = []
                    if primary_row:
                        participants.append({
                            "acct": primary_row["tenant_account"],
                            "name": primary_row["full_name"] or primary_row["tenant_account"],
                            "pct": primary_pct,
                            "status": "active",
                        })
                    for rm in roommate_rows_db:
                        participants.append({
                            "acct": rm["tenant_account"],
                            "name": rm["full_name"] or rm["tenant_account"],
                            "pct": max(0, to_int(rm["share_percent"], 0)),
                            "status": (rm["status"] or "active"),
                        })
                    split_rows = ""
                    for part in participants:
                        acct = (part["acct"] or "").strip()
                        pct = max(0, to_int(part["pct"], 0))
                        share_amt = int(round(total_unit_rent * (pct / 100.0)))
                        paid_amt = to_int(c.execute(
                            "SELECT COALESCE(SUM(amount),0) AS n FROM payments "
                            "WHERE payer_role='tenant' AND payer_account=? AND payment_type='rent' "
                            "AND status='paid' AND substr(created_at,1,7)=?",
                            (acct, split_month),
                        ).fetchone()["n"], 0)
                        paid_state = "paid" if share_amt > 0 and paid_amt >= share_amt else ("pending" if share_amt > 0 else "n/a")
                        badge = "badge ok" if paid_state == "paid" else ("badge no" if (part["status"] or "").lower() != "active" else "badge")
                        who = "You" if acct == u["account_number"] else esc(part["name"])
                        split_rows += (
                            "<div style='padding:7px 0;border-bottom:1px solid rgba(255,255,255,.08);'>"
                            f"<b>{who}</b> <span class='muted'>({esc(acct)})</span>"
                            f"<div class='muted'>{pct}% share - ${share_amt:,} for {split_month}</div>"
                            f"<span class='{badge}'>{esc(paid_state)}</span>"
                            "</div>"
                        )
                    roommate_box = (
                        "<div class='card' style='margin-bottom:10px;'>"
                        "<h3 style='margin-top:0;'>Roommate Split</h3>"
                        f"<div class='muted'>Total unit rent: ${total_unit_rent:,}</div>"
                        f"{split_rows or '<div class=\"muted\">No split participants.</div>'}"
                        "</div>"
                    )
                else:
                    roommate_box = "<div class='card' style='margin-bottom:10px;'><h3 style='margin-top:0;'>Roommate Split</h3><div class='muted'>No active lease split found.</div></div>"
                c.close()
                ledger_rows = ""
                for r in rows:
                    typ = (r["entry_type"] or "").strip()
                    amt = to_int(r["amount"], 0)
                    disp = f"-${abs(amt):,}" if amt < 0 else f"${amt:,}"
                    status = (r["status"] or "").strip().lower()
                    badge = "badge"
                    if status in ("paid",):
                        badge = "badge ok"
                    elif status in ("failed", "void"):
                        badge = "badge no"
                    ledger_rows += (
                        "<tr>"
                        f"<td>{esc(r['due_date'] or r['created_at'])}</td>"
                        f"<td>{esc(r['statement_month'] or '-')}</td>"
                        f"<td>{esc(typ)}</td>"
                        f"<td>{esc(r['category'])}</td>"
                        f"<td>{disp}</td>"
                        f"<td><span class='{badge}'>{esc(status or '-')}</span></td>"
                        f"<td>{esc(r['note'] or '')}</td>"
                        "</tr>"
                    )
                if not ledger_rows:
                    ledger_rows = "<tr><td colspan='7' class='muted'>No ledger entries found.</td></tr>"
                month_opts = "".join(
                    f"<option value='{esc(m['statement_month'])}' {'selected' if month==m['statement_month'] else ''}>{esc(m['statement_month'])}</option>"
                    for m in months
                )
                export_month = month or datetime.now(timezone.utc).strftime("%Y-%m")
                filters_form = (
                    "<div class='card' style='margin-bottom:10px;'>"
                    "<form method='GET' action='/tenant/ledger' class='row' style='align-items:flex-end;'>"
                    "<div class='field' style='min-width:180px;'><label>Statement Month</label>"
                    f"<select name='month'><option value=''>All</option>{month_opts}</select></div>"
                    "<div class='field' style='min-width:150px;'><label>Sort</label>"
                    f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                    "<button class='primary-btn' type='submit'>Apply</button>"
                    "<a class='ghost-btn' href='/tenant/ledger'>Reset</a>"
                    f"<a class='ghost-btn' href='/tenant/ledger/statement?month={esc(export_month)}'>Download Statement CSV</a>"
                    "</form>"
                    "</div>"
                )
                summary_cards = (
                    "<div class='card' style='margin-bottom:10px;'><div class='grid-3'>"
                    f"<div class='stat'><div class='muted'>Charges</div><div class='stat-num'>${to_int(month_stats['charges'],0):,}</div></div>"
                    f"<div class='stat'><div class='muted'>Paid</div><div class='stat-num'>${to_int(month_stats['paid'],0):,}</div></div>"
                    f"<div class='stat'><div class='muted'>Balance</div><div class='stat-num'>${to_int(month_stats['balance'],0):,}</div></div>"
                    "</div></div>"
                )
                pager_box = pager_html("/tenant/ledger", q2, page, per, total)
                return send_html(self,render("tenant_ledger.html",title="Tenant Ledger",nav_right=nr,nav_menu=nav_menu(u,path),filters_form=filters_form,summary_cards=summary_cards,roommate_box=roommate_box,ledger_rows=ledger_rows,pager_box=pager_box))
            if path=="/tenant/ledger/statement":
                q2=parse_qs(urlparse(self.path).query)
                month=((q2.get("month") or [""])[0]).strip()
                if not re.fullmatch(r"\d{4}-\d{2}", month):
                    return e400(self, "Month is required in YYYY-MM format.")
                c=db()
                ensure_tenant_ledger_current(c, u["account_number"])
                rows_db = c.execute(
                    "SELECT due_date,created_at,entry_type,category,amount,status,note "
                    "FROM tenant_ledger_entries WHERE tenant_account=? AND statement_month=? "
                    "ORDER BY COALESCE(due_date,created_at) ASC,id ASC",
                    (u["account_number"], month),
                ).fetchall()
                c.close()
                rows = [["date", "entry_type", "category", "amount", "status", "note"]]
                for r in rows_db:
                    rows.append([
                        r["due_date"] or r["created_at"],
                        r["entry_type"],
                        r["category"],
                        to_int(r["amount"], 0),
                        r["status"],
                        r["note"] or "",
                    ])
                return send_csv(self, f"tenant_ledger_statement_{month}.csv", rows)
            if path=="/tenant/payment-methods":
                q2=parse_qs(urlparse(self.path).query)
                c=db()
                methods = tenant_saved_methods(c, u["id"])
                c.close()
                methods_rows = ""
                for m in methods:
                    default_badge = "<span class='badge ok'>default</span>" if to_int(m["is_default"], 0) else "<span class='muted'>-</span>"
                    actions = (
                        "<div class='row'>"
                        "<form method='POST' action='/tenant/payment-methods' style='margin:0;'>"
                        "<input type='hidden' name='action' value='set_default'>"
                        f"<input type='hidden' name='method_id' value='{m['id']}'>"
                        "<button class='ghost-btn' type='submit'>Set Default</button>"
                        "</form>"
                        "<form method='POST' action='/tenant/payment-methods' style='margin:0;'>"
                        "<input type='hidden' name='action' value='delete'>"
                        f"<input type='hidden' name='method_id' value='{m['id']}'>"
                        "<button class='ghost-btn' type='submit'>Remove</button>"
                        "</form>"
                        "</div>"
                    )
                    methods_rows += (
                        "<tr>"
                        f"<td>{esc(m['method_type'])}</td>"
                        f"<td>{esc(format_payment_method_label(m))}</td>"
                        f"<td>{default_badge}</td>"
                        f"<td>{esc(m['created_at'])}</td>"
                        f"<td>{actions}</td>"
                        "</tr>"
                    )
                if not methods_rows:
                    methods_rows = "<tr><td colspan='5' class='muted'>No saved methods yet.</td></tr>"
                empty_box = "" if methods else "<div class='notice' style='margin-top:10px;'>Add your first payment method to enable one-click rent payment and autopay.</div>"
                return send_html(self,render("tenant_payment_methods.html",title="Payment Methods",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),methods_rows=methods_rows,empty_box=empty_box))
            if path=="/tenant/autopay":
                q2=parse_qs(urlparse(self.path).query)
                c=db()
                methods = tenant_saved_methods(c, u["id"])
                row = c.execute("SELECT * FROM tenant_autopay WHERE tenant_user_id=? LIMIT 1", (u["id"],)).fetchone()
                c.close()
                enabled = 1 if (row and to_int(row["is_enabled"], 0)) else 0
                payment_day = str(max(1, min(28, to_int(row["payment_day"], 1) if row else 1)))
                notify_days_before = str(max(0, min(14, to_int(row["notify_days_before"], 3) if row else 3)))
                selected_mid = to_int(row["payment_method_id"], 0) if row else 0
                autopay_method_options = "<option value=''>Select payment method...</option>"
                for m in methods:
                    autopay_method_options += (
                        f"<option value='{m['id']}' {'selected' if to_int(m['id'],0)==selected_mid else ''}>"
                        f"{esc(format_payment_method_label(m))}</option>"
                    )
                autopay_notice = "<div class='notice err'><b>No saved methods.</b> Add one before enabling autopay.</div>" if not methods else "<div class='notice'>Autopay will create a paid rent entry each month on your selected day.</div>"
                return send_html(self,render("tenant_autopay.html",title="Autopay Settings",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),autopay_notice=autopay_notice,autopay_off_selected=("selected" if not enabled else ""),autopay_on_selected=("selected" if enabled else ""),payment_day=payment_day,notify_days_before=notify_days_before,autopay_method_options=autopay_method_options))
            if path=="/tenant/maintenance/new":
                q2=parse_qs(urlparse(self.path).query)
                c = db()
                lease = active_lease_with_rent(c, u["account_number"])
                c.close()
                lease_gate_notice = ""
                form_disabled_attr = ""
                submit_label = "Submit Request"
                if lease:
                    lease_gate_notice = (
                        "<div class='notice'>"
                        f"<b>Linked Property:</b> {esc(lease['property_id'])} / {esc(lease['unit_label'])}"
                        "</div>"
                    )
                else:
                    lease_gate_notice = (
                        "<div class='notice err'>"
                        "<b>No active lease linked.</b> "
                        "You need a linked property before submitting maintenance. "
                        "<a href='/tenant/invites'>Open Property Invites</a>"
                        "</div>"
                    )
                    form_disabled_attr = "disabled"
                    submit_label = "Link Property First"
                return send_html(
                    self,
                    render(
                        "tenant_maintenance_new.html",
                        title="Request Maintenance",
                        nav_right=nr,
                        nav_menu=nav_menu(u,path),
                        message_box=query_message_box(q2),
                        lease_gate_notice=lease_gate_notice,
                        form_disabled_attr=form_disabled_attr,
                        submit_label=submit_label,
                    ),
                )
            m_maint = re.match(r"^/tenant/maintenance/(\d+)$", path)
            if m_maint:
                rid = to_int(m_maint.group(1), 0)
                if rid <= 0:
                    return e404(self)
                c=db()
                row = c.execute(
                    "SELECT * FROM maintenance_requests WHERE id=? AND tenant_account=?",
                    (rid, u["account_number"]),
                ).fetchone()
                photo = c.execute(
                    "SELECT path FROM uploads WHERE kind='maintenance_photo' AND related_table='maintenance_requests' AND related_id=? ORDER BY id DESC LIMIT 1",
                    (rid,),
                ).fetchone()
                thread = c.execute(
                    "SELECT t.id FROM message_threads t JOIN message_participants mp ON mp.thread_id=t.id "
                    "WHERE t.context_type='maintenance' AND t.context_id=? AND mp.user_id=? "
                    "ORDER BY t.id DESC LIMIT 1",
                    (str(rid), u["id"]),
                ).fetchone()
                timeline_rows = c.execute(
                    "SELECT created_at,actor_role,action,details FROM audit_logs "
                    "WHERE entity_type='maintenance_requests' AND entity_id=? ORDER BY id ASC LIMIT 60",
                    (str(rid),),
                ).fetchall()
                c.close()
                if not row:
                    return e404(self)
                urgency = (row["urgency"] or "normal").strip().lower() if "urgency" in row.keys() else "normal"
                status = (row["status"] or "open").strip().lower()
                urgency_html = status_badge(urgency, "priority")
                status_html = status_badge(status, "maintenance")
                photo_html = f"<div style='margin-top:10px;'><a class='ghost-btn' href='{esc(photo['path'])}' target='_blank' rel='noopener'>Open Uploaded Photo</a></div>" if photo else "<div class='muted' style='margin-top:10px;'>No photo uploaded.</div>"
                timeline_html = ""
                for ev in timeline_rows:
                    label = (ev["action"] or "").replace("_", " ").strip() or "update"
                    details = (ev["details"] or "").strip()
                    timeline_html += (
                        "<div style='padding:6px 0;border-bottom:1px solid rgba(255,255,255,.08);'>"
                        f"<div><b>{esc(label)}</b> <span class='muted'>({esc(ev['actor_role'] or 'system')})</span></div>"
                        f"<div class='muted'>{esc(ev['created_at'])}</div>"
                        + (f"<div class='muted'>{esc(details[:180])}</div>" if details else "")
                        + "</div>"
                    )
                if not timeline_html:
                    timeline_html = "<div class='muted'>No timeline events yet.</div>"
                thread_box = (
                    f"<a class='ghost-btn' href='/messages?thread={to_int(thread['id'],0)}'>Open Message Thread</a>"
                    if thread else
                    "<form method='POST' action='/tenant/maintenance/thread' style='margin:0;'><input type='hidden' name='request_id' value='"
                    + str(rid)
                    + "'><button class='ghost-btn' type='submit'>Start Message Thread</button></form>"
                )
                detail_box = (
                    f"<div><b>Status:</b> {status_html}</div>"
                    f"<div><b>Priority:</b> {urgency_html}</div>"
                    f"<div><b>Assigned To:</b> {esc(row['assigned_to'] or 'Unassigned')}</div>"
                    f"<div><b>Submitted:</b> {esc(row['created_at'])}</div>"
                    f"<div><b>Last Update:</b> {esc(row['updated_at'] or row['created_at'])}</div>"
                    f"<div style='margin-top:10px;'><b>Messages</b><div class='row' style='margin-top:6px;'>{thread_box}</div></div>"
                    f"<div style='margin-top:10px;'><b>Description</b><div class='muted'>{esc(row['description'])}</div></div>"
                    "<div style='margin-top:10px;'><b>Timeline</b>"
                    f"{timeline_html}"
                    "</div>"
                    f"{photo_html}"
                )
                return send_html(self,render("tenant_maintenance_detail.html",title=f"Maintenance #{rid}",nav_right=nr,nav_menu=nav_menu(u,path),request_id=f'#{rid}',message_box="",detail_box=detail_box))
            if path=="/tenant/maintenance":
                c=db()
                rows=c.execute("SELECT * FROM maintenance_requests WHERE tenant_account=? ORDER BY created_at DESC LIMIT 200",(u["account_number"],)).fetchall()
                photos = c.execute(
                    "SELECT related_id,path FROM uploads WHERE kind='maintenance_photo' AND related_table='maintenance_requests' ORDER BY id DESC"
                ).fetchall()
                c.close()
                photo_map = {}
                for p in photos:
                    rid = to_int(p["related_id"], 0)
                    if rid <= 0 or rid in photo_map:
                        continue
                    photo_map[rid] = p["path"]
                tr=""
                for r in rows:
                    photo = photo_map.get(to_int(r["id"], 0))
                    photo_html = f"<div style='margin-top:6px;'><a class='ghost-btn' href='{esc(photo)}' target='_blank' rel='noopener'>View Photo</a></div>" if photo else ""
                    status = (r["status"] or "open").strip().lower()
                    urgency = (r["urgency"] or "normal").strip().lower() if "urgency" in r.keys() else "normal"
                    tr += (
                        "<tr>"
                        f"<td>#{r['id']}</td>"
                        f"<td>{esc(r['created_at'])}</td>"
                        f"<td>{status_badge(urgency,'priority')}</td>"
                        f"<td>{status_badge(status,'maintenance')}</td>"
                        f"<td>{esc(r['assigned_to']or'')}</td>"
                        f"<td>{esc(r['description'])}{photo_html}</td>"
                        f"<td><a class='ghost-btn' href='/tenant/maintenance/{r['id']}'>Open</a></td>"
                        "</tr>"
                    )
                if not tr:
                    tr = "<tr><td colspan='7'>" + empty_state("!", "No Maintenance Requests", "You have not submitted maintenance requests yet.", "Submit Request", "/tenant/maintenance/new") + "</td></tr>"
                return send_html(self,render("tenant_maintenance_list.html",title="My Maintenance",nav_right=nr,nav_menu=nav_menu(u,path),maintenance_rows=tr))
            if path=="/tenant/lease":
                c=db()
                ls = active_lease_with_rent(c, u["account_number"])
                info = '<div class="notice err"><b>No active lease.</b></div>'
                lease_doc_box = ""
                esign_box = ""
                contact_box=""
                if ls:
                    split_text = f" ({to_int(ls.get('share_percent'), 100)}% share)" if to_int(ls.get("share_percent"), 100) < 100 else ""
                    base_lease = c.execute("SELECT * FROM tenant_leases WHERE id=?", (ls["id"],)).fetchone()
                    info = (
                        f'<div class="notice"><b>Active:</b> {esc(ls["property_id"])} - {esc(ls["unit_label"])}{split_text} - Start {esc(ls["start_date"])}'
                        f"<div class='muted'>Monthly rent share: ${to_int(ls.get('rent'),0):,}</div>"
                        "</div>"
                    )
                    lease_doc = lease_doc_for_lease(c, ls["id"])
                    if lease_doc:
                        lease_doc_box = (
                            "<div class='notice' style='margin-top:10px;'><b>Lease Document</b>"
                            f"<div class='muted' style='margin-top:6px;'><a class='ghost-btn' href='{esc(lease_doc['path'])}' target='_blank' rel='noopener'>Download Lease PDF</a></div>"
                            "</div>"
                        )
                    if base_lease:
                        mgr_signed = (base_lease["manager_signed_at"] or "").strip()
                        ten_signed = (base_lease["tenant_signed_at"] or "").strip()
                        if ls["tenant_account"] != u["account_number"]:
                            esign_box = (
                                "<div class='notice' style='margin-top:10px;'>"
                                "<b>E-Signature</b><div class='muted'>Primary tenant signs this lease. You are a roommate on this lease.</div>"
                                "</div>"
                            )
                        else:
                            if ten_signed:
                                esign_box = (
                                    "<div class='notice' style='margin-top:10px;'>"
                                    f"<b>E-Signature Complete</b><div class='muted'>Manager signed: {esc(mgr_signed or 'pending')} | Tenant signed: {esc(ten_signed)}</div>"
                                    "</div>"
                                )
                            else:
                                mgr_note = f"Manager signed: {esc(mgr_signed)}" if mgr_signed else "Manager signature pending."
                                esign_box = (
                                    "<div class='notice' style='margin-top:10px;'>"
                                    f"<b>E-Signature</b><div class='muted'>{mgr_note}</div>"
                                    "<form method='POST' action='/tenant/lease/sign' style='margin-top:8px;'>"
                                    "<button class='primary-btn' type='submit'>Sign Lease</button>"
                                    "</form>"
                                    "</div>"
                                )
                    owner=c.execute("SELECT u.full_name,u.email,u.phone FROM properties p JOIN users u ON u.account_number=p.owner_account WHERE p.id=? LIMIT 1",(ls["property_id"],)).fetchone()
                    mgr=c.execute("SELECT full_name,email,phone FROM users WHERE role='property_manager' ORDER BY id LIMIT 1").fetchone()
                    owner_html=f"{esc(owner['full_name'])} ({esc(owner['email'])}, {esc(owner['phone'])})" if owner else "-"
                    mgr_html=f"{esc(mgr['full_name'])} ({esc(mgr['email'])}, {esc(mgr['phone'])})" if mgr else "-"
                    contact_box=f"<div class='notice' style='margin-top:10px;'><b>Contacts</b><div class='muted'>Owner: {owner_html}</div><div class='muted'>Manager: {mgr_html}</div></div>"
                c.close()
                return send_html(self,render("tenant_lease.html",title="My Lease",nav_right=nr,nav_menu=nav_menu(u,path),lease_info=info,lease_doc_box=lease_doc_box,esign_box=esign_box,contact_box=contact_box))
            if path=="/tenant/invites":
                return self._tenant_invites_get(u)
            return e404(self)

        def _tenant_post(self,path,u,f):
            u=self._req_role(u,"tenant",action="tenant.portal")
            if not u:return
            if path=="/tenant/pay-rent":
                if not self._req_action(u, "tenant.payment.submit"): return
                amt=int(f.get("amount")or"0")if(f.get("amount")or"").isdigit()else 0
                method_id = to_int(f.get("payment_method_id"), 0)
                if amt<=0:
                    return handle_user_error(self, "Enter a valid rent amount.", "/tenant/pay-rent")
                c=db()
                ls=active_lease_with_rent(c, u["account_number"])
                if not ls:
                    c.close()
                    return handle_user_error(self, "No active lease found. Accept a property invite first.", "/tenant/pay-rent")
                expected = max(0, to_int(ls.get("rent"), 0))
                if expected > 0 and amt > (expected * 3):
                    c.close()
                    return handle_user_error(self, f"Amount looks too high for your lease share (${expected:,}).", "/tenant/pay-rent")
                provider = "Rent"
                if method_id > 0:
                    pm = tenant_method_by_id(c, u["id"], method_id)
                    if not pm:
                        c.close()
                        return handle_user_error(self, "Saved payment method was not found.", "/tenant/pay-rent")
                    provider = "Saved Method - " + format_payment_method_label(pm)
                c.execute("INSERT INTO payments(payer_account,payer_role,payment_type,provider,amount,status)VALUES(?,?,?,?,?,?)",(u["account_number"],"tenant","rent",provider,amt,"submitted"))
                pay_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                sync_ledger_from_payments(c, payment_id=pay_id)
                reconcile_tenant_ledger(c, u["account_number"])
                audit_log(c,u,"tenant_rent_submitted","payments",pay_id,f"amount={amt};lease={ls['property_id']}/{ls['unit_label']};share={to_int(ls.get('share_percent'),100)};provider={provider}")
                c.commit();c.close()
                return redir(self, with_msg(f"/tenant/payment/confirmation?id={pay_id}", "Payment submitted successfully."))
            if path=="/tenant/lease/sign":
                if not self._req_action(u, "tenant.portal"): return
                c=db()
                ls=active_lease_with_rent(c, u["account_number"])
                if not ls:
                    c.close()
                    return redir(self, with_msg("/tenant/lease", "No active lease found.", True))
                if ls["tenant_account"] != u["account_number"]:
                    c.close()
                    return redir(self, with_msg("/tenant/lease", "Only the primary tenant can e-sign this lease.", True))
                row = c.execute("SELECT tenant_signed_at,manager_signed_at FROM tenant_leases WHERE id=?", (ls["id"],)).fetchone()
                if not row:
                    c.close()
                    return redir(self, with_msg("/tenant/lease", "Lease was not found.", True))
                if (row["tenant_signed_at"] or "").strip():
                    c.close()
                    return redir(self, with_msg("/tenant/lease", "Lease is already signed."))
                ip = client_ip(self.headers)
                c.execute(
                    "UPDATE tenant_leases SET tenant_signed_at=datetime('now'), esign_ip=? WHERE id=?",
                    (ip, ls["id"]),
                )
                owner = c.execute("SELECT u.id FROM properties p JOIN users u ON u.account_number=p.owner_account WHERE p.id=? LIMIT 1", (ls["property_id"],)).fetchone()
                if owner:
                    create_notification(c, owner["id"], f"Tenant signed lease: {ls['property_id']} / {ls['unit_label']}", "/manager/leases")
                audit_log(c, u, "tenant_lease_signed", "tenant_leases", ls["id"], f"ip={ip};property={ls['property_id']};unit={ls['unit_label']}")
                c.commit();c.close()
                return redir(self, with_msg("/tenant/lease", "Lease signed successfully."))
            if path=="/tenant/pay-bills":
                if not self._req_action(u, "tenant.payment.submit"): return
                prov=f.get("provider")or"";amt=int(f.get("amount")or"0")if(f.get("amount")or"").isdigit()else 0
                if prov in("Cable Bahamas","Aliv","BTC","BPL")and amt>0:
                    c=db()
                    c.execute("INSERT INTO payments(payer_account,payer_role,payment_type,provider,amount,status)VALUES(?,?,?,?,?,?)",(u["account_number"],"tenant","bill",prov,amt,"submitted"))
                    pay_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                    sync_ledger_from_payments(c, payment_id=pay_id)
                    audit_log(c,u,"tenant_bill_submitted","payments",pay_id,f"provider={prov};amount={amt}")
                    c.commit();c.close()
                    return redir(self, with_msg(f"/tenant/payment/confirmation?id={pay_id}", "Bill payment submitted successfully."))
                return handle_user_error(self, "Select a valid provider and amount.", "/tenant/pay-bills")
            if path=="/tenant/payment-methods":
                if not self._req_action(u, "tenant.payment.submit"): return
                action = (f.get("action") or "").strip().lower()
                c = db()
                if action == "add":
                    method_type = (f.get("method_type") or "card").strip().lower()
                    if method_type not in ("card", "bank"):
                        method_type = "card"
                    label = (f.get("brand_label") or "").strip()[:80]
                    last4 = re.sub(r"\D", "", str(f.get("last4") or ""))[-4:]
                    is_default = 1 if str(f.get("is_default") or "0").strip().lower() in ("1", "true", "yes", "on") else 0
                    if len(label) < 2 or len(last4) != 4:
                        c.close()
                        return redir(self, with_msg("/tenant/payment-methods", "Label and 4-digit ending are required.", True))
                    c.execute(
                        "INSERT INTO payment_methods(tenant_user_id,method_type,brand_label,last4,is_default,is_active,updated_at)VALUES(?,?,?,?,?,1,datetime('now'))",
                        (u["id"], method_type, label, last4, 0),
                    )
                    mid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                    if is_default:
                        set_default_payment_method(c, u["id"], mid)
                    else:
                        has_default = c.execute(
                            "SELECT 1 FROM payment_methods WHERE tenant_user_id=? AND is_active=1 AND is_default=1",
                            (u["id"],),
                        ).fetchone()
                        if not has_default:
                            set_default_payment_method(c, u["id"], mid)
                    audit_log(c, u, "tenant_payment_method_added", "payment_methods", mid, f"type={method_type};label={label}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg("/tenant/payment-methods", "Payment method saved."))
                if action == "set_default":
                    mid = to_int(f.get("method_id"), 0)
                    if mid <= 0:
                        c.close()
                        return redir(self, with_msg("/tenant/payment-methods", "Payment method was not found.", True))
                    row = tenant_method_by_id(c, u["id"], mid)
                    if not row:
                        c.close()
                        return redir(self, with_msg("/tenant/payment-methods", "Payment method was not found.", True))
                    set_default_payment_method(c, u["id"], mid)
                    c.execute(
                        "UPDATE tenant_autopay SET payment_method_id=?,updated_at=datetime('now') WHERE tenant_user_id=? AND payment_method_id IS NULL",
                        (mid, u["id"]),
                    )
                    audit_log(c, u, "tenant_payment_method_default_set", "payment_methods", mid, "")
                    c.commit()
                    c.close()
                    return redir(self, with_msg("/tenant/payment-methods", "Default payment method updated."))
                if action == "delete":
                    mid = to_int(f.get("method_id"), 0)
                    if mid <= 0:
                        c.close()
                        return redir(self, with_msg("/tenant/payment-methods", "Payment method was not found.", True))
                    row = tenant_method_by_id(c, u["id"], mid)
                    if not row:
                        c.close()
                        return redir(self, with_msg("/tenant/payment-methods", "Payment method was not found.", True))
                    c.execute("UPDATE payment_methods SET is_active=0,is_default=0,updated_at=datetime('now') WHERE id=? AND tenant_user_id=?", (mid, u["id"]))
                    c.execute("UPDATE tenant_autopay SET payment_method_id=NULL,updated_at=datetime('now') WHERE tenant_user_id=? AND payment_method_id=?", (u["id"], mid))
                    next_default = c.execute(
                        "SELECT id FROM payment_methods WHERE tenant_user_id=? AND is_active=1 ORDER BY id DESC LIMIT 1",
                        (u["id"],),
                    ).fetchone()
                    if next_default:
                        set_default_payment_method(c, u["id"], next_default["id"])
                    audit_log(c, u, "tenant_payment_method_removed", "payment_methods", mid, "")
                    c.commit()
                    c.close()
                    return redir(self, with_msg("/tenant/payment-methods", "Payment method removed."))
                c.close()
                return redir(self, with_msg("/tenant/payment-methods", "Unsupported action.", True))
            if path=="/tenant/autopay":
                if not self._req_action(u, "tenant.payment.submit"): return
                enabled = 1 if str(f.get("is_enabled") or "0").strip() in ("1", "true", "yes", "on") else 0
                payment_day = max(1, min(28, to_int(f.get("payment_day"), 1)))
                notify_days_before = max(0, min(14, to_int(f.get("notify_days_before"), 3)))
                method_id = to_int(f.get("payment_method_id"), 0)
                c = db()
                if enabled:
                    if method_id <= 0:
                        c.close()
                        return redir(self, with_msg("/tenant/autopay", "Select a payment method before enabling autopay.", True))
                    pm = tenant_method_by_id(c, u["id"], method_id)
                    if not pm:
                        c.close()
                        return redir(self, with_msg("/tenant/autopay", "Payment method was not found.", True))
                else:
                    pm = tenant_method_by_id(c, u["id"], method_id) if method_id > 0 else None
                    if method_id > 0 and not pm:
                        method_id = 0
                c.execute(
                    "INSERT INTO tenant_autopay(tenant_user_id,payment_method_id,is_enabled,payment_day,notify_days_before,updated_at)VALUES(?,?,?,?,?,datetime('now')) "
                    "ON CONFLICT(tenant_user_id) DO UPDATE SET payment_method_id=excluded.payment_method_id,is_enabled=excluded.is_enabled,payment_day=excluded.payment_day,notify_days_before=excluded.notify_days_before,updated_at=datetime('now')",
                    (u["id"], method_id if method_id > 0 else None, enabled, payment_day, notify_days_before),
                )
                audit_log(c, u, "tenant_autopay_updated", "tenant_autopay", u["id"], f"enabled={enabled};day={payment_day};reminder_days={notify_days_before};method={method_id}")
                c.commit()
                c.close()
                return redir(self, with_msg("/tenant/autopay", "Autopay settings saved."))
            if path=="/tenant/maintenance/new":
                if not self._req_action(u, "tenant.maintenance.submit"): return
                issue=(f.get("issue_type") or "").strip()
                urgency=(f.get("urgency") or "normal").strip().lower()
                if urgency not in ("normal", "high", "emergency"):
                    urgency = "normal"
                desc=(f.get("description")or"").strip()
                if issue:
                    desc=f"[{issue}] {desc}"
                if len(desc) < 5:
                    return handle_user_error(self, "Please provide more detail for your maintenance request.", "/tenant/maintenance/new")
                c=db()
                lease = active_lease_with_rent(c, u["account_number"])
                if not lease:
                    c.close()
                    return handle_user_error(self, "No active lease found. Accept a property invite before requesting maintenance.", "/tenant/maintenance/new")
                c.execute(
                    "INSERT INTO maintenance_requests(tenant_account,tenant_name,description,status,urgency)VALUES(?,?,?,?,?)",
                    (u["account_number"],u["full_name"],desc,"open",urgency),
                )
                mid=to_int(c.execute("SELECT last_insert_rowid()").fetchone()[0], 0)
                up=getattr(self,"_files",{}).get("photo")
                if up and up.get("content"):
                    save_image_upload(c, u["id"], "maintenance_requests", mid, "maintenance_photo", up)
                req_row = c.execute("SELECT * FROM maintenance_requests WHERE id=?", (mid,)).fetchone()
                owner_user = maintenance_manager_user(c, req_row)
                thread_id = 0
                if owner_user and to_int(owner_user.get("id"), 0) != to_int(u.get("id"), 0):
                    create_notification(
                        c,
                        owner_user["id"],
                        f"New {urgency} maintenance request from {u['full_name']} for {lease['property_id']} / {lease['unit_label']}",
                        "/manager/maintenance",
                    )
                    ok, _note, thread_id = create_message_thread(
                        c,
                        u,
                        owner_user.get("account_number") or "",
                        f"Maintenance Request #{mid} ({urgency.title()})",
                        (
                            f"Property: {lease['property_id']} / {lease['unit_label']}\n"
                            f"Tenant: {u['full_name']} ({u['account_number']})\n"
                            f"Urgency: {urgency}\n"
                            f"Issue: {desc}"
                        ),
                        context_type="maintenance",
                        context_id=str(mid),
                        attachment=None,
                    )
                    if not ok:
                        thread_id = 0
                if thread_id > 0:
                    create_notification(c, u["id"], "Maintenance request sent to property owner. Replies will appear in Messages.", f"/messages?thread={thread_id}")
                audit_log(c,u,"tenant_maintenance_created","maintenance_requests",mid,f"urgency={urgency};{desc[:160]}")
                c.commit();c.close()
                return redir(self, with_msg(f"/tenant/maintenance/confirmation?id={mid}", "Maintenance request submitted."))
            if path=="/tenant/maintenance/thread":
                rid = to_int(f.get("request_id"), 0)
                if rid <= 0:
                    return handle_user_error(self, "Maintenance request was not found.", "/tenant/maintenance")
                c = db()
                req = c.execute("SELECT id FROM maintenance_requests WHERE id=? AND tenant_account=?", (rid, u["account_number"])).fetchone()
                if not req:
                    c.close()
                    return handle_user_error(self, "Maintenance request was not found.", "/tenant/maintenance")
                tid = ensure_maintenance_message_thread(c, u, rid)
                c.commit()
                c.close()
                if tid > 0:
                    return redir(self, with_msg(f"/messages?thread={tid}", "Maintenance thread ready."))
                return handle_user_error(self, "Could not start maintenance thread.", f"/tenant/maintenance/{rid}")
            if path=="/tenant/invite/respond":
                if not self._req_action(u, "tenant.invite.respond"): return
                return self._tenant_invite_respond(f,u)
            return e404(self)

        def _tenant_invites_get(self, u):
            q = parse_qs(urlparse(self.path).query)
            msg = (q.get("msg") or [""])[0].strip()
            err = (q.get("err") or ["0"])[0] == "1"
            search = (q.get("q") or [""])[0].strip()
            status_filter = (q.get("status") or [""])[0].strip().lower()
            if status_filter not in ("", "accepted", "declined", "cancelled"):
                status_filter = ""
            page, per, offset = parse_page_params(q, default_per=20, max_per=100)
            sort = (q.get("sort") or ["newest"])[0].strip().lower()
            order = "DESC" if sort != "oldest" else "ASC"
            message_box = ""
            if msg:
                klass = "notice err" if err else "notice"
                message_box = f'<div class="{klass}" style="margin-bottom:10px;">{esc(msg)}</div>'

            c = db()
            cleanup_expired_invites(c)
            pending = c.execute(
                "SELECT i.*, su.full_name AS sender_name, p.name AS property_name "
                "FROM tenant_property_invites i "
                "LEFT JOIN users su ON su.id=i.sender_user_id "
                "LEFT JOIN properties p ON p.id=i.property_id "
                "WHERE i.tenant_account=? AND i.status='pending' "
                f"ORDER BY i.created_at {order}, i.id {order} LIMIT 100",
                (u["account_number"],),
            ).fetchall()
            hist_sql = (
                "SELECT i.*, su.full_name AS sender_name, p.name AS property_name "
                "FROM tenant_property_invites i "
                "LEFT JOIN users su ON su.id=i.sender_user_id "
                "LEFT JOIN properties p ON p.id=i.property_id "
                "WHERE i.tenant_account=? AND i.status!='pending' "
            )
            hist_args = [u["account_number"]]
            if status_filter:
                hist_sql += "AND i.status=? "
                hist_args.append(status_filter)
            if search:
                hist_sql += "AND (LOWER(COALESCE(i.property_id,'')) LIKE ? OR LOWER(COALESCE(i.unit_label,'')) LIKE ? OR LOWER(COALESCE(p.name,'')) LIKE ?) "
                s = "%" + search.lower() + "%"
                hist_args.extend([s, s, s])
            hist_count = c.execute("SELECT COUNT(1) AS n FROM (" + hist_sql + ") t", tuple(hist_args)).fetchone()["n"]
            history = c.execute(
                hist_sql + f"ORDER BY i.created_at {order}, i.id {order} LIMIT ? OFFSET ?",
                tuple(hist_args + [per, offset]),
            ).fetchall()
            active = c.execute(
                "SELECT l.*, p.name AS property_name "
                "FROM tenant_leases l "
                "LEFT JOIN properties p ON p.id=l.property_id "
                "WHERE l.tenant_account=? AND l.is_active=1 "
                "ORDER BY l.id DESC LIMIT 1",
                (u["account_number"],),
            ).fetchone()
            c.close()

            pending_cards = ""
            for r in pending:
                note = f"<div class='muted' style='margin-top:6px;'>Message: {esc(r['message'])}</div>" if (r["message"] or "").strip() else ""
                pending_cards += (
                    "<div class='card' style='margin-bottom:10px;'>"
                    f"<div><b>{esc(r['property_name'] or r['property_id'])}</b> - {esc(r['unit_label'])}</div>"
                    f"<div class='muted'>From: {esc(r['sender_name'] or 'AtlasBahamas')} - Sent: {esc(r['created_at'])}</div>"
                    f"{note}"
                    "<div class='row' style='margin-top:10px;'>"
                    "<form method='POST' action='/tenant/invite/respond' style='margin:0;'>"
                    f"<input type='hidden' name='invite_id' value='{r['id']}'>"
                    "<input type='hidden' name='action' value='accept'>"
                    "<button class='primary-btn' type='submit'>Accept</button>"
                    "</form>"
                    "<form method='POST' action='/tenant/invite/respond' style='margin:0;'>"
                    f"<input type='hidden' name='invite_id' value='{r['id']}'>"
                    "<input type='hidden' name='action' value='decline'>"
                    "<button class='ghost-btn' type='submit'>Decline</button>"
                    "</form>"
                    "</div>"
                    "</div>"
                )
            if not pending_cards:
                pending_cards = '<div class="notice">No pending property invites.</div>'

            if active:
                active_box = (
                    "<div class='notice'>"
                    f"<b>{esc(active['property_name'] or active['property_id'])}</b> - {esc(active['unit_label'])}"
                    f"<div class='muted' style='margin-top:4px;'>Linked since {esc(active['start_date'])}</div>"
                    "</div>"
                )
            else:
                active_box = '<div class="notice err"><b>No linked property yet.</b> Accept an invite to sync your account.</div>'

            history_rows = ""
            for r in history:
                st = (r["status"] or "").strip().lower()
                klass = "badge"
                if st == "accepted":
                    klass = "badge ok"
                elif st in ("declined", "cancelled"):
                    klass = "badge no"
                history_rows += (
                    "<tr>"
                    f"<td>#{r['id']}</td>"
                    f"<td>{esc(r['property_name'] or r['property_id'])}</td>"
                    f"<td>{esc(r['unit_label'])}</td>"
                    f"<td>{esc(r['sender_name'] or '-')}</td>"
                    f"<td><span class='{klass}'>{esc(st)}</span></td>"
                    f"<td>{esc(r['created_at'])}</td>"
                    f"<td>{esc(r['responded_at'] or '-')}</td>"
                    "</tr>"
                )
            history_empty = "" if history else '<div class="notice" style="margin-top:10px;">No invite history yet.</div>'
            history_empty += pager_html("/tenant/invites", q, page, per, hist_count)

            return send_html(
                self,
                render(
                    "tenant_invites.html",
                    title="Property Invites",
                    nav_right=nav(u, "/tenant/invites"),
                    nav_menu=nav_menu(u, "/tenant/invites"),
                    message_box=message_box,
                    pending_cards=pending_cards,
                    active_box=active_box,
                    history_rows=history_rows,
                    history_empty=history_empty,
                ),
            )

        def _tenant_invite_respond(self, f, u):
            iid = to_int(f.get("invite_id"), 0)
            action = (f.get("action") or "").strip().lower()
            if iid <= 0 or action not in ("accept", "decline"):
                return redir(self, with_msg("/tenant/invites", "Invalid invite action.", True))

            c = db()
            cleanup_expired_invites(c)
            inv = c.execute(
                "SELECT * FROM tenant_property_invites WHERE id=? AND tenant_account=? AND status='pending'",
                (iid, u["account_number"]),
            ).fetchone()
            if not inv:
                c.close()
                return redir(self, with_msg("/tenant/invites", "Invite is no longer available.", True))
            exp = (inv["expires_at"] or "").strip() if "expires_at" in inv.keys() else ""
            if exp and exp <= datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"):
                c.execute(
                    "UPDATE tenant_property_invites SET status='cancelled', responded_at=datetime('now'), revoke_reason='expired' WHERE id=?",
                    (iid,),
                )
                c.commit()
                c.close()
                return redir(self, with_msg("/tenant/invites", "Invite expired. Ask for a new invite.", True))

            sender_id = inv["sender_user_id"]
            pid = inv["property_id"]
            ul = inv["unit_label"]

            if action == "decline":
                c.execute(
                    "UPDATE tenant_property_invites SET status='declined', responded_at=datetime('now'), revoke_reason='declined_by_tenant' WHERE id=?",
                    (iid,),
                )
                if sender_id:
                    create_notification(c, sender_id, f"Tenant declined invite: {pid} / {ul}", "/notifications")
                audit_log(c, u, "tenant_invite_declined", "tenant_property_invites", iid, f"{pid}/{ul}")
                c.commit()
                c.close()
                return redir(self, with_msg("/tenant/invites", "Invite declined."))

            unit = c.execute(
                "SELECT is_occupied FROM units WHERE property_id=? AND unit_label=?",
                (pid, ul),
            ).fetchone()
            busy = c.execute(
                "SELECT tenant_account FROM tenant_leases WHERE property_id=? AND unit_label=? AND is_active=1 ORDER BY id DESC LIMIT 1",
                (pid, ul),
            ).fetchone()
            same_tenant_busy = bool(busy and busy["tenant_account"] == u["account_number"])
            unit_marked_occupied = bool(unit and to_int(unit["is_occupied"], 0))
            if (not unit) or (busy and not same_tenant_busy) or (unit_marked_occupied and not same_tenant_busy):
                c.execute(
                    "UPDATE tenant_property_invites SET status='cancelled', responded_at=datetime('now'), revoke_reason='unavailable' WHERE id=?",
                    (iid,),
                )
                if sender_id:
                    create_notification(c, sender_id, f"Invite expired/unavailable: {pid} / {ul}", "/notifications")
                audit_log(c, u, "tenant_invite_unavailable", "tenant_property_invites", iid, f"{pid}/{ul}")
                c.commit()
                c.close()
                return redir(self, with_msg("/tenant/invites", "Invite could not be accepted because the unit is unavailable.", True))

            current = c.execute(
                "SELECT property_id,unit_label FROM tenant_leases WHERE tenant_account=? AND is_active=1 ORDER BY id DESC LIMIT 1",
                (u["account_number"],),
            ).fetchone()
            already_linked = bool(current and current["property_id"] == pid and current["unit_label"] == ul)
            if not already_linked:
                prev = c.execute(
                    "SELECT property_id,unit_label FROM tenant_leases WHERE tenant_account=? AND is_active=1",
                    (u["account_number"],),
                ).fetchall()
                for p in prev:
                    c.execute(
                        "UPDATE units SET is_occupied=0 WHERE property_id=? AND unit_label=?",
                        (p["property_id"], p["unit_label"]),
                    )
                c.execute(
                    "UPDATE tenant_leases SET is_active=0,end_date=date('now') WHERE tenant_account=? AND is_active=1",
                    (u["account_number"],),
                )
                c.execute(
                    "INSERT INTO tenant_leases(tenant_account,property_id,unit_label,start_date,is_active,manager_signed_at)VALUES(?,?,?,?,1,datetime('now'))",
                    (u["account_number"], pid, ul, datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                )
                c.execute("UPDATE units SET is_occupied=1 WHERE property_id=? AND unit_label=?", (pid, ul))
            c.execute(
                "UPDATE tenant_property_invites SET status='accepted', responded_at=datetime('now'), revoke_reason=NULL WHERE id=?",
                (iid,),
            )
            c.execute(
                "UPDATE tenant_property_invites SET status='cancelled', responded_at=datetime('now') "
                "WHERE tenant_account=? AND status='pending' AND id<>?",
                (u["account_number"], iid),
            )
            c.execute(
                "UPDATE tenant_property_invites SET status='cancelled', responded_at=datetime('now') "
                "WHERE property_id=? AND unit_label=? AND status='pending' AND id<>?",
                (pid, ul, iid),
            )
            if sender_id:
                create_notification(c, sender_id, f"Tenant accepted invite: {pid} / {ul}", "/notifications")
            audit_log(c, u, "tenant_invite_accepted", "tenant_property_invites", iid, f"{pid}/{ul}")
            create_notification(c, u["id"], f"Property linked: {pid} / {ul}", "/tenant/lease")
            c.commit()
            c.close()
            if already_linked:
                return redir(self, with_msg("/tenant/invites", "Invite accepted. This property was already linked to your account."))
            return redir(self, with_msg("/tenant/invites", "Invite accepted. Property synced to your account."))



