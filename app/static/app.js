// AYX Laundry MVP frontend.
// Talks to the FastAPI backend on the same origin this file is served from,
// so no API base URL configuration is needed when served by app/main.py.

const API_BASE = "";

const state = {
  mode: "customer", // "customer" | "admin"
  userToken: localStorage.getItem("ayx_user_token") || null,
  adminToken: localStorage.getItem("ayx_admin_token") || null,
};

// ---------- generic fetch helper ----------

async function apiFetch(path, { method = "GET", body, token, form } = {}) {
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let fetchBody;
  if (form) {
    // OAuth2PasswordRequestForm endpoints expect x-www-form-urlencoded
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    fetchBody = new URLSearchParams(body).toString();
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    fetchBody = JSON.stringify(body);
  }

  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: fetchBody });
  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    /* no body */
  }
  if (!res.ok) {
    const detail = (data && data.detail) || res.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function setMsg(el, text, type) {
  el.textContent = text || "";
  el.className = "form-msg" + (type ? ` ${type}` : "");
}

// ---------- mode switching ----------

const customerView = document.getElementById("customer-view");
const adminView = document.getElementById("admin-view");
const modeCustomerBtn = document.getElementById("mode-customer");
const modeAdminBtn = document.getElementById("mode-admin");
const sessionLabel = document.getElementById("session-label");
const logoutBtn = document.getElementById("logout-btn");

function setMode(mode) {
  state.mode = mode;
  modeCustomerBtn.classList.toggle("active", mode === "customer");
  modeAdminBtn.classList.toggle("active", mode === "admin");
  customerView.classList.toggle("hidden", mode !== "customer");
  adminView.classList.toggle("hidden", mode !== "admin");
  renderSession();
}

modeCustomerBtn.addEventListener("click", () => setMode("customer"));
modeAdminBtn.addEventListener("click", () => setMode("admin"));

function renderSession() {
  if (state.mode === "customer" && state.userToken) {
    sessionLabel.textContent = "Signed in";
    logoutBtn.classList.remove("hidden");
    document.getElementById("customer-auth").classList.add("hidden");
    document.getElementById("customer-dashboard").classList.remove("hidden");
  } else if (state.mode === "admin" && state.adminToken) {
    sessionLabel.textContent = "Admin signed in";
    logoutBtn.classList.remove("hidden");
    document.getElementById("admin-auth").classList.add("hidden");
    document.getElementById("admin-dashboard").classList.remove("hidden");
  } else {
    sessionLabel.textContent = "Not signed in";
    logoutBtn.classList.add("hidden");
    if (state.mode === "customer") {
      document.getElementById("customer-auth").classList.remove("hidden");
      document.getElementById("customer-dashboard").classList.add("hidden");
    } else {
      document.getElementById("admin-auth").classList.remove("hidden");
      document.getElementById("admin-dashboard").classList.add("hidden");
    }
  }
}

logoutBtn.addEventListener("click", () => {
  if (state.mode === "customer") {
    state.userToken = null;
    localStorage.removeItem("ayx_user_token");
  } else {
    state.adminToken = null;
    localStorage.removeItem("ayx_admin_token");
  }
  renderSession();
});

// ---------- customer auth tabs ----------

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`${btn.dataset.tab}-form`).classList.add("active");
  });
});

// ---------- customer: register ----------

document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("register-msg");
  setMsg(msg, "");
  try {
    await apiFetch("/auth/register", {
      method: "POST",
      body: {
        full_name: document.getElementById("register-name").value,
        email: document.getElementById("register-email").value,
        password: document.getElementById("register-password").value,
      },
    });
    setMsg(msg, "Account created. You can log in now.", "success");
    e.target.reset();
  } catch (err) {
    setMsg(msg, err.message, "error");
  }
});

// ---------- customer: login ----------

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("login-msg");
  setMsg(msg, "");
  try {
    const data = await apiFetch("/auth/login", {
      method: "POST",
      form: true,
      body: {
        username: document.getElementById("login-email").value,
        password: document.getElementById("login-password").value,
      },
    });
    state.userToken = data.access_token;
    localStorage.setItem("ayx_user_token", state.userToken);
    renderSession();
    loadPlans();
    loadSubscriptionStatus();
    loadMyOrders();
  } catch (err) {
    setMsg(msg, err.message, "error");
  }
});

// ---------- customer: plans + subscribe ----------

async function loadPlans() {
  const grid = document.getElementById("plans-grid");
  grid.innerHTML = "Loading plans...";
  try {
    const plans = await apiFetch("/auth/plans");
    grid.innerHTML = "";
    plans.forEach((p) => {
      const div = document.createElement("div");
      div.className = "plan-card";
      div.innerHTML = `
        <h3>${p.plan}</h3>
        <p>${p.description}</p>
        <p>${p.pickups_per_period ? p.pickups_per_period + " pickups/period" : "Unlimited pickups"}</p>
        <button data-plan="${p.plan}">Subscribe</button>
      `;
      div.querySelector("button").addEventListener("click", () => subscribe(p.plan));
      grid.appendChild(div);
    });
  } catch (err) {
    grid.innerHTML = `<p class="form-msg error">${err.message}</p>`;
  }
}

async function subscribe(plan) {
  const msg = document.getElementById("subscribe-msg");
  setMsg(msg, "");
  try {
    await apiFetch("/subscriptions/subscribe", {
      method: "POST",
      token: state.userToken,
      body: { plan },
    });
    setMsg(msg, `Subscribed to ${plan}.`, "success");
    loadSubscriptionStatus();
  } catch (err) {
    setMsg(msg, err.message, "error");
  }
}

async function loadSubscriptionStatus() {
  const box = document.getElementById("subscription-status");
  try {
    const sub = await apiFetch("/subscriptions/status", { token: state.userToken });
    box.textContent = `Plan: ${sub.plan} · Status: ${sub.status} · Pickups used: ${sub.pickups_used_this_period}` +
      (sub.current_period_end ? ` · Renews/ends: ${new Date(sub.current_period_end).toLocaleString()}` : "");
  } catch (err) {
    box.textContent = "No active subscription yet — choose a plan below to get started.";
  }
}

// ---------- customer: book order ----------

document.getElementById("order-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("order-msg");
  setMsg(msg, "");
  try {
    const pickupTime = document.getElementById("order-pickup-time").value;
    const deliveryTime = document.getElementById("order-delivery-time").value;
    await apiFetch("/orders/", {
      method: "POST",
      token: state.userToken,
      body: {
        pickup_address: document.getElementById("order-address").value,
        pickup_time: new Date(pickupTime).toISOString(),
        delivery_time: deliveryTime ? new Date(deliveryTime).toISOString() : null,
        notes: document.getElementById("order-notes").value || null,
      },
    });
    setMsg(msg, "Pickup booked!", "success");
    e.target.reset();
    loadMyOrders();
    loadSubscriptionStatus();
  } catch (err) {
    setMsg(msg, err.message, "error");
  }
});

// ---------- customer: my orders ----------

async function loadMyOrders() {
  const tbody = document.getElementById("orders-table-body");
  tbody.innerHTML = "";
  try {
    const orders = await apiFetch("/orders/my", { token: state.userToken });
    if (orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4">No orders yet.</td></tr>`;
      return;
    }
    orders.forEach((o) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${o.pickup_address}</td>
        <td>${new Date(o.pickup_time).toLocaleString()}</td>
        <td>${o.status}</td>
        <td>${o.plan_at_booking}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="form-msg error">${err.message}</td></tr>`;
  }
}

document.getElementById("refresh-orders").addEventListener("click", loadMyOrders);

// ---------- admin: register / login ----------

document.getElementById("admin-register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("admin-register-msg");
  setMsg(msg, "");
  try {
    await apiFetch("/admin/register", {
      method: "POST",
      body: {
        full_name: document.getElementById("admin-reg-name").value,
        email: document.getElementById("admin-reg-email").value,
        password: document.getElementById("admin-reg-password").value,
      },
    });
    setMsg(msg, "Staff account created. Log in above.", "success");
    e.target.reset();
  } catch (err) {
    setMsg(msg, err.message, "error");
  }
});

document.getElementById("admin-login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("admin-login-msg");
  setMsg(msg, "");
  try {
    const data = await apiFetch("/admin/login", {
      method: "POST",
      form: true,
      body: {
        username: document.getElementById("admin-login-email").value,
        password: document.getElementById("admin-login-password").value,
      },
    });
    state.adminToken = data.access_token;
    localStorage.setItem("ayx_admin_token", state.adminToken);
    renderSession();
    loadAdminOrders();
  } catch (err) {
    setMsg(msg, err.message, "error");
  }
});

// ---------- admin: orders ----------

async function loadAdminOrders() {
  const tbody = document.getElementById("admin-orders-table-body");
  tbody.innerHTML = "";
  const statusFilter = document.getElementById("status-filter").value;
  const qs = statusFilter ? `?status_filter=${statusFilter}` : "";
  try {
    const orders = await apiFetch(`/admin/orders${qs}`, { token: state.adminToken });
    if (orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5">No orders found.</td></tr>`;
      return;
    }
    orders.forEach((o) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${o.pickup_address}</td>
        <td>${new Date(o.pickup_time).toLocaleString()}</td>
        <td>${o.status}</td>
        <td>${o.plan_at_booking}</td>
        <td></td>
      `;
      const select = document.createElement("select");
      ["PENDING", "PICKED_UP", "IN_PROGRESS", "DELIVERED", "CANCELLED"].forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s;
        if (s === o.status) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener("change", () => updateOrderStatus(o.id, select.value));
      tr.lastElementChild.appendChild(select);
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="form-msg error">${err.message}</td></tr>`;
  }
}

async function updateOrderStatus(orderId, newStatus) {
  try {
    await apiFetch(`/admin/orders/${orderId}/status`, {
      method: "PATCH",
      token: state.adminToken,
      body: { status: newStatus },
    });
    loadAdminOrders();
  } catch (err) {
    alert(`Failed to update status: ${err.message}`);
  }
}

document.getElementById("admin-refresh-orders").addEventListener("click", loadAdminOrders);
document.getElementById("status-filter").addEventListener("change", loadAdminOrders);

// ---------- init ----------

setMode("customer");
if (state.userToken) {
  loadPlans();
  loadSubscriptionStatus();
  loadMyOrders();
}
if (state.adminToken) {
  loadAdminOrders();
}
