"""BaseHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class BaseHandlerMixin:
        def _absolute_url(self, path):
            p = path if str(path).startswith("/") else f"/{path}"
            if PUBLIC_BASE_URL:
                return f"{PUBLIC_BASE_URL.rstrip('/')}{p}"
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
                log_exception("request_failed", scope="http_get", path=self.path, method="GET", alert_key="http_get_error")
                try:e500(self)
                except:pass
            finally:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                if elapsed_ms >= 800:
                    log_event(logging.WARNING, "slow_request", method="GET", path=self.path, elapsed_ms=elapsed_ms)

        def do_POST(self):
            start = time.perf_counter()
            try:self._post()
            except Exception:
                log_exception("request_failed", scope="http_post", path=self.path, method="POST", alert_key="http_post_error")
                try:e500(self)
                except:pass
            finally:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                if elapsed_ms >= 800:
                    log_event(logging.WARNING, "slow_request", method="POST", path=self.path, elapsed_ms=elapsed_ms)

        def _get(self):
            if self._https_redirect_if_needed():
                return
            run_housekeeping_if_due()
            parsed=urlparse(self.path);path=parsed.path;q=parse_qs(parsed.query);u=cur_user(self.headers)
            if path=="/health":
                return send_json(self, {
                    "ok": True,
                    "service": "atlas",
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
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

        def log_message(self,fmt,*args):pass


