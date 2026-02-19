"""AdminHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class AdminHandlerMixin:
        def _admin_get(self, u):
            u = self._req_role(u, "admin", action="admin.portal")
            if not u:
                return
            def _fmt_mb(nbytes):
                return f"{(max(0, to_int(nbytes, 0)) / (1024 * 1024)):.1f} MB"
            c = db()
            stats = {
                "users": c.execute("SELECT COUNT(1) AS n FROM users").fetchone()["n"],
                "listings": c.execute("SELECT COUNT(1) AS n FROM listings").fetchone()["n"],
                "properties": c.execute("SELECT COUNT(1) AS n FROM properties").fetchone()["n"],
                "open_maintenance": c.execute("SELECT COUNT(1) AS n FROM maintenance_requests WHERE status!='closed'").fetchone()["n"],
                "new_inquiries": c.execute("SELECT COUNT(1) AS n FROM inquiries WHERE status IN('new','open')").fetchone()["n"],
                "pending_apps": c.execute("SELECT COUNT(1) AS n FROM applications WHERE status IN('submitted','under_review')").fetchone()["n"],
            }
            active_sessions = c.execute("SELECT COUNT(1) AS n FROM sessions WHERE expires_at>datetime('now')").fetchone()["n"]
            logins_24h = c.execute("SELECT COUNT(1) AS n FROM sessions WHERE created_at>=datetime('now','-1 day')").fetchone()["n"]
            pending_submissions = c.execute("SELECT COUNT(1) AS n FROM listing_requests WHERE status='pending'").fetchone()["n"]
            overdue_maint = c.execute(
                "SELECT COUNT(1) AS n FROM maintenance_requests "
                "WHERE status IN('open','in_progress') AND julianday('now') - julianday(created_at) >= 7"
            ).fetchone()["n"]
            pending_leases = c.execute("SELECT COUNT(1) AS n FROM tenant_property_invites WHERE status='pending'").fetchone()["n"]
            unhandled_inquiries = c.execute("SELECT COUNT(1) AS n FROM inquiries WHERE status IN('new','open')").fetchone()["n"]
            unhandled_apps = c.execute("SELECT COUNT(1) AS n FROM applications WHERE status IN('submitted','under_review')").fetchone()["n"]
            stuck_submissions = c.execute(
                "SELECT COUNT(1) AS n FROM listing_requests WHERE status='pending' AND julianday('now') - julianday(created_at) >= 3"
            ).fetchone()["n"]
            c.close()
            guard_stats = login_guard_snapshot()
            try:
                db_bytes = DATABASE_PATH.stat().st_size if DATABASE_PATH.exists() else 0
            except Exception:
                db_bytes = 0
            upload_bytes = 0
            try:
                if UPLOAD_DIR.exists():
                    for p in UPLOAD_DIR.rglob("*"):
                        if p.is_file():
                            upload_bytes += p.stat().st_size
            except Exception:
                upload_bytes = 0
            system_health_cards = (
                "<div class='card' style='margin-top:18px;'><h3>System Health</h3>"
                "<div class='grid-3' style='margin-top:10px;'>"
                f"<div class='stat'><div class='muted'>Users Online</div><div class='stat-num'>{to_int(active_sessions,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Logins (24h)</div><div class='stat-num'>{to_int(logins_24h,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Locked Login Buckets</div><div class='stat-num'>{to_int(guard_stats['locked'],0)}</div></div>"
                f"<div class='stat'><div class='muted'>Tracked Failed Attempts</div><div class='stat-num'>{to_int(guard_stats['fail_total'],0)}</div></div>"
                f"<div class='stat'><div class='muted'>Database Size</div><div class='stat-num'>{esc(_fmt_mb(db_bytes))}</div></div>"
                f"<div class='stat'><div class='muted'>Upload Storage</div><div class='stat-num'>{esc(_fmt_mb(upload_bytes))}</div></div>"
                "</div></div>"
            )
            pending_actions_cards = (
                "<div class='card' style='margin-top:18px;'><h3>Pending Actions</h3>"
                "<div class='grid-3' style='margin-top:10px;'>"
                f"<div class='stat'><div class='muted'>Listing Submissions</div><div class='stat-num'>{to_int(pending_submissions,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Applications</div><div class='stat-num'>{to_int(unhandled_apps,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Inquiries</div><div class='stat-num'>{to_int(unhandled_inquiries,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Lease/Invite Pending</div><div class='stat-num'>{to_int(pending_leases,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Overdue Maintenance</div><div class='stat-num'>{to_int(overdue_maint,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Stuck Submissions (3d+)</div><div class='stat-num'>{to_int(stuck_submissions,0)}</div></div>"
                "</div></div>"
            )
            ops_cards = (
                "<div class='card' style='margin-top:18px;'><h3>Operational Watchlist</h3>"
                "<div class='grid-3' style='margin-top:10px;'>"
                f"<div class='stat'><div class='muted'>Overdue Maintenance (7d+)</div><div class='stat-num'>{to_int(overdue_maint,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Pending Lease/Invite Actions</div><div class='stat-num'>{to_int(pending_leases,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Unresolved Inquiries</div><div class='stat-num'>{to_int(unhandled_inquiries,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Applications Awaiting Review</div><div class='stat-num'>{to_int(unhandled_apps,0)}</div></div>"
                f"<div class='stat'><div class='muted'>Stuck Submissions (3d+)</div><div class='stat-num'>{to_int(stuck_submissions,0)}</div></div>"
                "</div></div>"
            )
            return send_html(self,render(
                "admin_home.html",
                title="Admin Console",
                nav_right=nav(u,"/admin"),
                nav_menu=nav_menu(u,"/admin"),
                stat_users=str(stats["users"]),
                stat_listings=str(stats["listings"]),
                stat_properties=str(stats["properties"]),
                stat_open_maint=str(stats["open_maintenance"]),
                stat_inq=str(stats["new_inquiries"]),
                stat_apps=str(stats["pending_apps"]),
                system_health_cards=system_health_cards,
                pending_actions_cards=pending_actions_cards,
                ops_cards=ops_cards,
            ))

        def _admin_permissions_get(self, u):
            u = self._req_role(u, "admin", action="admin.permissions.manage")
            if not u:
                return
            q = parse_qs(urlparse(self.path).query)
            msg = (q.get("msg") or [""])[0].strip()
            err = (q.get("err") or ["0"])[0] == "1"
            message_box = ""
            if msg:
                klass = "notice err" if err else "notice"
                message_box = f'<div class="{klass}" style="margin-bottom:10px;">{esc(msg)}</div>'
            c = db()
            migrate_role_permissions_table(c)
            rows_db = c.execute("SELECT role,action,allowed FROM role_permissions").fetchall()
            c.commit()
            c.close()
            roles = ["tenant", "property_manager", "admin"]
            perm = {(r["action"], r["role"]): to_int(r["allowed"], 0) for r in rows_db}
            rows = ""
            for action, label in PERMISSION_LABELS:
                cells = ""
                for role in roles:
                    allowed = 1 if perm.get((action, role), 0) else 0
                    target = 0 if allowed else 1
                    cells += (
                        "<td>"
                        "<form method='post' action='/admin/permissions/update' style='margin:0;'>"
                        f"<input type='hidden' name='role' value='{role}'>"
                        f"<input type='hidden' name='action' value='{action}'>"
                        f"<input type='hidden' name='allowed' value='{target}'>"
                        f"<button class='{'primary-btn' if allowed else 'ghost-btn'}' type='submit'>{'Yes' if allowed else 'No'}</button>"
                        "</form>"
                        "</td>"
                    )
                rows += f"<tr><td>{esc(label)}</td>{cells}</tr>"
            rows += (
                "<tr><td><b>Reset to defaults</b></td><td colspan='3'>"
                "<form method='post' action='/admin/permissions/update' style='margin:0;'>"
                "<input type='hidden' name='action' value='__reset_defaults__'>"
                "<button class='secondary-btn' type='submit'>Reset Matrix</button>"
                "</form>"
                "</td></tr>"
            )
            return send_html(self, render("admin_permissions.html", title="Role Permissions", nav_right=nav(u, "/admin/permissions"), nav_menu=nav_menu(u, "/admin/permissions"), matrix_rows=rows, message_box=message_box))

        def _admin_permissions_update(self, u, f):
            u = self._req_role(u, "admin", action="admin.permissions.manage")
            if not u:
                return
            action = (f.get("action") or "").strip()
            role = (f.get("role") or "").strip().lower()
            if action == "__reset_defaults__":
                c = db()
                for a, allowed_roles in PERMISSION_DEFAULTS.items():
                    for r in ("tenant", "property_manager", "admin"):
                        c.execute(
                            "INSERT INTO role_permissions(role,action,allowed,updated_at)VALUES(?,?,?,datetime('now')) "
                            "ON CONFLICT(role,action) DO UPDATE SET allowed=excluded.allowed, updated_at=datetime('now')",
                            (r, a, 1 if r in allowed_roles else 0),
                        )
                audit_log(c, u, "permissions_reset_defaults", "role_permissions", "", "all actions")
                c.commit()
                c.close()
                return redir(self, with_msg("/admin/permissions", "Permission matrix reset to defaults."))
            if action not in PERMISSION_DEFAULTS or role not in ("tenant", "property_manager", "admin"):
                return redir(self, with_msg("/admin/permissions", "Invalid permission update.", True))
            allowed = 1 if str(f.get("allowed") or "0").strip() in ("1", "true", "yes", "on") else 0
            c = db()
            c.execute(
                "INSERT INTO role_permissions(role,action,allowed,updated_at)VALUES(?,?,?,datetime('now')) "
                "ON CONFLICT(role,action) DO UPDATE SET allowed=excluded.allowed, updated_at=datetime('now')",
                (role, action, allowed),
            )
            audit_log(c, u, "permission_updated", "role_permissions", f"{role}:{action}", f"allowed={allowed}")
            c.commit()
            c.close()
            return redir(self, with_msg("/admin/permissions", f"Updated {role} / {action} -> {'Yes' if allowed else 'No'}"))

        def _admin_users_get(self, u):
            u = self._req_role(u, "admin", action="admin.permissions.manage")
            if not u:
                return
            q = parse_qs(urlparse(self.path).query)
            search = ((q.get("q") or [""])[0]).strip().lower()
            role_filter = normalize_role((q.get("role") or [""])[0])
            if role_filter not in ("tenant", "property_manager", "admin"):
                role_filter = ""
            page, per, offset = parse_page_params(q, default_per=30, max_per=200)
            sql_from = (
                " FROM users u "
                "LEFT JOIN (SELECT user_id, MAX(created_at) AS last_login FROM sessions GROUP BY user_id) ss ON ss.user_id=u.id "
                "WHERE 1=1 "
            )
            args = []
            if role_filter:
                sql_from += "AND u.role=? "
                args.append(role_filter)
            if search:
                s = "%" + search + "%"
                sql_from += (
                    "AND (LOWER(COALESCE(u.account_number,'')) LIKE ? OR LOWER(COALESCE(u.full_name,'')) LIKE ? OR "
                    "LOWER(COALESCE(u.username,'')) LIKE ? OR LOWER(COALESCE(u.email,'')) LIKE ?) "
                )
                args.extend([s, s, s, s])
            c = db()
            total = c.execute("SELECT COUNT(1) AS n " + sql_from, tuple(args)).fetchone()["n"]
            rows_db = c.execute(
                "SELECT u.id,u.account_number,u.full_name,u.username,u.email,u.role,u.created_at,ss.last_login "
                + sql_from
                + "ORDER BY u.created_at DESC,u.id DESC LIMIT ? OFFSET ?",
                tuple(args + [per, offset]),
            ).fetchall()
            c.close()
            rows = ""
            for r in rows_db:
                cur_role = normalize_role(r["role"])
                locked, wait_s, fail_total = login_guard_status_for_username(r["username"])
                if locked:
                    status_text = f"Locked ({max(1, int((wait_s + 59) // 60))}m)"
                elif r["last_login"]:
                    status_text = "Active"
                else:
                    status_text = "Never logged in"
                lock_note = f" / {to_int(fail_total,0)} attempts" if fail_total > 0 else ""
                unlock_form = ""
                if locked or fail_total > 0:
                    unlock_form = (
                        "<form method='POST' action='/admin/users/unlock' style='margin:0;'>"
                        f"<input type='hidden' name='user_id' value='{r['id']}'>"
                        "<button class='ghost-btn' type='submit'>Unlock</button>"
                        "</form>"
                    )
                rows += (
                    "<tr>"
                    f"<td>{esc(r['account_number'])}</td>"
                    f"<td>{esc(r['full_name'])}</td>"
                    f"<td>{esc(r['username'])}</td>"
                    f"<td>{esc(r['email'])}</td>"
                    f"<td>{esc(cur_role)}</td>"
                    f"<td>{esc(r['last_login'] or '-')}</td>"
                    f"<td>{esc(status_text + lock_note)}</td>"
                    f"<td>{esc(r['created_at'])}</td>"
                    "<td>"
                    "<form method='POST' action='/admin/users/role' class='row' style='gap:8px;align-items:center;flex-wrap:wrap;margin:0;'>"
                    f"<input type='hidden' name='user_id' value='{r['id']}'>"
                    "<select name='role'>"
                    f"<option value='tenant' {'selected' if cur_role=='tenant' else ''}>tenant</option>"
                    f"<option value='property_manager' {'selected' if cur_role=='property_manager' else ''}>property_manager</option>"
                    f"<option value='admin' {'selected' if cur_role=='admin' else ''}>admin</option>"
                    "</select>"
                    "<button class='secondary-btn' type='submit'>Save</button>"
                    "</form>"
                    + unlock_form +
                    "</td>"
                    "</tr>"
                )
            if not rows:
                rows = "<tr><td colspan='9' class='muted'>No users found.</td></tr>"
            filters_form = (
                "<div class='card' style='margin-bottom:10px;'>"
                "<form method='GET' action='/admin/users' class='row' style='align-items:flex-end;'>"
                "<div class='field' style='min-width:170px;'><label>Role</label>"
                f"<select name='role'><option value=''>All</option><option value='tenant' {'selected' if role_filter=='tenant' else ''}>tenant</option><option value='property_manager' {'selected' if role_filter=='property_manager' else ''}>property_manager</option><option value='admin' {'selected' if role_filter=='admin' else ''}>admin</option></select></div>"
                f"<div class='field' style='min-width:240px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='account/name/username/email'></div>"
                "<button class='primary-btn' type='submit'>Apply</button>"
                "<a class='ghost-btn' href='/admin/users'>Reset</a>"
                "</form>"
                "</div>"
            )
            return send_html(self, render("admin_users.html", title="User Roles", nav_right=nav(u, "/admin/users"), nav_menu=nav_menu(u, "/admin/users"), message_box=query_message_box(q), filters_form=filters_form, rows=rows, pager_box=pager_html("/admin/users", q, page, per, total)))

        def _admin_users_role_update(self, u, f):
            u = self._req_role(u, "admin", action="admin.permissions.manage")
            if not u:
                return
            user_id = to_int(f.get("user_id"), 0)
            new_role = normalize_role(f.get("role"))
            if user_id <= 0 or new_role not in ("tenant", "property_manager", "admin"):
                return redir(self, with_msg("/admin/users", "Invalid role update request.", True))
            c = db()
            tgt = c.execute("SELECT id,role,full_name FROM users WHERE id=?", (user_id,)).fetchone()
            if not tgt:
                c.close()
                return redir(self, with_msg("/admin/users", "User not found.", True))
            cur_role = normalize_role(tgt["role"])
            if cur_role == "admin" and new_role != "admin":
                cnt_admin = to_int(c.execute("SELECT COUNT(1) AS n FROM users WHERE role='admin'").fetchone()["n"], 0)
                if cnt_admin <= 1:
                    c.close()
                    return redir(self, with_msg("/admin/users", "At least one admin account must remain.", True))
            c.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
            audit_log(c, u, "user_role_updated", "users", user_id, f"{cur_role}->{new_role}")
            c.commit()
            c.close()
            return redir(self, with_msg("/admin/users", f"Updated role for {tgt['full_name']} to {new_role}."))

        def _admin_users_unlock(self, u, f):
            u = self._req_role(u, "admin", action="admin.permissions.manage")
            if not u:
                return
            user_id = to_int(f.get("user_id"), 0)
            if user_id <= 0:
                return redir(self, with_msg("/admin/users", "User ID is required.", True))
            c = db()
            tgt = c.execute("SELECT id,username,full_name FROM users WHERE id=?", (user_id,)).fetchone()
            if not tgt:
                c.close()
                return redir(self, with_msg("/admin/users", "User not found.", True))
            removed = login_guard_unlock_username(tgt["username"])
            audit_log(c, u, "user_login_lock_cleared", "users", user_id, f"username={tgt['username']};entries={removed}")
            c.commit()
            c.close()
            return redir(self, with_msg("/admin/users", f"Unlock reset for {tgt['full_name']} complete."))

        def _admin_audit_get(self, u):
            u = self._req_role(u, "admin", action="admin.audit.read")
            if not u:
                return
            q = parse_qs(urlparse(self.path).query)
            role = (q.get("role") or [""])[0].strip()
            action = (q.get("action") or [""])[0].strip()
            range_filter = (q.get("range") or [""])[0].strip().lower()
            if range_filter not in ("", "today", "week", "month"):
                range_filter = ""
            sort = (q.get("sort") or ["newest"])[0].strip().lower()
            order = "DESC" if sort != "oldest" else "ASC"
            page, per, offset = parse_page_params(q, default_per=40, max_per=200)
            sql = (
                "SELECT a.*, uu.full_name AS actor_name "
                "FROM audit_logs a "
                "LEFT JOIN users uu ON uu.id=a.actor_user_id "
                "WHERE 1=1 "
            )
            args = []
            if role:
                sql += "AND a.actor_role=? "
                args.append(role)
            if action:
                sql += "AND a.action LIKE ? "
                args.append(f"%{action}%")
            if range_filter == "today":
                sql += "AND date(a.created_at)=date('now') "
            elif range_filter == "week":
                sql += "AND a.created_at>=datetime('now','-7 days') "
            elif range_filter == "month":
                sql += "AND a.created_at>=datetime('now','-30 days') "
            c = db()
            total = c.execute("SELECT COUNT(1) AS n FROM (" + sql + ") t", tuple(args)).fetchone()["n"]
            rows_db = c.execute(
                sql + f"ORDER BY a.created_at {order}, a.id {order} LIMIT ? OFFSET ?",
                tuple(args + [per, offset]),
            ).fetchall()
            c.close()
            rows = ""
            for r in rows_db:
                ent = f"{r['entity_type'] or '-'} {r['entity_id'] or ''}".strip()
                rows += (
                    "<tr>"
                    f"<td>{esc(r['created_at'])}</td>"
                    f"<td>{esc(r['actor_name'] or '-')}</td>"
                    f"<td>{esc(r['actor_role'] or '-')}</td>"
                    f"<td>{esc(r['action'])}</td>"
                    f"<td>{esc(ent)}</td>"
                    f"<td>{esc(r['details'] or '')}</td>"
                    "</tr>"
                )
            empty = "" if rows_db else '<div class="notice">No audit entries yet.</div>'
            filter_form = (
                "<div class='row' style='margin-bottom:10px;'>"
                f"<a class='ghost-btn' href='/admin/audit?range=today'>Today</a>"
                f"<a class='ghost-btn' href='/admin/audit?range=week'>This Week</a>"
                f"<a class='ghost-btn' href='/admin/audit?range=month'>This Month</a>"
                f"<a class='ghost-btn' href='/admin/audit'>All Time</a>"
                "</div>"
                "<form method='get' action='/admin/audit' class='row' style='margin-bottom:10px;gap:8px;align-items:flex-end;'>"
                "<div class='field' style='min-width:160px;'><label>Role</label>"
                f"<select name='role'><option value=''>All</option><option value='tenant' {'selected' if role=='tenant' else ''}>tenant</option>"
                f"<option value='property_manager' {'selected' if role=='property_manager' else ''}>property_manager</option>"
                f"<option value='landlord' {'selected' if role=='landlord' else ''}>legacy_landlord</option>"
                f"<option value='manager' {'selected' if role=='manager' else ''}>legacy_manager</option>"
                f"<option value='admin' {'selected' if role=='admin' else ''}>admin</option></select></div>"
                "<div class='field' style='min-width:160px;'><label>Range</label>"
                f"<select name='range'><option value='' {'selected' if range_filter=='' else ''}>All</option><option value='today' {'selected' if range_filter=='today' else ''}>Today</option><option value='week' {'selected' if range_filter=='week' else ''}>7 days</option><option value='month' {'selected' if range_filter=='month' else ''}>30 days</option></select></div>"
                f"<div class='field' style='min-width:220px;'><label>Action contains</label><input name='action' value='{esc(action)}' placeholder='invite, approve, lease'></div>"
                "<div class='field' style='min-width:160px;'><label>Sort</label>"
                f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                "<button class='primary-btn' type='submit'>Filter</button>"
                "<a class='ghost-btn' href='/admin/audit'>Reset</a>"
                "</form>"
            )
            filter_form += pager_html("/admin/audit", q, page, per, total)
            return send_html(self, render("admin_audit.html", title="Audit Log", nav_right=nav(u, "/admin/audit"), nav_menu=nav_menu(u, "/admin/audit"), filter_form=filter_form, audit_rows=rows, empty=empty))

        def _admin_audit_export(self, u):
            u = self._req_role(u, "admin", action="admin.audit.read")
            if not u:
                return
            c = db()
            rows_db = c.execute(
                "SELECT a.created_at, COALESCE(uu.full_name,'-') AS actor_name, COALESCE(a.actor_role,'-') AS actor_role, "
                "a.action, COALESCE(a.entity_type,'') AS entity_type, COALESCE(a.entity_id,'') AS entity_id, COALESCE(a.details,'') AS details "
                "FROM audit_logs a LEFT JOIN users uu ON uu.id=a.actor_user_id "
                "ORDER BY a.created_at DESC, a.id DESC LIMIT 5000"
            ).fetchall()
            c.close()
            rows = [["created_at", "actor_name", "actor_role", "action", "entity_type", "entity_id", "details"]]
            for r in rows_db:
                rows.append([r["created_at"], r["actor_name"], r["actor_role"], r["action"], r["entity_type"], r["entity_id"], r["details"]])
            return send_csv(self, "atlas_audit_log.csv", rows)

        def _admin_submissions_get(self,u):
            u = self._req_role(u, "admin", action="admin.submissions.review")
            if not u:
                return
            nr=nav(u,"/admin/submissions")
            q=parse_qs(urlparse(self.path).query)
            msg=(q.get("msg") or [""])[0].strip()
            err=(q.get("err") or ["0"])[0].strip()=="1"
            st_filter=(q.get("status") or [""])[0].strip().lower()
            prop_filter=(q.get("property") or [""])[0].strip()
            search=(q.get("q") or [""])[0].strip()
            sort=(q.get("sort") or ["newest"])[0].strip().lower()
            order="DESC" if sort!="oldest" else "ASC"
            page, per, offset = parse_page_params(q, default_per=30, max_per=200)
            c=db()
            sql=(
                "SELECT r.*, p.name AS prop_name, u.unit_label AS unit_label "
                "FROM listing_requests r "
                "LEFT JOIN properties p ON p.id=r.property_id "
                "LEFT JOIN units u ON u.id=r.unit_id "
                "WHERE 1=1 "
            )
            args=[]
            if st_filter in ("pending","approved","rejected"):
                sql += "AND r.status=? "
                args.append(st_filter)
            if prop_filter:
                sql += "AND r.property_id=? "
                args.append(prop_filter)
            if search:
                sql += "AND (r.title LIKE ? OR r.location LIKE ? OR p.name LIKE ?) "
                args.extend([f"%{search}%"] * 3)
            total = c.execute("SELECT COUNT(1) AS n FROM (" + sql + ") t", tuple(args)).fetchone()["n"]
            reqs=c.execute(sql + f"ORDER BY r.created_at {order}, r.id {order} LIMIT ? OFFSET ?", tuple(args + [per, offset])).fetchall()
            props=c.execute("SELECT id,name FROM properties ORDER BY created_at DESC LIMIT 500").fetchall()
            rows=""
            pending_count = 0
            for r in reqs:
                actions=""
                note_col = esc((r["approval_note"] or "").strip()) if "approval_note" in r.keys() else ""
                cp = 1 if to_int(r["checklist_photos"], 0) else 0
                cpr = 1 if to_int(r["checklist_price"], 0) else 0
                cd = 1 if to_int(r["checklist_description"], 0) else 0
                cdoc = 1 if to_int(r["checklist_docs"], 0) else 0
                checklist_col = (
                    f"<div class='row'><span class='badge {'ok' if cp else 'no'}'>photos:{'ok' if cp else 'missing'}</span>"
                    f"<span class='badge {'ok' if cpr else 'no'}'>price:{'ok' if cpr else 'check'}</span>"
                    f"<span class='badge {'ok' if cd else 'no'}'>description:{'ok' if cd else 'check'}</span>"
                    f"<span class='badge {'ok' if cdoc else 'no'}'>docs:{'ok' if cdoc else 'check'}</span></div>"
                )
                if r["status"]=="pending":
                    pending_count += 1
                    actions = (
                        f"<form method='post' action='/admin/submissions/review' style='display:flex;gap:6px;align-items:center;flex-wrap:wrap;'>"
                        f"<input type='hidden' name='req_id' value='{r['id']}'>"
                        f"<select name='checklist_photos'><option value='1' {'selected' if cp else ''}>photos ok</option><option value='0' {'selected' if not cp else ''}>photos missing</option></select>"
                        f"<select name='checklist_price'><option value='1' {'selected' if cpr else ''}>price ok</option><option value='0' {'selected' if not cpr else ''}>price check</option></select>"
                        f"<select name='checklist_description'><option value='1' {'selected' if cd else ''}>description ok</option><option value='0' {'selected' if not cd else ''}>description check</option></select>"
                        f"<select name='checklist_docs'><option value='1' {'selected' if cdoc else ''}>docs ok</option><option value='0' {'selected' if not cdoc else ''}>docs check</option></select>"
                        "<select name='decision'><option value='approve'>Approve</option><option value='request_changes'>Request Changes</option><option value='reject'>Reject</option></select>"
                        "<input name='note' placeholder='Review note / required for reject' style='min-width:220px;'>"
                        f"<button class='primary-btn' type='submit'>Submit Review</button>"
                        f"</form>"
                    )
                else:
                    actions = "<span class='muted'>-</span>"
                prop_name = r["prop_name"] if ("prop_name" in r.keys() and r["prop_name"]) else r["property_id"]
                unit_label = r["unit_label"] if ("unit_label" in r.keys() and r["unit_label"]) else ""
                rows += f"<tr><td>{r['id']}</td><td>{esc(r['title'])}</td><td>{esc(prop_name)}</td><td>{esc(unit_label)}</td><td>${int(r['price']):,}</td><td>{status_badge(r['status'],'review')}</td><td>{checklist_col}</td><td>{note_col}</td><td>{actions}</td></tr>"
            empty = "" if reqs else "<p class='muted' style='margin:12px 0 0;'>No submissions yet.</p>"
            bulk_actions = ""
            if pending_count:
                bulk_actions = (
                    "<form method='post' action='/admin/submissions/approve_all' class='row' style='margin-bottom:12px;'>"
                    "<input name='note' placeholder='Approval note for all (optional)' style='min-width:220px;'>"
                    "<button class='primary-btn' type='submit'>Approve All Pending</button>"
                    f"<div class='muted' style='align-self:center;'>Pending: {pending_count}</div>"
                    "</form>"
                )
            prop_opts = "".join(f"<option value='{esc(p['id'])}' {'selected' if prop_filter==p['id'] else ''}>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
            filters_form = (
                "<form method='get' action='/admin/submissions' class='row' style='margin-bottom:10px;gap:8px;align-items:flex-end;'>"
                "<div class='field' style='min-width:140px;'><label>Status</label>"
                f"<select name='status'><option value=''>All</option><option value='pending' {'selected' if st_filter=='pending' else ''}>pending</option>"
                f"<option value='approved' {'selected' if st_filter=='approved' else ''}>approved</option><option value='rejected' {'selected' if st_filter=='rejected' else ''}>rejected</option></select></div>"
                f"<div class='field' style='min-width:260px;'><label>Property</label><select name='property'><option value=''>All</option>{prop_opts}</select></div>"
                f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='title/location'></div>"
                "<div class='field' style='min-width:160px;'><label>Sort</label>"
                f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                "<button class='primary-btn' type='submit'>Apply</button><a class='ghost-btn' href='/admin/submissions'>Reset</a></form>"
            )
            filters_form += pager_html("/admin/submissions", q, page, per, total)
            if msg:
                filters_form = f"<div class='{'notice err' if err else 'notice'}' style='margin-bottom:10px;'>{esc(msg)}</div>" + filters_form
            c.close()
            return send_html(self,render("admin_submissions.html",title="Listing Submissions",nav_right=nr,nav_menu=nav_menu(u,"/admin/submissions"),rows=rows,empty=empty,bulk_actions=bulk_actions,filters_form=filters_form))

        def _admin_submissions_review(self,u,f):
            u = self._req_role(u, "admin", action="admin.submissions.review")
            if not u:
                return
            req_id=to_int(f.get("req_id"), 0)
            if req_id <= 0:
                return redir(self, with_msg("/admin/submissions", "Request ID missing.", True))
            decision = (f.get("decision") or "approve").strip().lower()
            if decision not in ("approve", "request_changes", "reject"):
                decision = "approve"
            note=(f.get("note") or "").strip()[:280]
            cp = 1 if str(f.get("checklist_photos") or "0").strip() in ("1","true","yes","on") else 0
            cpr = 1 if str(f.get("checklist_price") or "0").strip() in ("1","true","yes","on") else 0
            cd = 1 if str(f.get("checklist_description") or "0").strip() in ("1","true","yes","on") else 0
            cdoc = 1 if str(f.get("checklist_docs") or "0").strip() in ("1","true","yes","on") else 0
            c=db()
            r=c.execute("SELECT * FROM listing_requests WHERE id=?",(req_id,)).fetchone()
            if not r:
                c.close()
                return e404(self)
            if r["status"]!="pending":
                c.close()
                return redir(self, with_msg("/admin/submissions", "Submission is no longer pending.", True))

            if decision == "approve":
                missing = []
                if not cp: missing.append("photos")
                if not cpr: missing.append("price")
                if not cd: missing.append("description")
                if not cdoc: missing.append("docs")
                if missing:
                    c.execute(
                        "UPDATE listing_requests SET checklist_photos=?,checklist_price=?,checklist_description=?,checklist_docs=?,"
                        "approval_note=?,review_state='changes_requested',status='rejected',reviewed_at=datetime('now') WHERE id=?",
                        (cp, cpr, cd, cdoc, f"Checklist incomplete: {', '.join(missing)}", req_id),
                    )
                    if r["submitted_by_user_id"]:
                        create_notification(c, r["submitted_by_user_id"], f"Listing needs changes before approval: {r['title']}", "/landlord/listing-requests")
                    audit_log(c, u, "listing_request_changes_requested", "listing_requests", req_id, f"missing={','.join(missing)}")
                    c.commit()
                    c.close()
                    return redir(self, with_msg("/admin/submissions", "Checklist incomplete. Changes requested for this submission.", True))
                title=(r["title"] or "").strip()
                desc=(r["description"] or "").strip()
                issues=[]
                if len(title)<4:issues.append("title")
                if len(desc)<8:issues.append("description")
                if issues:
                    c.execute(
                        "UPDATE listing_requests SET checklist_photos=?,checklist_price=?,checklist_description=?,checklist_docs=?,"
                        "approval_note=?,review_state='changes_requested',status='rejected',reviewed_at=datetime('now') WHERE id=?",
                        (cp, cpr, cd, cdoc, f"Needs fixes: {', '.join(issues)}", req_id),
                    )
                    if r["submitted_by_user_id"]:
                        create_notification(c, r["submitted_by_user_id"], f"Listing needs fixes: {r['title']}", "/landlord/listing-requests")
                    audit_log(c, u, "listing_request_changes_requested", "listing_requests", req_id, f"issues={','.join(issues)}")
                    c.commit();c.close()
                    return redir(self, with_msg("/admin/submissions", "Submission needs fixes before approval.", True))
                listing_id = approve_listing_request(c, r)
                c.execute(
                    "UPDATE listing_requests SET checklist_photos=?,checklist_price=?,checklist_description=?,checklist_docs=?,"
                    "approval_note=?,review_state='approved',reviewed_at=datetime('now') WHERE id=?",
                    (cp, cpr, cd, cdoc, note, req_id),
                )
                audit_log(c, u, "listing_request_approved", "listing_requests", req_id, f"listing_id={listing_id}; note={note}")
                c.commit();c.close()
                return redir(self, with_msg("/admin/submissions", "Submission approved."))

            if decision in ("request_changes", "reject") and not note:
                c.close()
                return redir(self, with_msg("/admin/submissions", "Review note is required when rejecting or requesting changes.", True))
            state = "changes_requested" if decision == "request_changes" else "rejected"
            c.execute(
                "UPDATE listing_requests SET status='rejected',approval_note=?,review_state=?,"
                "checklist_photos=?,checklist_price=?,checklist_description=?,checklist_docs=?,reviewed_at=datetime('now') WHERE id=?",
                (note, state, cp, cpr, cd, cdoc, req_id),
            )
            if r["submitted_by_user_id"]:
                msg = "Listing update requested" if decision == "request_changes" else "Listing rejected"
                create_notification(c, r["submitted_by_user_id"], f"{msg}: {r['title']} ({note})", "/landlord/listing-requests")
            audit_log(c, u, "listing_request_reviewed", "listing_requests", req_id, f"decision={decision};note={note}")
            c.commit();c.close()
            return redir(self, with_msg("/admin/submissions", "Submission review saved."))

        def _admin_submissions_approve(self,u,f):
            f2 = dict(f or {})
            f2["decision"] = "approve"
            f2.setdefault("checklist_photos", "1")
            f2.setdefault("checklist_price", "1")
            f2.setdefault("checklist_description", "1")
            f2.setdefault("checklist_docs", "1")
            return self._admin_submissions_review(u, f2)

        def _admin_submissions_approve_all(self,u,f):
            u = self._req_role(u, "admin", action="admin.submissions.review")
            if not u:
                return
            note=(f.get("note") or "").strip()[:280]
            c=db()
            pending=c.execute("SELECT * FROM listing_requests WHERE status='pending' ORDER BY id").fetchall()
            for r in pending:
                req_id = r["id"]
                title=(r["title"] or "").strip()
                desc=(r["description"] or "").strip()
                issues=[]
                if len(title)<4:issues.append("title")
                if len(desc)<8:issues.append("description")
                if issues:
                    c.execute(
                        "UPDATE listing_requests SET status='rejected',approval_note=?,review_state='changes_requested',"
                        "checklist_photos=1,checklist_price=1,checklist_description=0,checklist_docs=1,reviewed_at=datetime('now') "
                        "WHERE id=?",
                        (f"Needs fixes: {', '.join(issues)}",req_id),
                    )
                    if r["submitted_by_user_id"]:
                        create_notification(c, r["submitted_by_user_id"], f"Listing needs fixes: {r['title']}", "/landlord/listing-requests")
                    audit_log(c, u, "listing_request_changes_requested", "listing_requests", req_id, f"issues={','.join(issues)}")
                    continue
                listing_id = approve_listing_request(c, r)
                c.execute(
                    "UPDATE listing_requests SET approval_note=?,review_state='approved',checklist_photos=1,checklist_price=1,"
                    "checklist_description=1,checklist_docs=1,reviewed_at=datetime('now') WHERE id=?",
                    (note, req_id),
                )
                audit_log(c, u, "listing_request_approved", "listing_requests", req_id, f"listing_id={listing_id}; note={note}")
            if pending:
                c.commit()
            c.close()
            return redir(self,"/admin/submissions")

        def _admin_submissions_reject(self,u,f):
            f2 = dict(f or {})
            mode = (f2.get("mode") or "").strip().lower()
            f2["decision"] = "request_changes" if mode == "changes_requested" else "reject"
            f2.setdefault("checklist_photos", "0")
            f2.setdefault("checklist_price", "0")
            f2.setdefault("checklist_description", "0")
            f2.setdefault("checklist_docs", "0")
            return self._admin_submissions_review(u, f2)


