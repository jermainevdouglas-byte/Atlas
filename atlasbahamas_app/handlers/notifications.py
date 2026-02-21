"""NotificationsHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


def _format_alert_time_label(raw_value):
        txt = str(raw_value or "").strip()
        if not txt:
            return ""
        try:
            norm = txt.replace("Z", "+00:00")
            dt = datetime.fromisoformat(norm)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.strftime("%b %d, %Y %I:%M %p")
        except Exception:
            try:
                return txt.replace("T", " ")[:19]
            except Exception:
                return txt


class NotificationsHandlerMixin:
        def _notifications_get(self, u):
            q = parse_qs(urlparse(self.path).query)
            c=db()
            rows=c.execute(
                "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
                (u["id"],)
            ).fetchall()
            total_count = len(rows)
            unread_count = sum(1 for r in rows if not to_int(r["is_read"], 0))
            linked_count = sum(1 for r in rows if (r["link"] or "").strip())
            today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_count = sum(1 for r in rows if str(r["created_at"] or "").startswith(today_key))
            items=""
            for r in rows:
                is_read = bool(to_int(r["is_read"], 0))
                cls = "alert-item is-read" if is_read else "alert-item is-unread"
                link=(r["link"] or "").strip()
                category = _classify_notification_category(link, r["text"], "general")
                category_label = {
                    "payment": "Payments",
                    "maintenance": "Maintenance",
                    "lease": "Leases",
                    "invite": "Invites",
                    "application": "Applications",
                    "inquiry": "Inquiries",
                    "system": "System",
                }.get(category, "System")
                time_label = _format_alert_time_label(r["created_at"])
                action_html = ""
                if link:
                    action_html = f"<a class='alert-open' href='{esc(link)}'>View</a>"
                state_html = "<span class='alert-state state-unread'>New</span>" if not is_read else ""
                actions_inner = action_html + state_html
                if not actions_inner:
                    actions_inner = "<span class='alert-state'>Update</span>"
                items += (
                    f"<article class='{cls}' data-read='{'1' if is_read else '0'}' data-has-link='{'1' if link else '0'}' data-kind='{esc(category)}'>"
                    "<div class='alert-main'>"
                    "<div class='alert-meta'>"
                    f"<span class='alert-kind kind-{esc(category)}'><span class='alert-kind-dot'></span>{esc(category_label)}</span>"
                    f"<span class='alert-time'>{esc(time_label)}</span>"
                    "</div>"
                    f"<div class='alert-text'>{esc(r['text'])}</div>"
                    f"<div class='alert-actions'>{actions_inner}</div>"
                    "</div>"
                    "</article>"
                )
            c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?",(u["id"],))
            c.commit();c.close()
            if not items:
                items = (
                    "<div class='alerts-empty'>"
                    "<div class='alerts-empty-icon'>!</div>"
                    "<div><b>No alerts yet.</b><div class='muted'>You are all caught up.</div></div>"
                    "</div>"
                )
            return send_html(
                self,
                render(
                    "notifications.html",
                    title="Alerts",
                    nav_right=nav(u,"/notifications"),
                    nav_menu=nav_menu(u,"/notifications"),
                    message_box=query_message_box(q),
                    notifications_html=items,
                    total_count=str(total_count),
                    unread_count=str(unread_count),
                    linked_count=str(linked_count),
                    today_count=str(today_count),
                ),
            )

        def _notifications_readall(self, f, u):
            if not u:return send_json(self,{"ok":False},401)
            db_write_retry(lambda c: c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?",(u["id"],)))
            accept = (self.headers.get("Accept") or "").lower()
            xrw = (self.headers.get("X-Requested-With") or "").lower()
            if "application/json" in accept or xrw == "xmlhttprequest":
                return send_json(self,{"ok":True})
            return redir(self, with_msg("/notifications", "All alerts marked as read."))

        def _notifications_preferences_get(self, u):
            q = parse_qs(urlparse(self.path).query)
            c = db()
            pref = ensure_notification_preferences(c, u["id"])
            c.close()
            ctx = {}
            for key in NOTIFICATION_PREF_KEYS:
                ctx[f"{key}_checked"] = "checked" if (pref and to_int(pref[key], 0)) else ""
            return send_html(
                self,
                render(
                    "notifications_preferences.html",
                    title="Notification Preferences",
                    nav_right=nav(u, "/notifications/preferences"),
                    nav_menu=nav_menu(u, "/notifications/preferences"),
                    message_box=query_message_box(q),
                    **ctx,
                ),
            )

        def _notifications_preferences_post(self, f, u):
            if not u:
                return redir(self, "/login")
            c = db()
            ensure_notification_preferences(c, u["id"])
            vals = {}
            for key in NOTIFICATION_PREF_KEYS:
                vals[key] = 1 if str(f.get(key) or "0").strip().lower() in ("1", "true", "yes", "on") else 0
            c.execute(
                "UPDATE notification_preferences SET "
                "payment_events=?,maintenance_events=?,lease_events=?,invite_events=?,"
                "application_events=?,inquiry_events=?,system_events=?,email_enabled=?,sms_enabled=?,"
                "updated_at=datetime('now') WHERE user_id=?",
                (
                    vals["payment_events"],
                    vals["maintenance_events"],
                    vals["lease_events"],
                    vals["invite_events"],
                    vals["application_events"],
                    vals["inquiry_events"],
                    vals["system_events"],
                    vals["email_enabled"],
                    vals["sms_enabled"],
                    u["id"],
                ),
            )
            audit_log(
                c,
                u,
                "notification_preferences_updated",
                "notification_preferences",
                u["id"],
                ";".join(f"{k}={vals[k]}" for k in NOTIFICATION_PREF_KEYS),
            )
            c.commit()
            c.close()
            return redir(self, with_msg("/notifications/preferences", "Notification preferences saved."))

        def _onboarding_get(self, u):
            q = parse_qs(urlparse(self.path).query)
            c = db()
            state = onboarding_state_for_user(c, u)
            c.close()
            role = state.get("role") or normalize_role(u.get("role"))
            checklist = state.get("checklist") or {}
            steps = ONBOARDING_STEPS.get(role, ONBOARDING_STEPS["tenant"])
            done_count = 0
            rows = ""
            for key, label, link in steps:
                done = 1 if to_int(checklist.get(key), 0) else 0
                if done:
                    done_count += 1
                rows += (
                    "<div class='card'>"
                    f"<div class='row' style='justify-content:space-between;align-items:center;'><div><b>{esc(label)}</b><div class='muted'>{esc(link)}</div></div>"
                    f"<div>{'<span class=\"badge ok\">Done</span>' if done else '<span class=\"badge\">Pending</span>'}</div></div>"
                    "<div class='row' style='margin-top:8px;'>"
                    f"<a class='ghost-btn' href='{esc(link)}'>Open</a>"
                    "<form method='POST' action='/onboarding/step' style='margin:0;'>"
                    f"<input type='hidden' name='step_key' value='{esc(key)}'>"
                    f"<input type='hidden' name='done' value='{'0' if done else '1'}'>"
                    f"<button class='secondary-btn' type='submit'>{'Mark Pending' if done else 'Mark Done'}</button>"
                    "</form>"
                    "</div>"
                    "</div>"
                )
            total = len(steps)
            pct = int(round((done_count / total) * 100.0)) if total > 0 else 0
            summary_box = (
                "<div class='card' style='margin-bottom:12px;'>"
                "<h3 style='margin-top:0;'>Progress</h3>"
                f"<div class='muted'>{done_count} of {total} steps complete ({pct}%).</div>"
                "</div>"
            )
            return send_html(
                self,
                render(
                    "onboarding.html",
                    title="Onboarding",
                    nav_right=nav(u, "/onboarding"),
                    nav_menu=nav_menu(u, "/onboarding"),
                    message_box=query_message_box(q),
                    summary_box=summary_box,
                    steps_rows=rows,
                    home_path=role_home(role),
                ),
            )

        def _onboarding_step_post(self, f, u):
            if not u:
                return redir(self, "/login")
            role = normalize_role(u.get("role"))
            allowed_keys = {k for k, _, _ in ONBOARDING_STEPS.get(role, [])}
            key = (f.get("step_key") or "").strip()
            if key not in allowed_keys:
                return redir(self, with_msg("/onboarding", "Step key is invalid.", True))
            done = 1 if str(f.get("done") or "0").strip() in ("1", "true", "yes", "on") else 0
            c = db()
            state = onboarding_state_for_user(c, u)
            checklist = state.get("checklist") or {}
            checklist[key] = done
            total = len(allowed_keys)
            done_count = sum(1 for k in allowed_keys if to_int(checklist.get(k), 0))
            completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if (total > 0 and done_count >= total) else None
            c.execute(
                "UPDATE user_onboarding SET role=?,checklist_json=?,completed_at=?,updated_at=datetime('now') WHERE user_id=?",
                (role, json.dumps(checklist), completed_at, u["id"]),
            )
            audit_log(c, u, "onboarding_step_updated", "user_onboarding", u["id"], f"{key}={done}")
            c.commit()
            c.close()
            return redir(self, with_msg("/onboarding", "Onboarding checklist updated."))



