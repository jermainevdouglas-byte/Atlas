"""PublicHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class PublicHandlerMixin:
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
            rows=[dict(r)for r in c.execute(
                "SELECT id AS unit_id,unit_label,is_occupied,COALESCE(rent,0) AS rent,COALESCE(beds,0) AS beds,COALESCE(baths,0) AS baths "
                "FROM units WHERE property_id=? ORDER BY id",
                (pid,),
            ).fetchall()]
            c.close()
            return send_json(self,{"ok":True,"units":rows})

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
            sql = "SELECT * FROM listings WHERE id IN (" + marks + ") ORDER BY id DESC"
            rows = c.execute(sql, tuple(ids)).fetchall()
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
                        search_sections=empty_state("*", "Search AtlasBahamas", "Enter a keyword to search records.", "Go to Dashboard", role_home(role)),
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



