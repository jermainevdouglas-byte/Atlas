"""AuthHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class AuthHandlerMixin:
        def _login(self,f,u):
            if u:return redir(self,role_home(u["role"]))
            un=(f.get("username")or"").strip();pw=f.get("password")or""
            ip=client_ip(self.headers)
            blocked, wait_s = login_guard_check(ip, un)
            if blocked:
                mins = max(1, int((wait_s + 59) // 60))
                return send_html(self,render("login.html",title="Log in",nav_right=nav(None),nav_menu=nav_menu(None),error_box=f'<div class="notice err"><b>Login locked:</b> Too many attempts. Try again in about {mins} minute(s).</div>'))
            if not un or not pw:
                return send_html(self,render("login.html",title="Log in",nav_right=nav(None),nav_menu=nav_menu(None),error_box='<div class="notice err"><b>Login failed:</b> Missing fields.</div>'))
            c=db()
            r=c.execute("SELECT * FROM users WHERE username=?",(un,)).fetchone()
            if not r:
                # Usability hardening: allow case-insensitive username login.
                # If multiple case-variants exist, fail safely as ambiguous.
                rows = c.execute(
                    "SELECT * FROM users WHERE LOWER(username)=LOWER(?) ORDER BY id LIMIT 2",
                    (un,),
                ).fetchall()
                if len(rows) == 1:
                    r = rows[0]
                elif len(rows) > 1:
                    c.close()
                    login_guard_fail(ip, un)
                    return send_html(self,render("login.html",title="Log in",nav_right=nav(None),nav_menu=nav_menu(None),error_box='<div class="notice err"><b>Login failed:</b> Username is ambiguous by letter case. Use exact username case.</div>'))
            if not r:
                c.close()
                login_guard_fail(ip, un)
                return send_html(self,render("login.html",title="Log in",nav_right=nav(None),nav_menu=nav_menu(None),error_box='<div class="notice err"><b>Login failed:</b> Invalid credentials.</div>'))
            h=pw_hash(pw,_salt_bytes(r["password_salt"]))
            if not hmac.compare_digest(h,r["password_hash"]):
                c.close()
                login_guard_fail(ip, un)
                return send_html(self,render("login.html",title="Log in",nav_right=nav(None),nav_menu=nav_menu(None),error_box='<div class="notice err"><b>Login failed:</b> Invalid credentials.</div>'))
            sid=create_session(c,r["id"],self.headers);c.close()
            login_guard_clear(ip, un)
            csrf = new_csrf_token()
            cookies = [
                f"{SESSION_COOKIE}={sid}; {session_cookie_attrs(self.headers)}",
                f"{CSRF_COOKIE}={csrf}; {csrf_cookie_attrs(self.headers)}",
            ]
            return redir(self,role_home(r["role"]),cookies=cookies)

        def _register(self,f,u):
            if u:return redir(self,role_home(u["role"]))
            fn=(f.get("full_name")or"").strip();ph=(f.get("phone")or"").strip();em=(f.get("email")or"").strip()
            un=(f.get("username")or"").strip();pw=f.get("password")or"";rl=f.get("role")or"tenant"
            # Public registration only creates tenant accounts. Property Manager is admin-managed.
            if rl != "tenant":
                rl = "tenant"
            pw_errs = password_policy_errors(pw)
            if len(fn)<2 or len(ph)<5 or"@"not in em or len(un)<3 or pw_errs:
                detail = "Check inputs." if not pw_errs else ("Password must include: " + ", ".join(pw_errs) + ".")
                return send_html(self,render("register.html",title="Register",nav_right=nav(None),nav_menu=nav_menu(None),message_box=f'<div class="notice err"><b>Error:</b> {esc(detail)}</div>'))
            c=db()
            if c.execute("SELECT 1 FROM users WHERE username=?",(un,)).fetchone():c.close();return send_html(self,render("register.html",title="Register",nav_right=nav(None),nav_menu=nav_menu(None),message_box='<div class="notice err"><b>Error:</b> Username taken.</div>'))
            a=create_user(c,fn,ph,em,un,pw,rl);c.close()
            return send_html(self,render("register.html",title="Register",nav_right=nav(None),nav_menu=nav_menu(None),message_box=f'<div class="notice"><b>Success!</b> Account: {esc(a)}. <a href="/login">Log in</a></div>'))

        def _logout(self,u):
            if not u:return redir(self,"/")
            signed=get_cookie(self.headers.get("Cookie",""),SESSION_COOKIE);raw=unsign(signed)if signed else None
            if raw:
                invalidate_session_raw(raw)

            secure = "; Secure" if cookie_secure(self.headers) else ""
            return redir(self,"/",cookies=[
                f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}",
                f"{CSRF_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax{secure}",
            ])

        def _forgot(self, f, u):
            if u:return redir(self,role_home(u["role"]))
            ident=(f.get("ident") or "").strip()
            c=db()
            user=get_user_by_email_or_username(c,ident)
            link = ""
            exp = ""
            sent = False
            if user:
                tok, exp = new_reset_token(c, user["id"])
                link = self._absolute_url(f"/reset?token={tok}")
                email_body = (
                    "A password reset was requested for your AtlasBahamas account.\n\n"
                    f"Use this link to reset your password:\n{link}\n\n"
                    f"This link expires at {exp} UTC.\n"
                    "If you did not request this, you can ignore this message."
                )
                sent = send_email((user["email"] or "").strip(), "AtlasBahamas Password Reset", email_body)
            c.commit();c.close()
            msg = "<div class='notice'><b>If an account exists for that identifier, a reset link has been sent to the registered email.</b></div>"
            if user and not sent and (not SMTP_HOST or not SMTP_FROM):
                msg += "<div class='notice err' style='margin-top:10px;'><b>Email is not configured.</b> Set `SMTP_HOST` and `SMTP_FROM` (plus optional auth vars) to deliver reset emails.</div>"
            if link and RESET_LINK_IN_RESPONSE and (request_is_local(self.headers) or ALLOW_RESET_LINK_IN_RESPONSE_NONLOCAL):
                msg += f"<div class='notice' style='margin-top:10px;'><b>Debug reset link:</b> <a href='{esc(link)}'>{esc(link)}</a></div>"
            return send_html(self,render("forgot_password.html",title="Reset password",nav_right=nav(None),nav_menu=nav_menu(None),message_box=msg))

        def _reset(self, f, u):
            if u:return redir(self,role_home(u["role"]))
            tok=(f.get("token") or "").strip()
            pw=(f.get("password") or "")
            pw2=(f.get("password2") or "")
            if not tok:
                return send_html(self,render("reset_password.html",title="Choose new password",nav_right=nav(None),nav_menu=nav_menu(None),
                                             token_value="",
                                             message_box='<div class="notice err"><b>Error:</b> Reset token is missing. Use the link from your reset email.</div>'))
            errs = password_policy_errors(pw)
            if pw!=pw2 or errs:
                detail = "Passwords must match." if pw != pw2 else ("Password must include: " + ", ".join(errs) + ".")
                return send_html(self,render("reset_password.html",title="Choose new password",nav_right=nav(None),nav_menu=nav_menu(None),
                                             token_value=esc(tok),
                                             message_box=f'<div class="notice err"><b>Error:</b> {esc(detail)}</div>'))
            c=db()
            r=valid_reset(c,tok)
            if not r:
                c.close()
                return send_html(self,render("reset_password.html",title="Choose new password",nav_right=nav(None),nav_menu=nav_menu(None),
                                             token_value=esc(tok),
                                             message_box='<div class="notice err"><b>Error:</b> Token invalid or expired.</div>'))
            user=c.execute("SELECT * FROM users WHERE id=?",(r["user_id"],)).fetchone()
            s=secrets.token_bytes(16);h=pw_hash(pw,s)
            c.execute("UPDATE users SET password_salt=?, password_hash=? WHERE id=?",(s.hex(),h,user["id"]))
            c.execute("UPDATE password_resets SET used=1 WHERE id=?",(r["id"],))
            invalidate_user_sessions(c, user["id"])
            create_notification(c,user["id"],"Your password was changed successfully.", "/login")
            audit_log(c, {"id": user["id"], "role": user["role"]}, "password_reset_completed", "users", user["id"], "self_service")
            c.commit();c.close()
            return send_html(self,render("reset_password.html",title="Password updated",nav_right=nav(None),nav_menu=nav_menu(None),
                                         token_value=esc(tok),
                                         message_box='<div class="notice"><b>Done!</b> Your password has been updated. <a href="/login">Log in</a>.</div>'))

        def _profile_get(self, u, message_box=""):
            c=db()
            row=c.execute("SELECT full_name,phone,email FROM users WHERE id=?",(u["id"],)).fetchone()
            c.close()
            if not row:
                return redir(self, "/login")
            return send_html(self,render_page(
                "profile.html",
                "Profile",
                u,
                "/profile",
                message_box=message_box,
                full_name=esc(row["full_name"]),
                phone=esc(row["phone"]),
                email=esc(row["email"]),
            ))

        def _profile_update(self, f, u):
            if not u:
                return redir(self, "/login")
            fn=(f.get("full_name") or "").strip()
            ph=(f.get("phone") or "").strip()
            em=(f.get("email") or "").strip()
            cur=(f.get("current_password") or "")
            npw=(f.get("new_password") or "")
            npw2=(f.get("new_password2") or "")
            if len(fn)<2 or len(ph)<5 or "@" not in em:
                return self._profile_get(u, '<div class="notice err"><b>Error:</b> Name, phone, and email are required.</div>')

            c=db()
            row=c.execute("SELECT password_salt,password_hash FROM users WHERE id=?",(u["id"],)).fetchone()
            if not row:
                c.close()
                return redir(self, "/login")
            if npw or npw2 or cur:
                errs = password_policy_errors(npw)
                if npw != npw2 or errs:
                    c.close()
                    detail = "New passwords must match." if npw != npw2 else ("Password must include: " + ", ".join(errs) + ".")
                    return self._profile_get(u, f'<div class="notice err"><b>Error:</b> {esc(detail)}</div>')
                curh = pw_hash(cur, _salt_bytes(row["password_salt"]))
                if not hmac.compare_digest(curh, row["password_hash"]):
                    c.close()
                    return self._profile_get(u, '<div class="notice err"><b>Error:</b> Current password is incorrect.</div>')
                s=secrets.token_bytes(16);h=pw_hash(npw,s)
                c.execute("UPDATE users SET full_name=?, phone=?, email=?, password_salt=?, password_hash=? WHERE id=?",
                          (fn,ph,em,s.hex(),h,u["id"]))
            else:
                c.execute("UPDATE users SET full_name=?, phone=?, email=? WHERE id=?",(fn,ph,em,u["id"]))
            create_notification(c,u["id"],"Profile updated successfully.", "/profile")
            c.commit();c.close()
            return self._profile_get(u, '<div class="notice"><b>Saved.</b> Your profile has been updated.</div>')



