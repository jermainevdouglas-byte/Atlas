"""LandlordHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class LandlordHandlerMixin:
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
                before_sql = "SELECT COUNT(1) AS n FROM units WHERE " + where
                before = c.execute(before_sql, tuple(args)).fetchone()["n"]
                affected = 0
                if to_int(before, 0) > 0:
                    if action=="set_rent":
                        cur=c.execute("UPDATE units SET rent=? WHERE " + where, tuple([rent] + args))
                        affected = to_int(cur.rowcount, to_int(before, 0))
                        if affected < 0:
                            affected = to_int(before, 0)
                    elif action=="increase_amount":
                        cur=c.execute("UPDATE units SET rent=MAX(0,rent+?) WHERE " + where, tuple([rent] + args))
                        affected = to_int(cur.rowcount, to_int(before, 0))
                        if affected < 0:
                            affected = to_int(before, 0)
                    elif action=="increase_percent":
                        cur=c.execute(
                            "UPDATE units SET rent=CAST(ROUND(rent * (1 + (? / 100.0))) AS INTEGER) WHERE " + where,
                            tuple([rent] + args),
                        )
                        affected = to_int(cur.rowcount, to_int(before, 0))
                        if affected < 0:
                            affected = to_int(before, 0)
                    elif action=="mark_occupied":
                        cur=c.execute("UPDATE units SET is_occupied=1 WHERE " + where, tuple(args))
                        affected = to_int(cur.rowcount, to_int(before, 0))
                        if affected < 0:
                            affected = to_int(before, 0)
                    elif action=="mark_vacant":
                        cur=c.execute(
                            "UPDATE units SET is_occupied=0 WHERE " + where + " "
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


