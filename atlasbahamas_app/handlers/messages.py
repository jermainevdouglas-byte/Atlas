"""MessagesHandlerMixin extracted from legacy handler."""
from .. import core as _core

# Pull all core symbols (including private helpers) into this module namespace
# so legacy handler code remains behavior-compatible after modularization.
globals().update({k: v for k, v in vars(_core).items() if k not in ("__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__")})


class MessagesHandlerMixin:
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



