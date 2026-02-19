(() => {
  function showToast(title, message) {
    const toast = document.getElementById("atlasToast");
    if (!toast) return;

    const titleNode = toast.querySelector(".toast-title");
    const msgNode = toast.querySelector(".toast-msg");
    if (titleNode) titleNode.textContent = title;
    if (msgNode) msgNode.textContent = message;

    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2800);
  }

  function setNotice(node, kind, text) {
    if (!node) return;
    if (!text) {
      node.innerHTML = "";
      return;
    }
    const cls = kind === "error" ? "notice err" : kind === "ok" ? "notice ok" : "notice";
    node.innerHTML = `<div class="${cls}">${text}</div>`;
  }

  function money(value) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "$0.00";
  }

  function statusClass(status) {
    return `chip status-${String(status || "").replace(/_/g, "-").toLowerCase()}`;
  }

  function setText(selector, value) {
    const node = document.querySelector(selector);
    if (node) node.textContent = value;
  }

  function asMonthValue(date = new Date()) {
    const year = date.getUTCFullYear();
    const month = `${date.getUTCMonth() + 1}`.padStart(2, "0");
    return `${year}-${month}`;
  }

  function renderTenantPayments(list, payments) {
    if (!list) return;
    const rows = Array.isArray(payments) ? payments : [];
    if (!rows.length) {
      list.innerHTML = `<li class="workflow-item"><div class="workflow-meta">No payments submitted yet.</div></li>`;
      return;
    }

    list.innerHTML = "";
    rows.forEach((row) => {
      const li = document.createElement("li");
      li.className = "workflow-item";
      li.innerHTML = `
        <div class="workflow-item-row">
          <strong>${money(row.amount)}</strong>
          <span class="${statusClass(row.status)}">${row.status}</span>
        </div>
        <div class="workflow-meta">Month: ${row.paymentMonth} | Tenant: ${row.tenantName}</div>
        <div class="workflow-meta">${row.note ? row.note : "No note provided."}</div>
      `;
      list.appendChild(li);
    });
  }

  function renderTenantMaintenance(list, requests) {
    if (!list) return;
    const rows = Array.isArray(requests) ? requests : [];
    if (!rows.length) {
      list.innerHTML = `<li class="workflow-item"><div class="workflow-meta">No maintenance requests yet.</div></li>`;
      return;
    }

    list.innerHTML = "";
    rows.forEach((row) => {
      const li = document.createElement("li");
      li.className = "workflow-item";
      li.innerHTML = `
        <div class="workflow-item-row">
          <strong>${row.subject}</strong>
          <span class="${statusClass(row.status)}">${row.status}</span>
        </div>
        <div class="workflow-meta">Severity: ${row.severity} | Tenant: ${row.tenantName}</div>
        <div class="workflow-meta">${row.details}</div>
      `;
      list.appendChild(li);
    });
  }

  function renderLandlordPayments(list, payments) {
    if (!list) return;
    const rows = Array.isArray(payments) ? payments : [];
    if (!rows.length) {
      list.innerHTML = `<li class="workflow-item"><div class="workflow-meta">No pending payments.</div></li>`;
      return;
    }

    list.innerHTML = "";
    rows.forEach((row) => {
      const li = document.createElement("li");
      li.className = "workflow-item";
      li.setAttribute("data-payment-id", String(row.id));
      li.innerHTML = `
        <div class="workflow-item-row">
          <strong>${row.tenantName} (${row.tenantUsername})</strong>
          <span class="${statusClass(row.status)}">${row.status}</span>
        </div>
        <div class="workflow-meta">Amount: ${money(row.amount)} | Month: ${row.paymentMonth}</div>
        <div class="workflow-meta">${row.note ? row.note : "No tenant note."}</div>
        <div class="tiny-actions">
          <button class="tiny-btn" type="button" data-payment-action="received" data-payment-id="${row.id}">Mark Received</button>
          <button class="tiny-btn" type="button" data-payment-action="rejected" data-payment-id="${row.id}">Reject</button>
        </div>
      `;
      list.appendChild(li);
    });
  }

  function renderLandlordMaintenance(list, requests) {
    if (!list) return;
    const rows = Array.isArray(requests) ? requests : [];
    if (!rows.length) {
      list.innerHTML = `<li class="workflow-item"><div class="workflow-meta">No open maintenance items.</div></li>`;
      return;
    }

    list.innerHTML = "";
    rows.forEach((row) => {
      const li = document.createElement("li");
      li.className = "workflow-item";
      li.setAttribute("data-request-id", String(row.id));
      li.innerHTML = `
        <div class="workflow-item-row">
          <strong>${row.subject}</strong>
          <span class="${statusClass(row.status)}">${row.status}</span>
        </div>
        <div class="workflow-meta">Tenant: ${row.tenantName} (${row.tenantUsername}) | Severity: ${row.severity}</div>
        <div class="workflow-meta">${row.details}</div>
        <div class="tiny-actions">
          <select class="tiny-btn" data-request-status>
            <option value="open"${row.status === "open" ? " selected" : ""}>Open</option>
            <option value="in_progress"${row.status === "in_progress" ? " selected" : ""}>In Progress</option>
            <option value="resolved"${row.status === "resolved" ? " selected" : ""}>Resolved</option>
            <option value="closed"${row.status === "closed" ? " selected" : ""}>Closed</option>
          </select>
          <button class="tiny-btn" type="button" data-maintenance-update data-request-id="${row.id}">Update</button>
        </div>
      `;
      list.appendChild(li);
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const auth = window.AtlasBahamasAuth;
    if (!auth) return;

    await auth.ensureSeedUsers();

    const root = document.querySelector("[data-dashboard-root]");
    if (!root) return;

    const expectedRole = auth.normalizeRole(root.getAttribute("data-role") || "");
    const gate = await auth.requireRole(expectedRole);

    if (!gate.ok) {
      const loginHref = `AtlasBahamasLogin.html?role=${encodeURIComponent(expectedRole)}&next=${encodeURIComponent(window.location.pathname.split("/").pop())}`;
      root.innerHTML = `
        <div class="card unauthorized">
          <h2>Authentication required</h2>
          <p class="muted">Please sign in with a ${expectedRole || "valid"} account to access this dashboard.</p>
          <div><a class="primary-btn" href="${loginHref}">Go to Login</a></div>
        </div>
      `;
      return;
    }

    setText("[data-welcome-name]", gate.session.fullName || "User");
    const tenantNotice = document.getElementById("atlasTenantNotice");
    const landlordNotice = document.getElementById("atlasLandlordNotice");
    const notice = expectedRole === "landlord" ? landlordNotice : tenantNotice;

    async function refreshDashboard() {
      const dashboardResult = await auth.fetchDashboard(expectedRole);
      if (!dashboardResult.ok) {
        setNotice(notice, "error", `Dashboard sync failed: ${dashboardResult.error || "Unknown error."}`);
        return null;
      }

      const data = dashboardResult.data || {};
      const kpis = data.kpis || {};

      if (expectedRole === "tenant") {
        setText("[data-kpi-rent-due]", money(kpis.rentDue));
        setText("[data-kpi-days-to-due]", `${Number(kpis.daysToDue || 0)} day(s)`);
        setText("[data-kpi-open-requests]", String(Number(kpis.openRequests || 0)));
        setText("[data-kpi-receipts]", String(Number(kpis.receipts || 0)));
        renderTenantPayments(document.getElementById("tenantPaymentList"), data.payments || []);
        renderTenantMaintenance(document.getElementById("tenantMaintenanceList"), data.maintenance || []);
      } else {
        setText("[data-kpi-properties]", String(Number(kpis.properties || 0)));
        setText("[data-kpi-occupied]", String(Number(kpis.occupied || 0)));
        setText("[data-kpi-monthly-revenue]", money(kpis.monthlyRevenue));
        setText("[data-kpi-open-requests]", String(Number(kpis.openRequests || 0)));
        renderLandlordPayments(document.getElementById("landlordPaymentQueue"), data.pendingPayments || []);
        renderLandlordMaintenance(document.getElementById("landlordMaintenanceQueue"), data.maintenanceQueue || []);
      }

      return data;
    }

    const paymentForm = document.getElementById("tenantPaymentForm");
    if (paymentForm) {
      const monthInput = paymentForm.querySelector("input[name='payment_month']");
      if (monthInput && !monthInput.value) {
        monthInput.value = asMonthValue();
      }

      paymentForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        setNotice(notice, "", "");

        const submitButton = paymentForm.querySelector("button[type='submit']");
        if (submitButton) submitButton.disabled = true;
        const result = await auth.submitRentPayment({
          amount: paymentForm.amount.value,
          paymentMonth: paymentForm.payment_month.value,
          note: paymentForm.note.value
        });
        if (submitButton) submitButton.disabled = false;

        if (!result.ok) {
          setNotice(notice, "error", `Payment was not submitted: ${result.error}`);
          return;
        }

        setNotice(notice, "ok", "Payment submitted successfully.");
        showToast("Payment submitted", "Rent payment was sent to landlord review.");
        paymentForm.reset();
        if (monthInput) monthInput.value = asMonthValue();
        await refreshDashboard();
      });
    }

    const maintenanceForm = document.getElementById("tenantMaintenanceForm");
    if (maintenanceForm) {
      maintenanceForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        setNotice(notice, "", "");

        const submitButton = maintenanceForm.querySelector("button[type='submit']");
        if (submitButton) submitButton.disabled = true;
        const result = await auth.createMaintenanceRequest({
          subject: maintenanceForm.subject.value,
          details: maintenanceForm.details.value,
          severity: maintenanceForm.severity.value
        });
        if (submitButton) submitButton.disabled = false;

        if (!result.ok) {
          setNotice(notice, "error", `Maintenance request failed: ${result.error}`);
          return;
        }

        setNotice(notice, "ok", "Maintenance request submitted.");
        showToast("Request submitted", "Your maintenance request is now in the landlord queue.");
        maintenanceForm.reset();
        await refreshDashboard();
      });
    }

    root.addEventListener("click", async (event) => {
      const payButton = event.target.closest("[data-payment-action]");
      if (payButton) {
        const paymentId = payButton.getAttribute("data-payment-id");
        const action = payButton.getAttribute("data-payment-action");
        if (!paymentId || !action) return;
        payButton.disabled = true;
        const result = await auth.reviewPayment(paymentId, action, "");
        payButton.disabled = false;
        if (!result.ok) {
          setNotice(notice, "error", `Payment update failed: ${result.error}`);
          return;
        }
        setNotice(notice, "ok", `Payment ${paymentId} marked as ${action}.`);
        showToast("Payment reviewed", `Payment ${paymentId} updated to ${action}.`);
        await refreshDashboard();
        return;
      }

      const maintenanceButton = event.target.closest("[data-maintenance-update]");
      if (maintenanceButton) {
        const requestId = maintenanceButton.getAttribute("data-request-id");
        if (!requestId) return;
        const card = maintenanceButton.closest("[data-request-id]");
        const select = card ? card.querySelector("[data-request-status]") : null;
        const status = select ? select.value : "";
        maintenanceButton.disabled = true;
        const result = await auth.updateMaintenanceStatus(requestId, status);
        maintenanceButton.disabled = false;
        if (!result.ok) {
          setNotice(notice, "error", `Maintenance update failed: ${result.error}`);
          return;
        }
        setNotice(notice, "ok", `Request ${requestId} updated to ${status}.`);
        showToast("Maintenance updated", `Request ${requestId} is now ${status}.`);
        await refreshDashboard();
      }
    });

    await refreshDashboard();
  });
})();
