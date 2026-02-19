"""HTTP request handler module extracted from monolith."""
from . import core as _core

# Import every symbol from core, including private helpers (leading underscore),
# because the legacy handler references many of them directly.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class H(BaseHTTPRequestHandler):
    server_version="Atlas/1.0"

    def _absolute_url(self, path):
        p = path if str(path).startswith("/") else f"/{path}"
        host = safe_request_host(self.headers)
        proto = "https" if (request_is_secure(self.headers) or (ENFORCE_HTTPS and not request_is_local(self.headers))) else "http"
        return f"{proto}://{host}{p}"

    def _https_redirect_if_needed(self):
        if not ENFORCE_HTTPS:
            return False
        if request_is_secure(self.headers):
            return False
        if request_is_local(self.headers):
            return False
        host = safe_request_host(self.headers)
        target = f"https://{host}{self.path}"
        redir(self, target, status=301)
        return True

    def do_GET(self):
        start = time.perf_counter()
        try:self._get()
        except Exception:
            traceback.print_exc()
            try:e500(self)
            except:pass
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if elapsed_ms >= 800:
                print(f"[slow] GET {self.path} {elapsed_ms}ms")

    def do_POST(self):
        start = time.perf_counter()
        try:self._post()
        except Exception:
            traceback.print_exc()
            try:e500(self)
            except:pass
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if elapsed_ms >= 800:
                print(f"[slow] POST {self.path} {elapsed_ms}ms")

    def _get(self):
        if self._https_redirect_if_needed():
            return
        run_housekeeping_if_due()
        parsed=urlparse(self.path);path=parsed.path;q=parse_qs(parsed.query);u=cur_user(self.headers)
        if path.startswith("/static/"):return self._static(path)
        if path.startswith("/uploads/"):return self._uploads(path)
        if path=="/api/listings":return self._api_listings(q)
        if path=="/api/units":return self._api_units(q,u)
        if path=="/":return send_html(self,render_page("home.html","Atlas",u,path))
        if path=="/about":return send_html(self,render_page("about.html","About Atlas",u,path))
        if path=="/contact":return send_html(self,render_page("contact.html","Contact Atlas",u,path))
        if path=="/changelog":
            if not u:
                return redir(self, "/login")
            u2 = self._req_role(u, "admin", action="admin.audit.read")
            if not u2:
                return
            c = db()
            latest = c.execute(
                "SELECT created_at,actor_role,action,entity_type,entity_id,details "
                "FROM audit_logs ORDER BY id DESC LIMIT 50"
            ).fetchall()
            c.close()
            audit_rows = ""
            for r in latest:
                audit_rows += (
                    "<tr>"
                    f"<td>{esc(r['created_at'])}</td>"
                    f"<td>{esc(r['actor_role'] or '-')}</td>"
                    f"<td>{esc(r['action'])}</td>"
                    f"<td>{esc(r['entity_type'] or '-')}#{esc(r['entity_id'] or '-')}</td>"
                    f"<td>{esc(r['details'] or '')}</td>"
                    "</tr>"
                )
            if not audit_rows:
                audit_rows = "<tr><td colspan='5' class='muted'>No audit entries yet.</td></tr>"
            rows = (
                "<div style='display:grid;gap:10px;'>"
                "<div class='notice'><b>2026-02-15:</b> Policy-layer permissions, invite lifecycle controls, and universal back-to-dashboard placement.</div>"
                "<div class='notice'><b>2026-02-15:</b> Tenant ledger with monthly statements, payment reconciliation, and downloadable CSV statement export.</div>"
                "<div class='notice'><b>2026-02-15:</b> Threaded messages with read state, notifications, and optional attachments.</div>"
                "<div class='notice'><b>2026-02-15:</b> Admin submission checklist workflow with request-changes + landlord resubmission flow.</div>"
                "<div class='notice'><b>2026-02-15:</b> Payment table filtering/pagination for tenant + manager and role-matrix regression testing.</div>"
                "<div class='notice'><b>2026-02-15:</b> DB ops tooling (`tools/db_ops.py`) plus seed reset helper (`tools/seed_reset.py`).</div>"
                "</div>"
                "<div class='card' style='margin-top:12px;'>"
                "<h3 style='margin-top:0;'>Recent Audit Trail</h3>"
                "<table class='table'><thead><tr><th>When</th><th>Role</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead><tbody>"
                f"{audit_rows}</tbody></table>"
                "<div style='margin-top:10px;'><a class='ghost-btn' href='/admin/audit'>Open full audit log</a></div>"
                "</div>"
            )
            return send_html(self,render_page("changelog.html","Changelog",u2,path,changelog_rows=rows))
        if path=="/login":
            if u:return redir(self,role_home(u["role"]))
            return send_html(self,render_page("login.html","Log in",u,path,error_box=""))
        if path=="/register":
            if u:return redir(self,role_home(u["role"]))
            return send_html(self,render_page("register.html","Register",u,path,message_box=""))
        if path=="/forgot":
            if u:return redir(self,role_home(u["role"]))
            return send_html(self,render_page("forgot_password.html","Reset password",u,path,message_box=""))
        if path=="/reset":
            if u:return redir(self,role_home(u["role"]))
            tok=(q.get("token")or[""])[0]
            return send_html(self,render_page("reset_password.html","Choose new password",u,path,token_value=esc(tok),message_box=""))
        if path=="/favorites":
            if not u:return redir(self,"/login")
            return self._favorites_get(u)
        if path=="/messages":
            if not u:return redir(self,"/login")
            return self._messages_get(u)
        if path=="/notifications":
            if not u:return redir(self,"/login")
            return self._notifications_get(u)
        if path=="/notifications/preferences":
            if not u:return redir(self,"/login")
            return self._notifications_preferences_get(u)
        if path=="/onboarding":
            if not u:return redir(self,"/login")
            return self._onboarding_get(u)
        if path=="/profile":
            if not u:return redir(self,"/login")
            return self._profile_get(u)
        if path=="/search":
            if not u:return redir(self,"/login")
            return self._global_search_get(u, q)
        if path=="/admin":
            if not u or u["role"]!="admin":return redir(self,"/login")
            return self._admin_get(u)
        
        if path=="/admin/submissions":
            if not u or u["role"]!="admin":return redir(self,"/login")
            return self._admin_submissions_get(u)
        if path=="/admin/permissions":
            if not u or u["role"]!="admin":return redir(self,"/login")
            return self._admin_permissions_get(u)
        if path=="/admin/audit":
            if not u or u["role"]!="admin":return redir(self,"/login")
            return self._admin_audit_get(u)
        if path=="/admin/audit/export":
            if not u or u["role"]!="admin":return redir(self,"/login")
            return self._admin_audit_export(u)
        if path=="/admin/users":
            if not u or u["role"]!="admin":return redir(self,"/login")
            return self._admin_users_get(u)
        if path=="/landlord/export/properties":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._landlord_export_properties(u)
        if path=="/landlord/export/property_units":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._landlord_export_property_units(u, q)
        if path=="/landlord/export/listing_requests":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._landlord_export_listing_requests(u)
        if path=="/manager/inquiries":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._manager_inquiries_get(u)
        if path=="/manager/applications":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._manager_applications_get(u)
        if path=="/manager/inquiries/export":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._manager_inquiries_export(u)
        if path=="/manager/applications/export":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._manager_applications_export(u)
        if path=="/manager/payments/export":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._manager_payments_export(u)
        if path=="/manager/listing-requests/export":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._manager_listing_requests_export(u)
        if path=="/manager/export/properties":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._manager_export_properties(u)
        if path=="/landlord/export/checks":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._landlord_export_checks(u)
        if path=="/landlord/export/listing_requests_filtered":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._landlord_export_listing_requests(u, filtered=True)
        if path=="/property-manager":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._property_manager_get(path, u, q)
        if path=="/property-manager/search":
            if not (u and user_has_role(u, "property_manager", "admin")):return redir(self,"/login")
            return self._property_manager_get(path, u, q)
        if path=="/compare":
            return self._compare_get(q, u)
        if path=="/listings":
            c=db();locs=[r["location"]for r in c.execute("SELECT DISTINCT location FROM listings ORDER BY location").fetchall()];c.close()
            opts="".join(f'<option value="{esc(l)}">{esc(l)}</option>'for l in locs)
            save_search_button=""
            if u:
                save_search_button=(
                    '<form method="POST" action="/search/save" id="saveSearchForm" style="display:flex;gap:8px;align-items:flex-end;">'
                    '<input type="hidden" id="saveSearchMaxPrice" name="maxPrice">'
                    '<input type="hidden" id="saveSearchLocation" name="location">'
                    '<input type="hidden" id="saveSearchBeds" name="beds">'
                    '<input type="hidden" id="saveSearchCategory" name="category">'
                    '<input name="name" placeholder="Saved search name" style="max-width:180px;">'
                    '<button class="ghost-btn" type="submit">Save Search</button>'
                    '</form>'
                )
            return send_html(self,render("listings.html",title="Listings",nav_right=nav(u,path),nav_menu=nav_menu(u,path),location_options=opts,save_search_button=save_search_button,scripts='<script src="/static/js/listings.js"></script>'))
        m=re.match(r"^/listing/(\d+)$",path)
        if m:
            c=db()
            lid=int(m.group(1))
            if u and normalize_role(u.get("role")) in ("property_manager","admin"):
                r=c.execute("SELECT * FROM listings WHERE id=?",(lid,)).fetchone()
            else:
                r=c.execute("SELECT * FROM listings WHERE id=? AND is_approved=1 AND is_available=1",(lid,)).fetchone()
            c.close()
            if not r:return e404(self)
            fav_btn = ''
            pre_name = u["full_name"] if u else ''
            pre_email = u["email"] if u else ''
            pre_phone = u["phone"] if u else ''
            if u:
                c2=db()
                isfav = c2.execute("SELECT 1 FROM favorites WHERE user_id=? AND listing_id=?",(u["id"],r["id"])).fetchone()
                c2.close()
                if isfav:
                    fav_btn = f'''<form method="POST" action="/favorite" style="margin:0;">
                      <input type="hidden" name="listing_id" value="{r["id"]}">
                      <input type="hidden" name="action" value="remove">
                      <button class="btn ghost" type="submit">â˜… Favorited</button>
                    </form>'''
                else:
                    fav_btn = f'''<form method="POST" action="/favorite" style="margin:0;">
                      <input type="hidden" name="listing_id" value="{r["id"]}">
                      <button class="btn" type="submit">â˜† Favorite</button>
                    </form>'''
            else:
                fav_btn = '<a class="btn" href="/login">Log in to favorite</a>'
            photos_html = ''
            c3=db()
            photos = listing_photos(c3, r["id"])
            c3.close()
            if photos:
                main = esc(r["image_url"] or photos[0]["path"])
                thumbs = ''.join(f'<a class="thumb" href="{esc(p["path"])}" target="_blank" title="Open image"><img src="{esc(p["path"])}" alt=""></a>' for p in photos[:12])
                photos_html = f'<div class="gallery"><img class="main" src="{main}" alt=""><div class="thumbs">{thumbs}</div></div>'
            else:
                photos_html = f'<div class="gallery"><img class="main" src="{esc(r["image_url"])}" alt=""></div>'
            return send_html(self,render(
                "listing_detail.html",
                title=r["title"],
                nav_right=nav(u,path),nav_menu=nav_menu(u,path),
                listing_id=str(r["id"]),
                share_url=self._absolute_url(f"/listing/{r['id']}"),
                favorite_button=fav_btn,
                gallery_html=photos_html,
                prefill_name=esc(pre_name),
                prefill_email=esc(pre_email),
                prefill_phone=esc(pre_phone),
                listing_title=esc(r["title"]),
                listing_price=f"{r['price']:,}",
                listing_location=esc(r["location"]),
                listing_beds=str(r["beds"]),
                listing_baths=str(r["baths"]),
                listing_category=esc(r["category"]),
                listing_image_url=esc(r["image_url"]),
                listing_description=esc(r["description"])
            ))

        if path.startswith("/tenant"):return self._tenant_get(path,u)
        if path.startswith("/landlord"):return self._landlord_get(path,u)
        if path.startswith("/manager"):return self._manager_get(path,u)
        if path.startswith("/property-manager"):return self._property_manager_get(path,u,q)
        return e404(self)

    def _post(self):
        if self._https_redirect_if_needed():
            return
        run_housekeeping_if_due()
        path=urlparse(self.path).path;u=cur_user(self.headers)
        ln=int(self.headers.get("Content-Length","0")or"0")
        if ln < 0 or ln > MAX_REQUEST_BYTES:
            return e400(self, f"Request payload is too large (max {MAX_REQUEST_BYTES // (1024 * 1024)} MB).")
        ctype_raw=(self.headers.get("Content-Type") or "")
        ctype=ctype_raw.lower()
        body_bytes=self.rfile.read(ln)
        files={}
        if ctype.startswith("multipart/form-data"):
            m = re.search(r'boundary="?([^";]+)"?', ctype_raw, flags=re.IGNORECASE)
            if m:
                boundary=m.group(1).encode("utf-8","replace")
                mp=parse_multipart(body_bytes, boundary)
                f=mp["fields"];files=mp["files"]
            else:
                f={}
        else:
            raw=body_bytes.decode("utf-8",errors="replace")
            f={k:v[0]for k,v in parse_qs(raw,keep_blank_values=True).items()}
        self._files = files
        if not same_origin_ok(self.headers):
            return e403(self)
        # CSRF check for authenticated POST endpoints (double-submit cookie).
        # Exempt auth bootstrap endpoints.
        if u and path not in CSRF_EXEMPT_PATHS:
            if not csrf_ok(self.headers, f):
                return e400(self, "Security token missing or invalid. Refresh the page and try again.")
        blocked, retry_in = route_rate_limit(path, self.headers, u, f)
        if blocked:
            return e429(self, f"Too many requests for this action. Try again in about {max(1, retry_in)} second(s).")

        if path=="/login":return self._login(f,u)
        if path=="/register":return self._register(f,u)
        
        if path=="/admin/submissions/approve":
            if not u or u.get("role")!="admin":return redir(self,"/login")
            return self._admin_submissions_approve(u,f)
        if path=="/admin/submissions/review":
            if not u or u.get("role")!="admin":return redir(self,"/login")
            return self._admin_submissions_review(u,f)
        if path=="/admin/submissions/reject":
            if not u or u.get("role")!="admin":return redir(self,"/login")
            return self._admin_submissions_reject(u,f)
        if path=="/admin/submissions/approve_all":
            if not u or u.get("role")!="admin":return redir(self,"/login")
            return self._admin_submissions_approve_all(u,f)
        if path=="/admin/permissions/update":
            if not u or u.get("role")!="admin":return redir(self,"/login")
            return self._admin_permissions_update(u,f)
        if path=="/admin/users/role":
            if not u or u.get("role")!="admin":return redir(self,"/login")
            return self._admin_users_role_update(u,f)
        if path=="/admin/users/unlock":
            if not u or u.get("role")!="admin":return redir(self,"/login")
            return self._admin_users_unlock(u,f)

        if path=="/logout":return self._logout(u)
        if path=="/forgot":return self._forgot(f,u)
        if path=="/reset":return self._reset(f,u)
        if path=="/profile/update":return self._profile_update(f,u)
        if path=="/messages/new":
            if not u:return redir(self,"/login")
            return self._messages_new(f,u)
        if path=="/messages/send":
            if not u:return redir(self,"/login")
            return self._messages_send(f,u)
        if path=="/favorite":return self._favorite_toggle(f,u)
        if path=="/inquiry":return self._inquiry_submit(f,u)
        if path=="/apply":return self._application_submit(f,u)
        if path=="/search/save":return self._save_search(f,u)
        if path=="/notifications/readall":return self._notifications_readall(f,u)
        if path=="/notifications/preferences":return self._notifications_preferences_post(f,u)
        if path=="/onboarding/step":return self._onboarding_step_post(f,u)
        if path=="/manager/inquiries/update":return self._manager_inquiries_update(f,u)
        if path=="/manager/applications/update":return self._manager_applications_update(f,u)
        if path.startswith("/tenant"):return self._tenant_post(path,u,f)
        if path.startswith("/landlord"):return self._landlord_post(path,u,f)
        if path.startswith("/manager"):return self._manager_post(path,u,f)
        if path.startswith("/property-manager"):return self._property_manager_post(path,u,f)
        return e404(self)

    def _static(self,path):
        rel=path[len("/static/"):].lstrip("/")
        if".."in rel:return e404(self)
        fp=STATIC_DIR/rel
        if not fp.exists()or not fp.is_file():return e404(self)
        ext=fp.suffix.lower()
        ct={".css":"text/css; charset=utf-8",".js":"application/javascript; charset=utf-8",".svg":"image/svg+xml",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",".avif":"image/avif"}
        ctype=ct.get(ext,"application/octet-stream")
        data=fp.read_bytes()
        max_age = "86400" if ext in (".css",".js") else "2592000"
        self.send_response(200)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control",f"public,max-age={max_age}")
        add_security_headers(self)
        self.end_headers()
        self.wfile.write(data)

    # â”€â”€ Auth â”€â”€
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
        c=db();r=c.execute("SELECT * FROM users WHERE username=?",(un,)).fetchone()
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
            db_write_retry(lambda c: c.execute("DELETE FROM sessions WHERE session_id=?",(raw,)))

        secure = "; Secure" if cookie_secure(self.headers) else ""
        return redir(self,"/",cookies=[
            f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}",
            f"{CSRF_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax{secure}",
        ])

    # â”€â”€ API â”€â”€
    

    def _uploads(self, path):
        rel = path[len("/uploads/"):].lstrip("/")
        if ".." in rel or "\x00" in rel:
            return e404(self)
        fp = (UPLOAD_DIR / rel).resolve()
        base = UPLOAD_DIR.resolve()
        if fp != base and base not in fp.parents:
            return e404(self)
        if not fp.exists() or not fp.is_file():
            return e404(self)
        ext = fp.suffix.lower()
        ct = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp",".pdf":"application/pdf",".txt":"text/plain; charset=utf-8",".csv":"text/csv; charset=utf-8"}
        ctype = ct.get(ext, "application/octet-stream")
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Download-Options", "noopen")
        self.send_header("Cache-Control", "private, max-age=300")
        add_security_headers(self)
        self.end_headers()
        self.wfile.write(data)
        return

    def _api_listings(self,q):
        mp=int(q["maxPrice"][0])if"maxPrice"in q and q["maxPrice"][0].isdigit()else None
        loc=q["location"][0]if"location"in q and q["location"][0]else None
        beds=int(q["beds"][0])if"beds"in q and q["beds"][0].isdigit()else None
        cat=q["category"][0]if"category"in q and q["category"][0]else None
        c=db();sql="SELECT * FROM listings WHERE is_approved=1 AND is_available=1";args=[]
        if mp is not None:sql+=" AND price<=?";args.append(mp)
        if loc:sql+=" AND location=?";args.append(loc)
        if beds is not None:sql+=" AND beds>=?";args.append(beds)
        if cat:sql+=" AND category=?";args.append(cat)
        rows=[dict(r)for r in c.execute(sql+" ORDER BY created_at DESC",args).fetchall()];c.close()
        return send_json(self,{"ok":True,"listings":rows})

    def _api_units(self,q,u):
        if not u:
            return send_json(self,{"ok":False},403)
        pid=q["property_id"][0]if"property_id"in q else""
        c=db()
        if normalize_role(u["role"]) == "property_manager":
            own = c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?",(pid, u["account_number"])).fetchone()
            if not own:
                c.close()
                return send_json(self,{"ok":False},403)
        elif normalize_role(u["role"]) != "admin":
            c.close()
            return send_json(self,{"ok":False},403)
        rows=[dict(r)for r in c.execute("SELECT unit_label,is_occupied FROM units WHERE property_id=? ORDER BY id",(pid,)).fetchall()]
        c.close()
        return send_json(self,{"ok":True,"units":rows})

    
    def _favorites_get(self, u):
        c=db()
        rows=c.execute(
            "SELECT l.* FROM favorites f JOIN listings l ON l.id=f.listing_id "
            "WHERE f.user_id=? ORDER BY f.created_at DESC",
            (u["id"],)
        ).fetchall()
        cards=""
        for r in rows:
            cards += f'''
            <div class="card listing-card">
              <div class="listing-thumb"><img class="thumb-img" src="{esc(r["image_url"])}" alt=""></div>
              <div class="listing-meta">
                <div class="listing-title">{esc(r["title"])}</div>
                <div class="listing-sub">${r["price"]:,} â€¢ {esc(r["location"])} â€¢ {r["beds"]} bd â€¢ {r["baths"]} ba</div>
                <div class="listing-actions">
                  <a class="btn" href="/listing/{r["id"]}">Open</a>
                  <form method="POST" action="/favorite" style="display:inline;">
                    <input type="hidden" name="listing_id" value="{r["id"]}">
                    <input type="hidden" name="action" value="remove">
                    <button class="btn ghost" type="submit">Remove</button>
                  </form>
                </div>
              </div>
            </div>'''
        c.close()
        if not cards:
            cards = '<div class="notice">No favorites yet. Browse <a href="/listings">Listings</a> and tap â€œFavoriteâ€.</div>'
        return send_html(self,render("favorites.html",title="Favorites",nav_right=nav(u,"/favorites"),nav_menu=nav_menu(u,"/favorites"),favorites_html=cards))

    def _messages_get(self, u):
        q = parse_qs(urlparse(self.path).query)
        thread_id = to_int((q.get("thread") or ["0"])[0], 0)
        msg = (q.get("msg") or [""])[0].strip()
        err = (q.get("err") or ["0"])[0] == "1"
        message_box = ""
        if msg:
            klass = "notice err" if err else "notice"
            message_box = f'<div class="{klass}" style="margin:10px 0;">{esc(msg)}</div>'

        c = db()
        threads = message_thread_summary_for_user(c, u["id"], limit=200)
        if thread_id <= 0 and threads:
            thread_id = to_int(threads[0]["id"], 0)

        threads_rows = ""
        for t in threads:
            tid = to_int(t["id"], 0)
            active = " is-active" if tid == thread_id else ""
            unread = to_int(t["unread_count"], 0)
            unread_badge = f"<span class='badge no'>{unread} new</span>" if unread > 0 else ""
            ctx = ""
            ctx_type = (t["context_type"] or "").strip()
            ctx_id = (t["context_id"] or "").strip()
            if ctx_type and ctx_id:
                ctx = f"<div class='muted'>{esc(ctx_type)}: {esc(ctx_id)}</div>"
            last_sender = esc(t["last_sender"] or "System")
            last_body = esc((t["last_body"] or "").strip())
            last_when = esc(t["last_post_at"] or t["created_at"] or "")
            threads_rows += (
                f"<a class='prop-item{active}' href='/messages?thread={tid}' style='text-decoration:none;margin-bottom:8px;'>"
                "<div class='thumb' style='width:52px;height:52px;'></div>"
                "<div>"
                f"<div><b>{esc(t['subject'])}</b></div>"
                f"{ctx}"
                f"<div class='muted'>{last_sender}: {last_body[:110] or '-'}</div>"
                f"<div class='muted'>{last_when}</div>"
                "</div>"
                f"<div style='display:flex;align-items:center;'>{unread_badge}</div>"
                "</a>"
            )
        threads_empty = "" if threads_rows else "<div class='notice'>No threads yet. Start one from the form.</div>"

        thread_view = "<div class='card' style='margin-top:12px;'><div class='notice'>Select a thread to read and reply.</div></div>"
        if thread_id > 0 and user_in_message_thread(c, u["id"], thread_id):
            t = c.execute("SELECT * FROM message_threads WHERE id=?", (thread_id,)).fetchone()
            if t:
                mark_message_thread_read(c, u["id"], thread_id)
                posts = c.execute(
                    "SELECT p.*,uu.full_name AS sender_name,uu.account_number AS sender_account "
                    "FROM message_posts p JOIN users uu ON uu.id=p.sender_user_id "
                    "WHERE p.thread_id=? ORDER BY p.id ASC LIMIT 400",
                    (thread_id,),
                ).fetchall()
                post_rows = ""
                for p in posts:
                    attach = ""
                    if (p["attachment_path"] or "").strip():
                        aname = esc(p["attachment_name"] or "attachment")
                        attach = (
                            "<div style='margin-top:6px;'>"
                            f"<a class='ghost-btn' href='{esc(p['attachment_path'])}' target='_blank' rel='noopener'>Attachment: {aname}</a>"
                            "</div>"
                        )
                    post_rows += (
                        "<div class='card' style='margin-bottom:10px;'>"
                        f"<div><b>{esc(p['sender_name'] or p['sender_account'] or 'User')}</b>"
                        f"<span class='muted'> ({esc(p['sender_account'] or '-')})</span></div>"
                        f"<div class='muted'>{esc(p['created_at'])}</div>"
                        f"<div style='margin-top:8px;white-space:pre-wrap;'>{esc(p['body'])}</div>"
                        f"{attach}"
                        "</div>"
                    )
                if not post_rows:
                    post_rows = "<div class='notice'>No messages in this thread yet.</div>"
                ctx = ""
                if (t["context_type"] or "").strip() and (t["context_id"] or "").strip():
                    ctx = f"<div class='muted' style='margin-top:4px;'>Context: {esc(t['context_type'])} / {esc(t['context_id'])}</div>"
                thread_view = (
                    "<div class='card' style='margin-top:12px;'>"
                    f"<h3 style='margin-top:0;'>{esc(t['subject'])}</h3>"
                    f"{ctx}"
                    "<div style='margin-top:10px;'>"
                    f"{post_rows}"
                    "</div>"
                    "<form method='POST' action='/messages/send' enctype='multipart/form-data' style='margin-top:12px;'>"
                    f"<input type='hidden' name='thread_id' value='{thread_id}'>"
                    "<div class='field'><label>Reply</label><textarea name='body' required placeholder='Type reply...'></textarea></div>"
                    "<div class='field'><label>Attachment (optional)</label><input type='file' name='attachment' accept='.pdf,.jpg,.jpeg,.png,.webp,.txt'></div>"
                    "<button class='primary-btn' type='submit'>Send Reply</button>"
                    "</form>"
                    "</div>"
                )
        c.commit()
        c.close()

        return send_html(
            self,
            render(
                "messages.html",
                title="Messages",
                nav_right=nav(u, "/messages"),
                nav_menu=nav_menu(u, "/messages"),
                message_box=message_box,
                threads_rows=threads_rows,
                threads_empty=threads_empty,
                thread_view=thread_view,
            ),
        )

    def _messages_new(self, f, u):
        recipient = (f.get("recipient") or "").strip()
        subject = (f.get("subject") or "").strip()
        body = (f.get("body") or "").strip()
        context_type = (f.get("context_type") or "").strip()
        context_id = (f.get("context_id") or "").strip()
        up = None
        files = getattr(self, "_files", {}) or {}
        if "attachment" in files:
            up = files.get("attachment")
            if isinstance(up, list):
                up = up[0] if up else None
        c = db()
        ok, note, tid = create_message_thread(c, u, recipient, subject, body, context_type=context_type, context_id=context_id, attachment=up)
        if ok:
            c.commit()
            c.close()
            return redir(self, with_msg(f"/messages?thread={tid}", note))
        c.close()
        return redir(self, with_msg("/messages", note, True))

    def _messages_send(self, f, u):
        thread_id = to_int(f.get("thread_id"), 0)
        body = (f.get("body") or "").strip()
        up = None
        files = getattr(self, "_files", {}) or {}
        if "attachment" in files:
            up = files.get("attachment")
            if isinstance(up, list):
                up = up[0] if up else None
        c = db()
        ok, note = send_message_reply(c, u, thread_id, body, attachment=up)
        if ok:
            c.commit()
            c.close()
            return redir(self, with_msg(f"/messages?thread={thread_id}", note))
        c.close()
        return redir(self, with_msg(f"/messages?thread={thread_id}", note, True))

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
                f"<div class='muted'>From: {esc(r['sender_name'] or 'Atlas')} - Sent: {esc(r['created_at'])}</div>"
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

    def _landlord_tenants_get(self, u):
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
        props = c.execute(
            "SELECT id,name FROM properties WHERE owner_account=? ORDER BY created_at DESC",
            (u["account_number"],),
        ).fetchall()
        active = c.execute(
            "SELECT l.id,l.tenant_account,l.property_id,l.unit_label,l.start_date,uu.full_name AS tenant_name,p.name AS property_name "
            "FROM tenant_leases l "
            "JOIN properties p ON p.id=l.property_id "
            "LEFT JOIN users uu ON uu.account_number=l.tenant_account "
            "WHERE l.is_active=1 AND p.owner_account=? "
            "ORDER BY l.created_at DESC,l.id DESC",
            (u["account_number"],),
        ).fetchall()
        invites_sql = (
            "SELECT i.*, tu.full_name AS tenant_name,p.name AS property_name "
            "FROM tenant_property_invites i "
            "LEFT JOIN users tu ON tu.id=i.tenant_user_id "
            "LEFT JOIN properties p ON p.id=i.property_id "
            "WHERE (p.owner_account=? OR i.sender_user_id=?) "
        )
        invites_args = [u["account_number"], u["id"]]
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
        active_rows = "".join(
            "<tr>"
            f"<td>{esc(r['tenant_name'] or '-')}</td>"
            f"<td>{esc(r['tenant_account'])}</td>"
            f"<td>{esc(r['property_name'] or r['property_id'])}</td>"
            f"<td>{esc(r['unit_label'])}</td>"
            f"<td>{esc(r['start_date'])}</td>"
            "<td>"
            "<form method='POST' action='/landlord/leases/end' style='margin:0;'>"
            f"<input type='hidden' name='lease_id' value='{r['id']}'>"
            "<button class='ghost-btn' type='submit'>Remove</button>"
            "</form>"
            "</td>"
            "</tr>"
            for r in active
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
                    "<form method='POST' action='/landlord/tenant/invite/cancel' style='margin:0;'>"
                    f"<input type='hidden' name='invite_id' value='{r['id']}'>"
                    "<button class='ghost-btn' type='submit'>Cancel</button>"
                    "</form>"
                )
            elif st in ("declined", "cancelled"):
                action_html = (
                    "<form method='POST' action='/landlord/tenant/invite/resend' style='margin:0;'>"
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
        invite_empty += pager_html("/landlord/tenants", q, page, per, invites_count)

        return send_html(
            self,
            render(
                "landlord_tenants.html",
                title="Tenant Sync",
                nav_right=nav(u, "/landlord/tenants"),
                nav_menu=nav_menu(u, "/landlord/tenants"),
                message_box=message_box,
                property_options=property_options,
                active_rows=active_rows,
                active_empty=active_empty,
                invite_rows=invite_rows,
                invite_empty=invite_empty,
                scripts=(
                    '<script>(function(){'
                    'function load(){var p=document.getElementById("landlordTenantPropertySelect");var u=document.getElementById("landlordTenantUnitSelect");'
                    'if(!p||!u)return;var pid=p.value||"";u.innerHTML=\'<option value="">Select...</option>\';if(!pid)return;'
                    'fetch("/api/units?property_id="+encodeURIComponent(pid)).then(function(r){return r.json();}).then(function(d){if(!d.ok)return;'
                    'd.units.forEach(function(x){var o=document.createElement("option");o.value=x.unit_label;o.textContent=x.unit_label+(x.is_occupied?" (occupied)":"");o.disabled=!!x.is_occupied;u.appendChild(o);});'
                    '});}'
                    'document.addEventListener("DOMContentLoaded",function(){var p=document.getElementById("landlordTenantPropertySelect");if(p)p.addEventListener("change",load);load();});'
                    '})();</script>'
                ),
            ),
        )

    def _landlord_tenant_invite(self, f, u):
        tenant_ident = (f.get("tenant_ident") or "").strip()
        pid = (f.get("property_id") or "").strip()
        unit_label = (f.get("unit_label") or "").strip()
        message = (f.get("message") or "").strip()
        c = db()
        ok, note = create_tenant_property_invite(
            c,
            u,
            tenant_ident,
            pid,
            unit_label,
            message=message,
            owner_account=u["account_number"],
        )
        if ok:
            c.commit()
        c.close()
        return redir(self, with_msg("/landlord/tenants", note, err=(not ok)))

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
                scripts=(
                    '<script>(function(){'
                    'function load(){var p=document.getElementById("managerTenantPropertySelect");var u=document.getElementById("managerTenantUnitSelect");'
                    'if(!p||!u)return;var pid=p.value||"";u.innerHTML=\'<option value="">Select...</option>\';if(!pid)return;'
                    'fetch("/api/units?property_id="+encodeURIComponent(pid)).then(function(r){return r.json();}).then(function(d){if(!d.ok)return;'
                    'd.units.forEach(function(x){var o=document.createElement("option");o.value=x.unit_label;o.textContent=x.unit_label+(x.is_occupied?" (occupied)":"");o.disabled=!!x.is_occupied;u.appendChild(o);});'
                    '});}'
                    'document.addEventListener("DOMContentLoaded",function(){var p=document.getElementById("managerTenantPropertySelect");if(p)p.addEventListener("change",load);load();});'
                    '})();</script>'
                ),
            ),
        )

    def _manager_tenant_invite(self, f, u):
        tenant_ident = (f.get("tenant_ident") or "").strip()
        pid = (f.get("property_id") or "").strip()
        unit_label = (f.get("unit_label") or "").strip()
        message = (f.get("message") or "").strip()
        c = db()
        ok, note = create_tenant_property_invite(
            c,
            u,
            tenant_ident,
            pid,
            unit_label,
            message=message,
            owner_account=u["account_number"],
        )
        if ok:
            c.commit()
        c.close()
        return redir(self, with_msg("/manager/tenants", note, err=(not ok)))

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

    def _notifications_get(self, u):
        c=db()
        rows=c.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
            (u["id"],)
        ).fetchall()
        items=""
        for r in rows:
            cls="notif unread" if not r["is_read"] else "notif"
            link=(r["link"] or "").strip()
            if link:
                items += f'<div class="{cls}"><a href="{esc(link)}">{esc(r["text"])}</a><span class="muted">{esc(r["created_at"])}</span></div>'
            else:
                items += f'<div class="{cls}">{esc(r["text"])}<span class="muted">{esc(r["created_at"])}</span></div>'
        c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?",(u["id"],))
        c.commit();c.close()
        if not items:
            items = '<div class="notice">No alerts yet.</div>'
        return send_html(self,render("notifications.html",title="Alerts",nav_right=nav(u,"/notifications"),nav_menu=nav_menu(u,"/notifications"),notifications_html=items))

    def _notifications_readall(self, f, u):
        if not u:return send_json(self,{"ok":False},401)
        db_write_retry(lambda c: c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?",(u["id"],)))
        return send_json(self,{"ok":True})

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

    def _favorite_toggle(self, f, u):
        if not u:return redir(self,"/login")
        lid=to_int(f.get("listing_id"), 0)
        if lid <= 0:return redir(self, self.headers.get("Referer") or "/favorites")
        action=(f.get("action") or "toggle").strip().lower()
        def _work(c):
            if action in ("remove","off"):
                c.execute("DELETE FROM favorites WHERE user_id=? AND listing_id=?",(u["id"],lid))
            else:
                c.execute("INSERT OR IGNORE INTO favorites(user_id,listing_id)VALUES(?,?)",(u["id"],lid))
        db_write_retry(_work)
        ref=self.headers.get("Referer") or (f"/listing/{lid}" if lid else "/favorites")
        return redir(self, ref)

    def _save_search(self, f, u):
        if not u:
            return redir(self, "/login")
        payload = {
            "maxPrice": (f.get("maxPrice") or "").strip(),
            "location": (f.get("location") or "").strip(),
            "beds": (f.get("beds") or "").strip(),
            "category": (f.get("category") or "").strip(),
        }
        name = (f.get("name") or "").strip()[:80]
        c = db()
        c.execute(
            "INSERT INTO saved_searches(user_id,name,query_json)VALUES(?,?,?)",
            (u["id"], name or "Saved Search", json.dumps(payload)),
        )
        create_notification(c, u["id"], "Search saved. You can revisit it from alerts.", "/notifications")
        audit_log(c, u, "saved_search_created", "saved_searches", c.execute("SELECT last_insert_rowid()").fetchone()[0], json.dumps(payload))
        c.commit()
        c.close()
        return redir(self, "/listings")

    def _compare_get(self, q, u):
        raw = (q.get("ids") or [""])[0]
        ids = []
        for part in raw.split(","):
            n = to_int(part, 0)
            if n > 0 and n not in ids:
                ids.append(n)
            if len(ids) >= 3:
                break
        if not ids:
            return send_html(self, render("compare.html", title="Compare Listings", nav_right=nav(u, "/compare"), nav_menu=nav_menu(u, "/compare"), compare_rows="", empty='<div class="notice">No listings selected for comparison.</div>'))
        c = db()
        marks = ",".join(["?"] * len(ids))
        rows = c.execute(f"SELECT * FROM listings WHERE id IN ({marks}) ORDER BY id DESC", ids).fetchall()
        c.close()
        tr = ""
        for r in rows:
            tr += (
                "<tr>"
                f"<td>{esc(r['title'])}</td>"
                f"<td>${int(r['price']):,}</td>"
                f"<td>{esc(r['location'])}</td>"
                f"<td>{esc(r['beds'])}</td>"
                f"<td>{esc(r['baths'])}</td>"
                f"<td>{esc(r['category'])}</td>"
                f"<td><a class='ghost-btn' href='/listing/{r['id']}'>Open</a></td>"
                "</tr>"
            )
        return send_html(self, render("compare.html", title="Compare Listings", nav_right=nav(u, "/compare"), nav_menu=nav_menu(u, "/compare"), compare_rows=tr, empty=""))

    def _global_search_get(self, u, q):
        if not u:
            return redir(self, "/login")
        role = normalize_role(u.get("role"))
        qtxt = ((q.get("q") or [""])[0]).strip().lower()
        if not qtxt:
            return send_html(
                self,
                render(
                    "search_results.html",
                    title="Search",
                    nav_right=nav(u, "/search"),
                    nav_menu=nav_menu(u, "/search"),
                    message_box="",
                    search_query="(empty)",
                    search_back_path=role_home(role),
                    search_sections=empty_state("*", "Search Atlas", "Enter a keyword to search records.", "Go to Dashboard", role_home(role)),
                ),
            )
        s = "%" + qtxt + "%"
        c = db()
        try:
            sections = []
            if role == "tenant":
                pays = c.execute(
                    "SELECT id,amount,payment_type,status,created_at FROM payments "
                    "WHERE payer_account=? AND (CAST(id AS TEXT) LIKE ? OR LOWER(COALESCE(provider,'')) LIKE ? OR LOWER(COALESCE(payment_type,'')) LIKE ? OR LOWER(COALESCE(status,'')) LIKE ?) "
                    "ORDER BY id DESC LIMIT 20",
                    (u["account_number"], s, s, s, s),
                ).fetchall()
                maint = c.execute(
                    "SELECT id,status,urgency,description,created_at FROM maintenance_requests "
                    "WHERE tenant_account=? AND (CAST(id AS TEXT) LIKE ? OR LOWER(COALESCE(description,'')) LIKE ? OR LOWER(COALESCE(status,'')) LIKE ?) "
                    "ORDER BY id DESC LIMIT 20",
                    (u["account_number"], s, s, s),
                ).fetchall()
                alerts = c.execute(
                    "SELECT id,text,link,is_read,created_at FROM notifications "
                    "WHERE user_id=? AND LOWER(COALESCE(text,'')) LIKE ? ORDER BY id DESC LIMIT 20",
                    (u["id"], s),
                ).fetchall()
                pay_rows = "".join(
                    f"<tr><td>#{r['id']}</td><td>{esc(r['created_at'])}</td><td>{esc(r['payment_type'])}</td><td>${to_int(r['amount'],0):,}</td><td>{status_badge(r['status'],'payment')}</td><td><a class='ghost-btn' href='/tenant/payment/receipt?id={r['id']}'>Open</a></td></tr>"
                    for r in pays
                )
                maint_rows = "".join(
                    f"<tr><td>#{r['id']}</td><td>{esc(r['created_at'])}</td><td>{status_badge(r['urgency'],'priority')}</td><td>{status_badge(r['status'],'maintenance')}</td><td>{esc((r['description'] or '')[:120])}</td><td><a class='ghost-btn' href='/tenant/maintenance/{r['id']}'>Open</a></td></tr>"
                    for r in maint
                )
                alert_rows = ""
                for r in alerts:
                    read_badge = "<span class='badge'>unread</span>" if not to_int(r["is_read"], 0) else "<span class='badge ok'>read</span>"
                    link = (r["link"] or "").strip()
                    action = f"<a class='ghost-btn' href='{esc(link)}'>Open</a>" if link else "-"
                    alert_rows += f"<tr><td>{esc(r['created_at'])}</td><td>{esc(r['text'])}</td><td>{read_badge}</td><td>{action}</td></tr>"
                sections.append(
                    "<h3>Payments</h3>"
                    + (f"<table class='table'><thead><tr><th>ID</th><th>Date</th><th>Type</th><th>Amount</th><th>Status</th><th>Action</th></tr></thead><tbody>{pay_rows}</tbody></table>" if pay_rows else empty_state("$", "No Payment Matches", "No payment records matched your query."))
                )
                sections.append(
                    "<h3 style='margin-top:12px;'>Maintenance</h3>"
                    + (f"<table class='table'><thead><tr><th>ID</th><th>Date</th><th>Priority</th><th>Status</th><th>Description</th><th>Action</th></tr></thead><tbody>{maint_rows}</tbody></table>" if maint_rows else empty_state("!", "No Maintenance Matches", "No maintenance requests matched your query."))
                )
                sections.append(
                    "<h3 style='margin-top:12px;'>Alerts</h3>"
                    + (f"<table class='table'><thead><tr><th>Date</th><th>Alert</th><th>Read</th><th>Action</th></tr></thead><tbody>{alert_rows}</tbody></table>" if alert_rows else empty_state("i", "No Alert Matches", "No alerts matched your query."))
                )
            else:
                owner_scope = role != "admin"
                owner_account = (u.get("account_number") or "").strip()
                psql = "SELECT id,name,location FROM properties WHERE 1=1 "
                pargs = []
                if owner_scope:
                    psql += "AND owner_account=? "
                    pargs.append(owner_account)
                psql += "AND (LOWER(COALESCE(id,'')) LIKE ? OR LOWER(COALESCE(name,'')) LIKE ? OR LOWER(COALESCE(location,'')) LIKE ?) ORDER BY created_at DESC LIMIT 20"
                pargs.extend([s, s, s])
                properties = c.execute(psql, tuple(pargs)).fetchall()
                usql = (
                    "SELECT u.id,u.unit_label,u.rent,u.is_occupied,p.name AS property_name,p.id AS property_id "
                    "FROM units u JOIN properties p ON p.id=u.property_id WHERE 1=1 "
                )
                uargs = []
                if owner_scope:
                    usql += "AND p.owner_account=? "
                    uargs.append(owner_account)
                usql += "AND (LOWER(COALESCE(u.unit_label,'')) LIKE ? OR LOWER(COALESCE(p.name,'')) LIKE ? OR LOWER(COALESCE(p.id,'')) LIKE ?) ORDER BY u.id DESC LIMIT 20"
                uargs.extend([s, s, s])
                units = c.execute(usql, tuple(uargs)).fetchall()
                tenants = c.execute(
                    "SELECT DISTINCT u.account_number,u.full_name,u.email FROM users u "
                    "LEFT JOIN tenant_leases l ON l.tenant_account=u.account_number AND l.is_active=1 "
                    "LEFT JOIN properties p ON p.id=l.property_id "
                    "WHERE u.role='tenant' "
                    + ("AND p.owner_account=? " if owner_scope else "")
                    + "AND (LOWER(COALESCE(u.account_number,'')) LIKE ? OR LOWER(COALESCE(u.full_name,'')) LIKE ? OR LOWER(COALESCE(u.email,'')) LIKE ?) "
                    "ORDER BY u.id DESC LIMIT 20",
                    tuple(([owner_account] if owner_scope else []) + [s, s, s]),
                ).fetchall()
                maint = c.execute(
                    "SELECT m.id,m.status,m.urgency,m.tenant_account,m.description,m.created_at "
                    "FROM maintenance_requests m WHERE "
                    + (
                        "EXISTS(SELECT 1 FROM tenant_leases l JOIN properties p ON p.id=l.property_id WHERE l.tenant_account=m.tenant_account AND l.is_active=1 AND p.owner_account=?) AND "
                        if owner_scope else
                        "1=1 AND "
                    )
                    + "(CAST(m.id AS TEXT) LIKE ? OR LOWER(COALESCE(m.description,'')) LIKE ? OR LOWER(COALESCE(m.tenant_account,'')) LIKE ? OR LOWER(COALESCE(m.status,'')) LIKE ?) "
                    "ORDER BY m.id DESC LIMIT 20",
                    tuple(([owner_account] if owner_scope else []) + [s, s, s, s]),
                ).fetchall()
                pay = c.execute(
                    "SELECT p.id,p.payer_account,p.payment_type,p.amount,p.status,p.created_at FROM payments p WHERE "
                    + (
                        "EXISTS(SELECT 1 FROM tenant_leases l JOIN properties pp ON pp.id=l.property_id WHERE l.tenant_account=p.payer_account AND l.is_active=1 AND pp.owner_account=?) AND "
                        if owner_scope else
                        "1=1 AND "
                    )
                    + "(CAST(p.id AS TEXT) LIKE ? OR LOWER(COALESCE(p.payer_account,'')) LIKE ? OR LOWER(COALESCE(p.status,'')) LIKE ?) "
                    "ORDER BY p.id DESC LIMIT 20",
                    tuple(([owner_account] if owner_scope else []) + [s, s, s]),
                ).fetchall()
                props_rows = "".join(f"<tr><td>{esc(r['id'])}</td><td>{esc(r['name'])}</td><td>{esc(r['location'])}</td><td><a class='ghost-btn' href='/manager/properties'>Open</a></td></tr>" for r in properties)
                unit_rows = "".join(f"<tr><td>#{r['id']}</td><td>{esc(r['property_name'])}</td><td>{esc(r['unit_label'])}</td><td>${to_int(r['rent'],0):,}</td><td>{('<span class=\"badge ok\">occupied</span>' if to_int(r['is_occupied'],0) else '<span class=\"badge\">vacant</span>')}</td></tr>" for r in units)
                tenant_rows = "".join(f"<tr><td>{esc(r['account_number'])}</td><td>{esc(r['full_name'])}</td><td>{esc(r['email'])}</td><td><a class='ghost-btn' href='/manager/tenants'>Open</a></td></tr>" for r in tenants)
                maint_rows = "".join(f"<tr><td>#{r['id']}</td><td>{esc(r['tenant_account'])}</td><td>{status_badge(r['urgency'],'priority')}</td><td>{status_badge(r['status'],'maintenance')}</td><td>{esc((r['description'] or '')[:120])}</td><td><a class='ghost-btn' href='/manager/maintenance'>Open</a></td></tr>" for r in maint)
                pay_rows = "".join(f"<tr><td>#{r['id']}</td><td>{esc(r['payer_account'])}</td><td>{esc(r['payment_type'])}</td><td>${to_int(r['amount'],0):,}</td><td>{status_badge(r['status'],'payment')}</td><td><a class='ghost-btn' href='/manager/payments'>Open</a></td></tr>" for r in pay)
                sections.append("<h3>Properties</h3>" + (f"<table class='table'><thead><tr><th>ID</th><th>Name</th><th>Location</th><th>Action</th></tr></thead><tbody>{props_rows}</tbody></table>" if props_rows else empty_state("P", "No Property Matches", "No properties matched your query.")))
                sections.append("<h3 style='margin-top:12px;'>Units</h3>" + (f"<table class='table'><thead><tr><th>ID</th><th>Property</th><th>Unit</th><th>Rent</th><th>Occupancy</th></tr></thead><tbody>{unit_rows}</tbody></table>" if unit_rows else empty_state("U", "No Unit Matches", "No units matched your query.")))
                sections.append("<h3 style='margin-top:12px;'>Tenants</h3>" + (f"<table class='table'><thead><tr><th>Account</th><th>Name</th><th>Email</th><th>Action</th></tr></thead><tbody>{tenant_rows}</tbody></table>" if tenant_rows else empty_state("T", "No Tenant Matches", "No tenant records matched your query.")))
                sections.append("<h3 style='margin-top:12px;'>Maintenance</h3>" + (f"<table class='table'><thead><tr><th>ID</th><th>Tenant</th><th>Priority</th><th>Status</th><th>Description</th><th>Action</th></tr></thead><tbody>{maint_rows}</tbody></table>" if maint_rows else empty_state("M", "No Maintenance Matches", "No maintenance rows matched your query.")))
                sections.append("<h3 style='margin-top:12px;'>Payments</h3>" + (f"<table class='table'><thead><tr><th>ID</th><th>Payer</th><th>Type</th><th>Amount</th><th>Status</th><th>Action</th></tr></thead><tbody>{pay_rows}</tbody></table>" if pay_rows else empty_state("$", "No Payment Matches", "No payment rows matched your query.")))
        finally:
            c.close()
        return send_html(
            self,
            render(
                "search_results.html",
                title="Search Results",
                nav_right=nav(u, "/search"),
                nav_menu=nav_menu(u, "/search"),
                message_box=query_message_box(q),
                search_query=esc(qtxt),
                search_back_path=role_home(role),
                search_sections="".join(sections),
            ),
        )

    def _inquiry_submit(self, f, u):
        lid=to_int(f.get("listing_id"), 0) or None
        fn=(f.get("full_name") or (u["full_name"] if u else "") or "").strip()
        em=(f.get("email") or (u["email"] if u else "") or "").strip()
        ph=(f.get("phone") or (u["phone"] if u else "") or "").strip()
        subj=(f.get("subject") or "").strip()
        body=(f.get("body") or "").strip()
        if len(fn)<2 or "@" not in em or len(body)<8:
            return send_html(self,render("inquiry_thanks.html",title="Inquiry",nav_right=nav(u,"/listings"),nav_menu=nav_menu(u,"/listings"),
                                         message_box='<div class="notice err"><b>Error:</b> Please complete the form.</div>',back_to_listing=(f'<a class="btn ghost" href="/listing/{lid}">Back to Listing</a>' if lid else "")))
        c=db()
        c.execute("INSERT INTO inquiries(listing_id,full_name,email,phone,subject,body)VALUES(?,?,?,?,?,?)",(lid,fn,em,ph,subj,body))
        c.commit()
        for m in c.execute("SELECT id FROM users WHERE role='property_manager'").fetchall():
            create_notification(c,m["id"],f"New inquiry from {fn}", "/manager/inquiries")
        audit_log(c, u, "inquiry_submitted", "inquiries", c.execute("SELECT last_insert_rowid()").fetchone()[0], f"listing_id={lid}")
        c.commit();c.close()
        return send_html(self,render("inquiry_thanks.html",title="Inquiry received",nav_right=nav(u,"/listings"),nav_menu=nav_menu(u,"/listings"),
                                     message_box='<div class="notice"><b>Inquiry sent.</b> Your application form is separate and optional.</div>',back_to_listing=(f'<a class="btn ghost" href="/listing/{lid}">Back to Listing</a>' if lid else "")))

    def _application_submit(self, f, u):
        lid=to_int(f.get("listing_id"), 0)
        fn=(f.get("full_name") or (u["full_name"] if u else "") or "").strip()
        em=(f.get("email") or (u["email"] if u else "") or "").strip()
        ph=(f.get("phone") or (u["phone"] if u else "") or "").strip()
        income=(f.get("income") or "").strip()
        notes=(f.get("notes") or "").strip()
        if lid<=0 or len(fn)<2 or "@" not in em:
            return send_html(self,render("apply_thanks.html",title="Application",nav_right=nav(u,"/listings"),nav_menu=nav_menu(u,"/listings"),
                                         message_box='<div class="notice err"><b>Error:</b> Please complete the form.</div>',back_to_listing=(f'<a class="btn ghost" href="/listing/{lid}">Back to Listing</a>' if lid else "")))
        c=db()
        c.execute("INSERT INTO applications(listing_id,applicant_user_id,full_name,email,phone,income,notes)VALUES(?,?,?,?,?,?,?)",
                  (lid, u["id"] if u else None, fn, em, ph, income, notes))
        c.commit()
        for m in c.execute("SELECT id FROM users WHERE role='property_manager'").fetchall():
            create_notification(c,m["id"],f"New application: {fn}", "/manager/applications")
        audit_log(c, u, "application_submitted", "applications", c.execute("SELECT last_insert_rowid()").fetchone()[0], f"listing_id={lid}")
        c.commit();c.close()
        return send_html(self,render("apply_thanks.html",title="Application received",nav_right=nav(u,"/listings"),nav_menu=nav_menu(u,"/listings"),
                                     message_box='<div class="notice"><b>Application submitted.</b> Inquiries are handled separately.</div>',back_to_listing=(f'<a class="btn ghost" href="/listing/{lid}">Back to Listing</a>' if lid else "")))

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
                "A password reset was requested for your Atlas account.\n\n"
                f"Use this link to reset your password:\n{link}\n\n"
                f"This link expires at {exp} UTC.\n"
                "If you did not request this, you can ignore this message."
            )
            sent = send_email((user["email"] or "").strip(), "Atlas Password Reset", email_body)
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
        c.execute("DELETE FROM sessions WHERE user_id=?",(user["id"],))
        create_notification(c,user["id"],"Your password was changed successfully.", "/login")
        audit_log(c, {"id": user["id"], "role": user["role"]}, "password_reset_completed", "users", user["id"], "self_service")
        c.commit();c.close()
        return send_html(self,render("reset_password.html",title="Password updated",nav_right=nav(None),nav_menu=nav_menu(None),
                                     token_value=esc(tok),
                                     message_box='<div class="notice"><b>Done!</b> Your password has been updated. <a href="/login">Log in</a>.</div>'))

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
        return send_csv(self, "atlas_inquiries.csv", rows)

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
        return send_csv(self, "atlas_applications.csv", rows)


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

    def _landlord_export_properties(self, u):
        u = self._req_role(u, "landlord", action="landlord.property.manage")
        if not u:
            return
        c = db()
        rows_db = c.execute(
            "SELECT p.id,p.name,p.location,p.property_type,p.units_count,p.created_at,"
            "COALESCE(SUM(CASE WHEN u2.is_occupied=1 THEN 1 ELSE 0 END),0) AS occupied_units "
            "FROM properties p "
            "LEFT JOIN units u2 ON u2.property_id=p.id "
            "WHERE p.owner_account=? "
            "GROUP BY p.id,p.name,p.location,p.property_type,p.units_count,p.created_at "
            "ORDER BY p.created_at DESC,p.id DESC",
            (u["account_number"],),
        ).fetchall()
        c.close()
        rows = [["property_id", "name", "location", "property_type", "units_total", "occupied_units", "vacant_units", "created_at"]]
        for r in rows_db:
            total = to_int(r["units_count"], 0)
            occ = to_int(r["occupied_units"], 0)
            rows.append([r["id"], r["name"], r["location"], r["property_type"], total, occ, max(0, total - occ), r["created_at"]])
        return send_csv(self, "atlas_properties.csv", rows)

    def _landlord_export_property_units(self, u, q):
        u = self._req_role(u, "landlord", action="landlord.property.manage")
        if not u:
            return
        pid = ((q.get("property_id") or [""])[0]).strip()
        if len(pid) < 5:
            return redir(self, with_msg("/landlord/properties", "Select a property before exporting units.", True))
        c = db()
        pr = c.execute("SELECT id,name FROM properties WHERE id=? AND owner_account=?", (pid, u["account_number"])).fetchone()
        if not pr:
            c.close()
            return e403(self)
        units = c.execute(
            "SELECT u.id,u.unit_label,u.beds,u.baths,u.rent,u.is_occupied,"
            "EXISTS(SELECT 1 FROM listing_requests lr WHERE lr.unit_id=u.id AND lr.status='pending') AS pending_submission "
            "FROM units u WHERE u.property_id=? ORDER BY u.id",
            (pid,),
        ).fetchall()
        c.close()
        rows = [["property_id", "property_name", "unit_id", "unit_label", "beds", "baths", "rent", "is_occupied", "pending_submission"]]
        for r in units:
            rows.append([
                pid,
                pr["name"],
                r["id"],
                r["unit_label"],
                to_int(r["beds"], 0),
                to_int(r["baths"], 0),
                to_int(r["rent"], 0),
                "yes" if to_int(r["is_occupied"], 0) else "no",
                "yes" if to_int(r["pending_submission"], 0) else "no",
            ])
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", pid)
        return send_csv(self, f"atlas_units_{safe}.csv", rows)

    def _landlord_export_listing_requests(self, u, filtered=False):
        u = self._req_role(u, "landlord", action="landlord.listing.submit")
        if not u:
            return
        q = parse_qs(urlparse(self.path).query)
        status_filter = ((q.get("status") or [""])[0]).strip().lower() if filtered else ""
        if status_filter not in ("", "pending", "approved", "rejected"):
            status_filter = ""
        property_filter = ((q.get("property") or [""])[0]).strip() if filtered else ""
        search = ((q.get("q") or [""])[0]).strip().lower() if filtered else ""
        c = db()
        sql = (
            "SELECT r.id,r.property_id,COALESCE(p.name,'') AS property_name,COALESCE(uu.unit_label,'') AS unit_label,"
            "r.title,r.price,r.status,r.created_at,COALESCE(r.approval_note,'') AS approval_note "
            "FROM listing_requests r "
            "LEFT JOIN properties p ON p.id=r.property_id "
            "LEFT JOIN units uu ON uu.id=r.unit_id "
            "WHERE (p.owner_account=? OR r.submitted_by_user_id=?) "
        )
        args = [u["account_number"], u["id"]]
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
        rows_db = c.execute(sql + "ORDER BY r.created_at DESC,r.id DESC", tuple(args)).fetchall()
        c.close()
        rows = [["request_id", "property_id", "property_name", "unit_label", "title", "price", "status", "submitted_at", "review_note"]]
        for r in rows_db:
            rows.append([
                r["id"],
                r["property_id"],
                r["property_name"],
                r["unit_label"],
                r["title"],
                to_int(r["price"], 0),
                r["status"],
                r["created_at"],
                r["approval_note"],
            ])
        fname = "atlas_listing_requests_filtered.csv" if filtered else "atlas_listing_requests.csv"
        return send_csv(self, fname, rows)

    def _landlord_export_checks(self, u):
        u = self._req_role(u, "landlord", action="landlord.portal")
        if not u:
            return
        q = parse_qs(urlparse(self.path).query)
        status_filter = ((q.get("status") or [""])[0]).strip().lower()
        if status_filter not in ("", "requested", "scheduled", "completed", "cancelled"):
            status_filter = ""
        search = ((q.get("q") or [""])[0]).strip().lower()
        sql = (
            "SELECT id,property_id,preferred_date,status,COALESCE(notes,'') AS notes,created_at "
            "FROM property_checks WHERE requester_account=? "
        )
        args = [u["account_number"]]
        if status_filter:
            sql += "AND status=? "
            args.append(status_filter)
        if search:
            s = "%" + search + "%"
            sql += "AND (LOWER(COALESCE(property_id,'')) LIKE ? OR LOWER(COALESCE(notes,'')) LIKE ?) "
            args.extend([s, s])
        c = db()
        rows_db = c.execute(sql + "ORDER BY created_at DESC,id DESC LIMIT 5000", tuple(args)).fetchall()
        c.close()
        rows = [["id", "property_id", "preferred_date", "status", "notes", "created_at"]]
        for r in rows_db:
            rows.append([r["id"], r["property_id"], r["preferred_date"], r["status"], r["notes"], r["created_at"]])
        return send_csv(self, "atlas_property_checks.csv", rows)

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
        return send_csv(self, "atlas_manager_properties.csv", rows)

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
        return send_csv(self, "atlas_manager_listing_requests.csv", rows)

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
        return send_csv(self, "atlas_payments.csv", rows)


    def _req_role(self,u,*roles,action=None):
        if not u:
            redir(self,"/login")
            return None
        user_role = normalize_role(u.get("role"))
        allowed_roles = {normalize_role(r) for r in roles}
        if user_role!="admin" and roles and user_role not in allowed_roles:
            e403(self)
            return None
        if action:
            c=db()
            ok = user_permission_allowed(c, u, action)
            c.close()
            if not ok:
                e403(self)
                return None
        return u

    def _req_action(self, u, action):
        if not u:
            redir(self, "/login")
            return False
        c = db()
        ok = user_permission_allowed(c, u, action)
        c.close()
        if not ok:
            e403(self)
            return False
        return True

    # â”€â”€ Tenant GET â”€â”€
    
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
            return send_html(self,render("tenant_maintenance_new.html",title="Request Maintenance",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2)))
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

    # â”€â”€ Tenant POST â”€â”€
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
            mid = 0
            if len(desc)>=5:
                c=db()
                c.execute("INSERT INTO maintenance_requests(tenant_account,tenant_name,description,status,urgency)VALUES(?,?,?,?,?)",
                          (u["account_number"],u["full_name"],desc,"open",urgency))
                mid=c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                up=getattr(self,"_files",{}).get("photo")
                if up and up.get("content"):
                    save_image_upload(c, u["id"], "maintenance_requests", mid, "maintenance_photo", up)
                for m in c.execute("SELECT id FROM users WHERE role='property_manager'").fetchall():
                    create_notification(c,m["id"],f"New {urgency} maintenance request from {u['full_name']}", "/manager/maintenance")
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

    # —— Property Manager (Unified) GET/POST ——
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

    # â”€â”€ Landlord GET â”€â”€
    def _landlord_get(self,path,u):
        u=self._req_role(u,"landlord",action="landlord.portal")
        if not u:return
        nr=nav(u,path)
        if path=="/landlord":return send_html(self,render("landlord_home.html",title="Landlord Dashboard",nav_right=nr,nav_menu=nav_menu(u,path)))
        if path=="/landlord/properties":
            q2=parse_qs(urlparse(self.path).query)
            search=((q2.get("q") or [""])[0]).strip().lower()
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
                "<form method='GET' action='/landlord/properties' class='row' style='align-items:flex-end;'>"
                f"<div class='field' style='min-width:260px;flex:1;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='property id, name, location'></div>"
                "<button class='secondary-btn' type='submit'>Apply</button>"
                "<a class='ghost-btn' href='/landlord/properties'>Reset</a>"
                "</form>"
                "</div>"
            )
            cards=""
            for p in props:
                cards+=f'<a class="prop-item" href="/landlord/property/{esc(p["id"])}" style="text-decoration:none;"><div class="thumb"></div><div><div style="font-weight:1000;">{esc(p["name"])}</div><div class="muted" style="font-size:12px;">{esc(p["location"])} - {esc(p["property_type"])} - {p["units_count"]} units</div><div class="muted" style="font-size:12px;">ID: <b>{esc(p["id"])}</b></div></div><div class="badge">Units</div></a>'
            np=""if props else'<div class="card"><p class="muted">No properties yet.</p></div>'
            return send_html(self,render("landlord_properties.html",title="My Properties",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),properties_cards=cards,no_properties=np,portfolio_summary=portfolio_summary,filters_form=filters_form))
        if path=="/landlord/listing-requests":
            q2=parse_qs(urlparse(self.path).query)
            st_filter=((q2.get("status") or [""])[0]).strip().lower()
            if st_filter not in ("", "pending", "approved", "rejected"):
                st_filter = ""
            prop_filter=((q2.get("property") or [""])[0]).strip()
            search=((q2.get("q") or [""])[0]).strip().lower()
            sort=((q2.get("sort") or ["newest"])[0]).strip().lower()
            order_sql = "r.created_at ASC, r.id ASC" if sort=="oldest" else "r.created_at DESC, r.id DESC"
            page, per, offset = parse_page_params(q2, default_per=30, max_per=200)
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
                action_col = "<span class='muted'>-</span>"
                if st == "rejected":
                    action_col = (
                        "<form method='POST' action='/landlord/listing/resubmit' style='margin:0;'>"
                        f"<input type='hidden' name='req_id' value='{r['id']}'>"
                        "<button class='ghost-btn' type='submit'>Resubmit</button>"
                        "</form>"
                    )
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
                    f"<td>{action_col}</td>"
                    "</tr>"
                )
            props = c.execute("SELECT id,name FROM properties WHERE owner_account=? ORDER BY created_at DESC",(u["account_number"],)).fetchall()
            c.close()
            empty_box="" if rows else '<div class="notice" style="margin-top:10px;">No listing submissions yet.</div>'
            prop_opts="".join(f"<option value='{esc(p['id'])}' {'selected' if prop_filter==p['id'] else ''}>{esc(p['name'])} ({esc(p['id'])})</option>" for p in props)
            filters_form = (
                "<div class='card' style='margin-bottom:10px;'>"
                "<form method='GET' action='/landlord/listing-requests' class='row' style='align-items:flex-end;'>"
                "<div class='field' style='min-width:150px;'><label>Status</label>"
                f"<select name='status'><option value=''>All</option><option value='pending' {'selected' if st_filter=='pending' else ''}>pending</option><option value='approved' {'selected' if st_filter=='approved' else ''}>approved</option><option value='rejected' {'selected' if st_filter=='rejected' else ''}>rejected</option></select></div>"
                "<div class='field' style='min-width:220px;'><label>Property</label>"
                f"<select name='property'><option value=''>All</option>{prop_opts}</select></div>"
                f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='title/property'></div>"
                "<div class='field' style='min-width:150px;'><label>Sort</label>"
                f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                "<button class='primary-btn' type='submit'>Apply</button>"
                "<a class='ghost-btn' href='/landlord/listing-requests'>Reset</a>"
                "</form>"
                "</div>"
            )
            export_q = urlencode(query_without_page(q2))
            export_filtered_url = "/landlord/export/listing_requests_filtered" + (f"?{export_q}" if export_q else "")
            pager_box = pager_html("/landlord/listing-requests", q2, page, per, total)
            return send_html(self,render("landlord_listing_requests.html",title="Listing Submissions",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),filters_form=filters_form,export_filtered_url=export_filtered_url,requests_rows=tr,empty_box=empty_box,pager_box=pager_box))
        if path=="/landlord/tenants":
            return self._landlord_tenants_get(u)
        if path=="/landlord/property/new":return send_html(self,render("landlord_property_new.html",title="Register Property",nav_right=nr,nav_menu=nav_menu(u,path),error_box=""))
        m2=re.match(r"^/landlord/property/(.+)$",path)
        if m2 and m2.group(1)!="new":
            q2=parse_qs(urlparse(self.path).query)
            _msg=(q2.get("msg") or [""])[0].strip()
            _err=(q2.get("err") or ["0"])[0]=="1"
            view = ((q2.get("view") or ["all"])[0]).strip().lower()
            if view not in ("all", "vacant", "occupied"):
                view = "all"
            unit_q = ((q2.get("q") or [""])[0]).strip().lower()
            message_box=f'<div class="{"notice err" if _err else "notice"}" style="margin-bottom:10px;">{esc(_msg)}</div>' if _msg else ""
            pid=m2.group(1)
            c=db()
            pr=c.execute("SELECT * FROM properties WHERE id=? AND owner_account=?",(pid,u["account_number"])).fetchone()
            if not pr:
                c.close()
                return e404(self)
            all_units=c.execute("SELECT * FROM units WHERE property_id=? ORDER BY id",(pid,)).fetchall()
            pending_cnt = c.execute(
                "SELECT COUNT(1) AS n FROM listing_requests WHERE property_id=? AND status='pending'",
                (pid,),
            ).fetchone()["n"]
            c.close()
            units = []
            for x in all_units:
                occ = to_int(x["is_occupied"], 0)
                if view == "vacant" and occ:
                    continue
                if view == "occupied" and not occ:
                    continue
                if unit_q and unit_q not in (x["unit_label"] or "").lower():
                    continue
                units.append(x)

            total_units = len(all_units)
            occupied_units = sum(1 for x in all_units if to_int(x["is_occupied"], 0))
            vacant_units = max(0, total_units - occupied_units)
            avg_rent = 0
            if all_units:
                avg_rent = int(sum(max(0, to_int(x["rent"], 0)) for x in all_units) / max(1, len(all_units)))
            property_summary = (
                "<div class='card' style='margin-bottom:12px;'>"
                "<div class='grid-3'>"
                f"<div class='stat'><div class='muted'>Units</div><div class='stat-num'>{total_units}</div></div>"
                f"<div class='stat'><div class='muted'>Occupied / Vacant</div><div class='stat-num'>{occupied_units} / {vacant_units}</div></div>"
                f"<div class='stat'><div class='muted'>Avg Rent (B$)</div><div class='stat-num'>{avg_rent:,}</div></div>"
                "</div>"
                f"<div class='muted' style='margin-top:10px;'>Pending listing submissions: {to_int(pending_cnt, 0)}</div>"
                "</div>"
            )
            unit_filters = (
                "<div class='card' style='margin-bottom:12px;'>"
                "<form method='GET' class='row' style='align-items:flex-end;'>"
                f"<input type='hidden' name='msg' value='{esc(_msg)}'>"
                "<div class='field' style='min-width:160px;'><label>View</label>"
                "<select name='view'>"
                f"<option value='all' {'selected' if view=='all' else ''}>All Units</option>"
                f"<option value='vacant' {'selected' if view=='vacant' else ''}>Vacant Only</option>"
                f"<option value='occupied' {'selected' if view=='occupied' else ''}>Occupied Only</option>"
                "</select></div>"
                f"<div class='field' style='flex:1;min-width:220px;'><label>Unit Search</label><input name='q' value='{esc(unit_q)}' placeholder='Unit label'></div>"
                "<button class='secondary-btn' type='submit'>Apply</button>"
                f"<a class='ghost-btn' href='/landlord/property/{esc(pid)}'>Reset</a>"
                "</form>"
                "</div>"
            )
            bulk_actions = (
                "<div class='card' style='margin-bottom:12px;'>"
                "<h3 style='margin-top:0;'>Bulk Unit Actions</h3>"
                "<form method='POST' action='/landlord/units/bulk' class='row' style='align-items:flex-end;'>"
                f"<input type='hidden' name='property_id' value='{esc(pid)}'>"
                "<div class='field' style='min-width:180px;'><label>Target Units</label>"
                "<select name='target'>"
                "<option value='all'>All</option>"
                "<option value='vacant'>Vacant</option>"
                "<option value='occupied'>Occupied</option>"
                "</select></div>"
                "<div class='field' style='min-width:220px;'><label>Action</label>"
                "<select name='action'>"
                "<option value='set_rent'>Set rent amount</option>"
                "<option value='increase_amount'>Increase rent by amount</option>"
                "<option value='increase_percent'>Increase rent by percent</option>"
                "<option value='mark_occupied'>Mark occupied</option>"
                "<option value='mark_vacant'>Mark vacant</option>"
                "</select></div>"
                "<div class='field' style='min-width:180px;'><label>Value (set/increase actions)</label>"
                "<input type='number' min='0' name='rent' placeholder='e.g. 1750'></div>"
                "<button class='secondary-btn' type='submit'>Apply Bulk Action</button>"
                "</form>"
                "</div>"
            )
            rows=""
            submit_btns=""
            for x in units:
                checked="checked" if x["is_occupied"] else ""
                form_id = f"unitUpdate{x['id']}"
                rows+=(
                    "<tr>"
                    f"<td>{esc(x['unit_label'])}</td>"
                    f"<td><label class='muted' style='display:flex;gap:6px;align-items:center;margin:0;'><input form='{form_id}' type='checkbox' name='is_occupied' value='1' {checked}>Occupied</label>"
                    f"</td>"
                    f"<td><input form='{form_id}' name='beds' type='number' min='0' value='{x['beds']}' style='width:70px;'></td>"
                    f"<td><input form='{form_id}' name='baths' type='number' min='0' value='{x['baths']}' style='width:70px;'></td>"
                    f"<td><input form='{form_id}' name='rent' type='number' min='0' value='{x['rent']}' style='width:120px;'></td>"
                    f"<td style='white-space:nowrap;display:flex;gap:8px;align-items:center;'>"
                    f"<form id='{form_id}' method='post' action='/landlord/unit/update' style='display:inline;margin:0;'>"
                    f"<input type='hidden' name='unit_id' value='{x['id']}'>"
                    f"<input type='hidden' name='property_id' value='{esc(pid)}'>"
                    f"<button class='secondary-btn' type='submit'>Save</button>"
                    f"</form>"
                    f"<a class='ghost-btn' href='/landlord/listing/submit?unit_id={x['id']}&property_id={esc(pid)}'>Submit for Listing</a>"
                    f"</td>"
                    "</tr>"
                )
            if not rows:
                rows = "<tr><td colspan='6' class='muted'>No units match your filter.</td></tr>"
            for x in all_units:
                if to_int(x["is_occupied"], 0):
                    continue
                submit_btns += f"<a class='primary-btn' href='/landlord/listing/submit?unit_id={x['id']}&property_id={esc(pid)}'>Submit {esc(x['unit_label'])} for Listing</a>"
            if not submit_btns:
                submit_btns = "<span class='muted'>All units are currently occupied.</span>"
            return send_html(
                self,
                render(
                    "landlord_property.html",
                    title=pr["name"],
                    nav_right=nr,
                    nav_menu=nav_menu(u,path),
                    property_id=esc(pid),
                    message_box=message_box,
                    prop_name=esc(pr["name"]),
                    prop_location=esc(pr["location"]),
                    prop_type=esc(pr["property_type"]),
                    prop_units=str(pr["units_count"]),
                    property_summary=property_summary,
                    unit_filters=unit_filters,
                    bulk_actions=bulk_actions,
                    units_rows=rows,
                    submit_buttons=submit_btns,
                ),
            )

        if path=="/landlord/listing/submit":
            q=parse_qs(urlparse(self.path).query)
            unit_id=to_int((q.get("unit_id")or["0"])[0], 0)
            pid=(q.get("property_id")or[""])[0]
            c=db()
            pr=c.execute("SELECT * FROM properties WHERE id=? AND owner_account=?",(pid,u["account_number"])).fetchone()
            if not pr:c.close();return e403(self)
            unit=c.execute("SELECT * FROM units WHERE id=?",(unit_id,)).fetchone()
            c.close()
            if (not pr) or (not unit) or unit["property_id"]!=pid:return e404(self)
            return send_html(self,render("landlord_listing_submit.html",
                title="Submit for Listing",nav_right=nr,nav_menu=nav_menu(u,path),
                unit_id=str(unit_id),property_id=esc(pid),
                listing_title=esc(f"{pr['name']} - {unit['unit_label']}"),
                price=str(unit["rent"] or 0),location=esc(pr["location"]),
                beds=str(unit["beds"]),baths=str(unit["baths"]),
                description=esc(""),
                cat_long="selected",cat_short="",cat_vehicle="",cat_sell=""
            ))

        if path=="/landlord/check/new":return send_html(self,render("landlord_check_new.html",title="Request Check",nav_right=nr,nav_menu=nav_menu(u,path),error_box=""))
        if path=="/landlord/checks":
            q2=parse_qs(urlparse(self.path).query)
            st_filter=((q2.get("status") or [""])[0]).strip().lower()
            if st_filter not in ("", "requested", "scheduled", "completed", "cancelled"):
                st_filter = ""
            search=((q2.get("q") or [""])[0]).strip().lower()
            sort=((q2.get("sort") or ["newest"])[0]).strip().lower()
            order_sql = "created_at ASC,id ASC" if sort=="oldest" else "created_at DESC,id DESC"
            page, per, offset = parse_page_params(q2, default_per=25, max_per=200)
            c=db()
            sql = "SELECT * FROM property_checks WHERE requester_account=? "
            args = [u["account_number"]]
            if st_filter:
                sql += "AND status=? "
                args.append(st_filter)
            if search:
                s = "%" + search + "%"
                sql += "AND (LOWER(COALESCE(property_id,'')) LIKE ? OR LOWER(COALESCE(notes,'')) LIKE ?) "
                args.extend([s, s])
            total = c.execute("SELECT COUNT(1) AS n FROM (" + sql + ") t", tuple(args)).fetchone()["n"]
            cks=c.execute(sql + f"ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(args + [per, offset])).fetchall()
            tr=""
            for x in cks:
                st=(x["status"] or "").strip()
                can_cancel=st in ("requested","scheduled")
                action=(
                    f"<form method='POST' action='/landlord/check/cancel' style='margin:0;'>"
                    f"<input type='hidden' name='check_id' value='{x['id']}'>"
                    "<button class='ghost-btn' type='submit'>Cancel</button>"
                    "</form>"
                ) if can_cancel else "<span class='muted'>-</span>"
                tr += (
                    "<tr>"
                    f"<td>#{x['id']}</td>"
                    f"<td>{esc(x['property_id'])}</td>"
                    f"<td>{esc(x['preferred_date'])}</td>"
                    f"<td>{status_badge(st,'review')}</td>"
                    f"<td>{esc(x['notes']or'')}</td>"
                    f"<td>{action}</td>"
                    "</tr>"
                )
            if not tr:
                tr = "<tr><td colspan='6'>" + empty_state("C", "No Property Checks", "No property checks matched this filter.") + "</td></tr>"
            c.close()
            export_q = urlencode(query_without_page(q2))
            export_filtered_url = "/landlord/export/checks" + (f"?{export_q}" if export_q else "")
            filters_form = (
                "<div class='card' style='margin-bottom:10px;'>"
                "<form method='GET' action='/landlord/checks' class='row' style='align-items:flex-end;'>"
                "<div class='field' style='min-width:170px;'><label>Status</label>"
                f"<select name='status'><option value=''>All</option><option value='requested' {'selected' if st_filter=='requested' else ''}>requested</option><option value='scheduled' {'selected' if st_filter=='scheduled' else ''}>scheduled</option><option value='completed' {'selected' if st_filter=='completed' else ''}>completed</option><option value='cancelled' {'selected' if st_filter=='cancelled' else ''}>cancelled</option></select></div>"
                f"<div class='field' style='min-width:220px;'><label>Search</label><input name='q' value='{esc(search)}' placeholder='property id / notes'></div>"
                "<div class='field' style='min-width:150px;'><label>Sort</label>"
                f"<select name='sort'><option value='newest' {'selected' if sort!='oldest' else ''}>Newest</option><option value='oldest' {'selected' if sort=='oldest' else ''}>Oldest</option></select></div>"
                "<button class='primary-btn' type='submit'>Apply</button>"
                "<a class='ghost-btn' href='/landlord/checks'>Reset</a>"
                f"<a class='ghost-btn' href='{export_filtered_url}'>Export CSV</a>"
                "</form>"
                "</div>"
            )
            pager_box = pager_html("/landlord/checks", q2, page, per, total)
            return send_html(self,render("landlord_checks.html",title="My Checks",nav_right=nr,nav_menu=nav_menu(u,path),message_box=query_message_box(q2),filters_form=filters_form,checks_rows=tr,pager_box=pager_box))
        return e404(self)

    # â”€â”€ Landlord POST â”€â”€
    def _landlord_post(self,path,u,f):
        u=self._req_role(u,"landlord",action="landlord.portal")
        if not u:return

        if path=="/landlord/tenant/invite":
            if not self._req_action(u, "landlord.tenant_sync.manage"): return
            return self._landlord_tenant_invite(f,u)
        if path=="/landlord/tenant/invite/cancel":
            if not self._req_action(u, "landlord.tenant_sync.manage"): return
            invite_id = to_int(f.get("invite_id"), 0)
            revoke_reason = (f.get("revoke_reason") or "revoked_by_landlord").strip()[:120]
            if invite_id <= 0:
                return redir(self, with_msg("/landlord/tenants", "Invite was not found.", True))
            c = db()
            cleanup_expired_invites(c)
            row = c.execute(
                "SELECT i.*, p.owner_account FROM tenant_property_invites i "
                "JOIN properties p ON p.id=i.property_id WHERE i.id=?",
                (invite_id,),
            ).fetchone()
            if not row:
                c.close()
                return redir(self, with_msg("/landlord/tenants", "Invite was not found.", True))
            if row["owner_account"] != u["account_number"]:
                c.close()
                return e403(self)
            st = (row["status"] or "").strip().lower()
            if st != "pending":
                c.close()
                return redir(self, with_msg("/landlord/tenants", "Invite has already been responded to.", True))
            c.execute(
                "UPDATE tenant_property_invites SET status='cancelled', responded_at=datetime('now'), revoke_reason=? WHERE id=?",
                (revoke_reason, invite_id),
            )
            if row["tenant_user_id"]:
                create_notification(c, row["tenant_user_id"], f"Invite cancelled: {row['property_id']} / {row['unit_label']}", "/tenant/invites")
            audit_log(c, u, "tenant_invite_cancelled", "tenant_property_invites", invite_id, f"{row['property_id']}/{row['unit_label']};reason={revoke_reason}")
            c.commit()
            c.close()
            return redir(self, with_msg("/landlord/tenants", "Invite cancelled."))
        if path=="/landlord/tenant/invite/resend":
            if not self._req_action(u, "landlord.tenant_sync.manage"): return
            invite_id = to_int(f.get("invite_id"), 0)
            if invite_id <= 0:
                return redir(self, with_msg("/landlord/tenants", "Invite was not found.", True))
            c = db()
            row = c.execute(
                "SELECT i.*, p.owner_account FROM tenant_property_invites i "
                "JOIN properties p ON p.id=i.property_id WHERE i.id=?",
                (invite_id,),
            ).fetchone()
            if not row:
                c.close()
                return redir(self, with_msg("/landlord/tenants", "Invite was not found.", True))
            if row["owner_account"] != u["account_number"]:
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
            return redir(self, with_msg("/landlord/tenants", note, err=(not ok)))
        if path=="/landlord/leases/end":
            if not self._req_action(u, "landlord.tenant_sync.manage"): return
            lease_id=to_int(f.get("lease_id"), 0)
            if lease_id<=0:return redir(self,"/landlord/tenants")
            c=db()
            row=c.execute(
                "SELECT l.* FROM tenant_leases l JOIN properties p ON p.id=l.property_id "
                "WHERE l.id=? AND p.owner_account=?",
                (lease_id,u["account_number"]),
            ).fetchone()
            if row and to_int(row["is_active"],0):
                c.execute("UPDATE tenant_leases SET is_active=0,end_date=date('now') WHERE id=?",(lease_id,))
                c.execute("UPDATE lease_roommates SET status='removed' WHERE lease_id=? AND status='active'", (lease_id,))
                c.execute("UPDATE units SET is_occupied=0 WHERE property_id=? AND unit_label=?",(row["property_id"],row["unit_label"]))
                tgt=c.execute("SELECT id FROM users WHERE account_number=?",(row["tenant_account"],)).fetchone()
                if tgt:
                    create_notification(c,tgt["id"],f"Lease ended: {row['property_id']} / {row['unit_label']}", "/tenant/lease")
                audit_log(c,u,"lease_ended","tenant_leases",lease_id,f"{row['property_id']}/{row['unit_label']}")
            c.commit();c.close()
            return redir(self,"/landlord/tenants")
        if path=="/landlord/units/bulk":
            if not self._req_action(u, "landlord.property.manage"): return
            pid=(f.get("property_id") or "").strip()
            target=(f.get("target") or "all").strip().lower()
            action=(f.get("action") or "").strip().lower()
            rent=to_int(f.get("rent"), -1)
            if target not in ("all","vacant","occupied"):
                target = "all"
            if action not in ("set_rent","increase_amount","increase_percent","mark_occupied","mark_vacant"):
                return redir(self, with_msg(f"/landlord/property/{esc(pid)}", "Invalid bulk action.", True))
            if action in ("set_rent","increase_amount","increase_percent") and rent < 0:
                return redir(self, with_msg(f"/landlord/property/{esc(pid)}", "Enter a valid value for this rent action.", True))
            c=db()
            own=c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?",(pid,u["account_number"])).fetchone()
            if not own:
                c.close()
                return e403(self)
            where="property_id=?"
            args=[pid]
            if target=="vacant":
                where+=" AND is_occupied=0"
            elif target=="occupied":
                where+=" AND is_occupied=1"
            before = c.execute(f"SELECT COUNT(1) AS n FROM units WHERE {where}", tuple(args)).fetchone()["n"]
            affected = 0
            if to_int(before, 0) > 0:
                if action=="set_rent":
                    cur=c.execute(f"UPDATE units SET rent=? WHERE {where}", tuple([rent] + args))
                    affected = to_int(cur.rowcount, to_int(before, 0))
                    if affected < 0:
                        affected = to_int(before, 0)
                elif action=="increase_amount":
                    cur=c.execute(f"UPDATE units SET rent=MAX(0,rent+?) WHERE {where}", tuple([rent] + args))
                    affected = to_int(cur.rowcount, to_int(before, 0))
                    if affected < 0:
                        affected = to_int(before, 0)
                elif action=="increase_percent":
                    cur=c.execute(
                        f"UPDATE units SET rent=CAST(ROUND(rent * (1 + (? / 100.0))) AS INTEGER) WHERE {where}",
                        tuple([rent] + args),
                    )
                    affected = to_int(cur.rowcount, to_int(before, 0))
                    if affected < 0:
                        affected = to_int(before, 0)
                elif action=="mark_occupied":
                    cur=c.execute(f"UPDATE units SET is_occupied=1 WHERE {where}", tuple(args))
                    affected = to_int(cur.rowcount, to_int(before, 0))
                    if affected < 0:
                        affected = to_int(before, 0)
                elif action=="mark_vacant":
                    cur=c.execute(
                        f"UPDATE units SET is_occupied=0 WHERE {where} "
                        "AND NOT EXISTS (SELECT 1 FROM tenant_leases l WHERE l.property_id=units.property_id AND l.unit_label=units.unit_label AND l.is_active=1)",
                        tuple(args),
                    )
                    affected = to_int(cur.rowcount, 0)
                    if affected < 0:
                        affected = 0
            audit_log(c, u, "landlord_bulk_unit_action", "properties", pid, f"target={target};action={action};affected={affected}")
            c.commit()
            c.close()
            return redir(self, with_msg(f"/landlord/property/{esc(pid)}", f"Bulk action complete. Updated {max(0, affected)} unit(s)."))
        if path=="/landlord/listing/submit_all":
            if not self._req_action(u, "landlord.listing.submit"): return
            pid=(f.get("property_id") or "").strip()
            cat=(f.get("category") or "Long Term Rental").strip()
            c=db()
            created, skipped, err = create_bulk_listing_requests(c, u, pid, cat, owner_account=u["account_number"])
            if not err:
                audit_log(c, u, "landlord_submit_all_units", "properties", pid, f"created={created};skipped={skipped};category={cat}")
                c.commit()
                c.close()
                return redir(self, with_msg(f"/landlord/property/{esc(pid)}", f"Submitted {created} unit(s) for approval. Skipped {skipped}."))
            c.close()
            fail_path = f"/landlord/property/{esc(pid)}" if pid else "/landlord/tenants"
            return redir(self, with_msg(fail_path, err, True))
        if path=="/landlord/listing/resubmit":
            if not self._req_action(u, "landlord.listing.submit"): return
            req_id = to_int(f.get("req_id"), 0)
            if req_id <= 0:
                return redir(self, "/landlord/listing-requests")
            c = db()
            old = c.execute(
                "SELECT r.*, p.owner_account FROM listing_requests r "
                "LEFT JOIN properties p ON p.id=r.property_id WHERE r.id=?",
                (req_id,),
            ).fetchone()
            if not old:
                c.close()
                return e404(self)
            if old["owner_account"] != u["account_number"]:
                c.close()
                return e403(self)
            if (old["status"] or "").strip().lower() != "rejected":
                c.close()
                return redir(self, with_msg("/landlord/listing-requests", "Only rejected submissions can be resubmitted.", True))
            exists_pending = c.execute(
                "SELECT 1 FROM listing_requests WHERE property_id=? AND unit_id=? AND status='pending'",
                (old["property_id"], old["unit_id"]),
            ).fetchone()
            if exists_pending:
                c.close()
                return redir(self, with_msg("/landlord/listing-requests", "A pending submission already exists for this unit.", True))
            c.execute(
                "INSERT INTO listing_requests("
                "property_id,unit_id,title,price,location,beds,baths,category,description,status,submitted_by_user_id,created_at,"
                "approval_note,review_state,checklist_photos,checklist_price,checklist_description,checklist_docs,reviewed_at,resubmission_count"
                ")VALUES(?,?,?,?,?,?,?,?,?,'pending',?,datetime('now'),?,'initial',0,0,0,0,NULL,?)",
                (
                    old["property_id"],
                    old["unit_id"],
                    old["title"],
                    old["price"],
                    old["location"],
                    old["beds"],
                    old["baths"],
                    old["category"],
                    old["description"],
                    u["id"],
                    "",
                    max(0, to_int(old["resubmission_count"], 0) + 1),
                ),
            )
            new_req_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            # Carry forward photos tied to previous request.
            c.execute(
                "UPDATE uploads SET related_id=? WHERE related_table='listing_requests' AND related_id=? AND kind='listing_photo'",
                (new_req_id, req_id),
            )
            for a in c.execute("SELECT id FROM users WHERE role='admin'").fetchall():
                create_notification(c, a["id"], f"Resubmitted listing request: {old['title']}", "/admin/submissions")
            audit_log(c, u, "listing_request_resubmitted", "listing_requests", new_req_id, f"from={req_id}")
            c.commit()
            c.close()
            return redir(self, with_msg("/landlord/listing-requests", "Listing request resubmitted."))

        if path=="/landlord/unit/update":
            if not self._req_action(u, "landlord.property.manage"): return
            unit_id=to_int(f.get("unit_id"), 0);pid=(f.get("property_id") or "")
            rent=to_int(f.get("rent"), 0);beds=to_int(f.get("beds"), 0);baths=to_int(f.get("baths"), 0)
            is_occ=1 if (f.get("is_occupied") in ("1","on","true","yes")) else 0
            c=db()
            pr=c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?",(pid,u["account_number"])).fetchone()
            if not pr:c.close();return e403(self)
            unit=c.execute("SELECT * FROM units WHERE id=?",(unit_id,)).fetchone()
            if not unit or unit["property_id"]!=pid:c.close();return e404(self)
            has_active_lease = c.execute(
                "SELECT 1 FROM tenant_leases WHERE property_id=? AND unit_label=? AND is_active=1",
                (pid, unit["unit_label"]),
            ).fetchone()
            if has_active_lease and not is_occ:
                c.close()
                return redir(self, with_msg(f"/landlord/property/{esc(pid)}", "Cannot mark this unit vacant while an active lease exists. Remove tenant link first.", True))
            c.execute("UPDATE units SET rent=?,beds=?,baths=?,is_occupied=? WHERE id=?",(rent,beds,baths,is_occ,unit_id))
            audit_log(c, u, "landlord_unit_updated", "units", unit_id, f"rent={rent};beds={beds};baths={baths};occupied={is_occ}")
            c.commit();c.close()
            return redir(self,f"/landlord/property/{esc(pid)}")

        if path=="/landlord/listing/submit":
            if not self._req_action(u, "landlord.listing.submit"): return
            pid=(f.get("property_id") or "").strip()
            unit_id=to_int(f.get("unit_id"), 0)
            title=(f.get("title") or "").strip()
            location=(f.get("location") or "").strip()
            category=(f.get("category") or "Long Term Rental").strip()
            description=(f.get("description") or "").strip()
            price=to_int(f.get("price"), 0)
            beds=to_int(f.get("beds"), 0);baths=to_int(f.get("baths"), 0)
            if not title or not pid or unit_id<=0:return redir(self,f"/landlord/property/{esc(pid)}")
            c=db()
            pr=c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?",(pid,u["account_number"])).fetchone()
            if not pr:c.close();return e403(self)
            unit=c.execute("SELECT * FROM units WHERE id=?",(unit_id,)).fetchone()
            if not unit or unit["property_id"]!=pid:c.close();return e404(self)
            c.execute("INSERT INTO listing_requests(property_id,unit_id,title,price,location,beds,baths,category,description,status,submitted_by_user_id)VALUES(?,?,?,?,?,?,?,?,?,'pending',?)",
                      (pid,unit_id,title,price,location,beds,baths,category,description,u["id"]))
            req_id=c.execute("SELECT last_insert_rowid()").fetchone()[0]
            files=getattr(self,"_files",{}) or {}
            photos=files.get("photos")
            if photos:
                photo_items = photos if isinstance(photos, list) else [photos]
                for fi in photo_items:
                    save_image_upload(c, u["id"], "listing_requests", req_id, "listing_photo", fi)
            lease=files.get("lease_pdf")
            if lease:
                save_pdf_upload(c, u["id"], "properties", None, "lease_pdf", lease, related_key=pid)
            # notify admin
            for r in c.execute("SELECT id FROM users WHERE role='admin'").fetchall():
                create_notification(c, r["id"], f"New listing submission: {title}", "/admin/submissions")
            audit_log(c, u, "landlord_listing_submitted", "listing_requests", req_id, f"{pid};unit={unit_id};title={title}")
            c.commit();c.close()
            return redir(self,"/landlord/properties")

        if path=="/landlord/property/new":
            if not self._req_action(u, "landlord.property.manage"): return
            nm=(f.get("name")or"").strip();loc=(f.get("location")or"").strip();pt=f.get("property_type")or"Apartment";uc=to_int(f.get("units_count"), 0)
            if pt not in("House","Apartment")or uc<1 or len(nm)<2 or len(loc)<2:return send_html(self,render("landlord_property_new.html",title="Register Property",nav_right=nav(u,"/landlord/property/new"),nav_menu=nav_menu(u,"/landlord/property/new"),error_box='<div class="notice err"><b>Error:</b> Check fields.</div>'))
            pid=f"{u['account_number']}-{int(datetime.now(timezone.utc).timestamp())}";c=db()
            c.execute("INSERT INTO properties(id,owner_account,name,property_type,units_count,location)VALUES(?,?,?,?,?,?)",(pid,u["account_number"],nm,pt,uc,loc))
            for i in range(1,uc+1):c.execute("INSERT INTO units(property_id,unit_label)VALUES(?,?)",(pid,f"Unit {i}"))
            files=getattr(self,"_files",{}) or {}
            photos=files.get("photos")
            if photos:
                photo_items = photos if isinstance(photos, list) else [photos]
                for fi in photo_items[:12]:
                    save_image_upload(c, u["id"], "properties", None, "property_photo", fi, related_key=pid)
            audit_log(c, u, "property_registered", "properties", pid, f"units={uc};type={pt}")
            c.commit();c.close();return redir(self,"/landlord/properties")
        if path=="/landlord/check/new":
            if not self._req_action(u, "landlord.property.manage"): return
            pid=(f.get("property_id")or"").strip();d=(f.get("preferred_date")or"").strip();notes=(f.get("notes")or"").strip()
            if len(pid)<5 or len(d)<8:return send_html(self,render("landlord_check_new.html",title="Request Check",nav_right=nav(u,"/landlord/check/new"),nav_menu=nav_menu(u,"/landlord/check/new"),error_box='<div class="notice err"><b>Error:</b> Fill property ID and date.</div>'))
            c=db();ok=c.execute("SELECT 1 FROM properties WHERE id=? AND owner_account=?",(pid,u["account_number"])).fetchone()
            if not ok:c.close();return e403(self)
            c.execute("INSERT INTO property_checks(requester_account,property_id,preferred_date,notes,status)VALUES(?,?,?,?,?)",(u["account_number"],pid,d,notes,"requested"))
            for m in c.execute("SELECT id FROM users WHERE role IN ('property_manager','admin')").fetchall():
                create_notification(c,m["id"],f"New property check request for {pid}", "/manager/checks")
            audit_log(c, u, "property_check_requested", "property_checks", "", f"{pid};date={d}")
            c.commit();c.close()
            return redir(self,"/landlord/checks")
        if path=="/landlord/check/cancel":
            if not self._req_action(u, "landlord.property.manage"): return
            cid=to_int(f.get("check_id"), 0)
            if cid<=0:return redir(self,"/landlord/checks")
            c=db()
            row=c.execute("SELECT * FROM property_checks WHERE id=? AND requester_account=?",(cid,u["account_number"])).fetchone()
            if not row:
                c.close()
                return e404(self)
            if row["status"] not in ("completed","cancelled"):
                c.execute("UPDATE property_checks SET status='cancelled' WHERE id=?",(cid,))
                audit_log(c, u, "property_check_cancelled", "property_checks", cid, row["property_id"])
            c.commit();c.close()
            return redir(self,"/landlord/checks")
        return e404(self)

    # â”€â”€ Manager GET â”€â”€
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
            cnt_open = to_int(c.execute(f"SELECT COUNT(1) AS n {base_sql} AND m.status='open'", tuple(base_args)).fetchone()["n"], 0)
            cnt_prog = to_int(c.execute(f"SELECT COUNT(1) AS n {base_sql} AND m.status='in_progress'", tuple(base_args)).fetchone()["n"], 0)
            cnt_closed = to_int(c.execute(f"SELECT COUNT(1) AS n {base_sql} AND m.status='closed'", tuple(base_args)).fetchone()["n"], 0)
            sql = f"SELECT m.*, CAST(julianday('now') - julianday(m.created_at) AS INT) AS age_days {base_sql}"
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
                "<div class='field' style='flex:1;min-width:180px;'><label>Email (optional)</label><input name='email' placeholder='tech@atlas.local'></div>"
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
            cnt_req = to_int(c.execute(f"SELECT COUNT(1) AS n {base_sql} AND pc.status='requested'", tuple(base_args)).fetchone()["n"], 0)
            cnt_sched = to_int(c.execute(f"SELECT COUNT(1) AS n {base_sql} AND pc.status='scheduled'", tuple(base_args)).fetchone()["n"], 0)
            cnt_done = to_int(c.execute(f"SELECT COUNT(1) AS n {base_sql} AND pc.status='completed'", tuple(base_args)).fetchone()["n"], 0)
            cnt_cancel = to_int(c.execute(f"SELECT COUNT(1) AS n {base_sql} AND pc.status='cancelled'", tuple(base_args)).fetchone()["n"], 0)
            sql = f"SELECT pc.* {base_sql}"
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

    # â”€â”€ Manager POST â”€â”€
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
            if row["owner_account"] != u["account_number"]:
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
            if row["owner_account"] != u["account_number"]:
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
            nm=(f.get("name")or"").strip();loc=(f.get("location")or"").strip();pt=f.get("property_type")or"Apartment";uc=to_int(f.get("units_count"), 0)
            if pt not in("House","Apartment")or uc<1 or len(nm)<2 or len(loc)<2:
                return send_html(self,render("manager_property_new.html",title="Register Property",nav_right=nav(u,"/manager/property/new"),nav_menu=nav_menu(u,"/manager/property/new"),error_box='<div class="notice err"><b>Error:</b> Check fields.</div>'))
            pid=f"{u['account_number']}-{int(datetime.now(timezone.utc).timestamp())}";c=db()
            c.execute("INSERT INTO properties(id,owner_account,name,property_type,units_count,location)VALUES(?,?,?,?,?,?)",(pid,u["account_number"],nm,pt,uc,loc))
            for i in range(1,uc+1):
                c.execute("INSERT INTO units(property_id,unit_label)VALUES(?,?)",(pid,f"Unit {i}"))
            files=getattr(self,"_files",{}) or {}
            photos=files.get("photos")
            if photos:
                photo_items = photos if isinstance(photos, list) else [photos]
                for fi in photo_items[:12]:
                    save_image_upload(c, u["id"], "properties", None, "property_photo", fi, related_key=pid)
            audit_log(c, u, "manager_property_registered", "properties", pid, f"units={uc};type={pt}")
            c.commit();c.close()
            return redir(self, with_msg("/manager/properties", f"Property registered: {pid}"))
        if path=="/manager/listing/submit_all":
            if not self._req_action(u, "manager.listing.submit"): return
            pid=(f.get("property_id") or "").strip()
            cat=(f.get("category") or "Long Term Rental").strip()
            c=db()
            created, skipped, err = create_bulk_listing_requests(c, u, pid, cat, owner_account=u["account_number"])
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

    def log_message(self,fmt,*args):pass


