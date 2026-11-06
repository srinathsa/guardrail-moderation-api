/* Shared helpers for the JWT-protected dashboard pages
   (review.html, analytics.html, admin.html). */

function guardrailRequireAuth() {
  const token = localStorage.getItem('guardrail_token');
  if (!token) {
    window.location.href = '/login';
    return null;
  }
  return {
    token,
    username: localStorage.getItem('guardrail_username') || '',
    role: localStorage.getItem('guardrail_role') || '',
    baseUrl: localStorage.getItem('guardrail_base_url') || window.location.origin,
  };
}

function guardrailLogout() {
  localStorage.removeItem('guardrail_token');
  localStorage.removeItem('guardrail_username');
  localStorage.removeItem('guardrail_role');
  window.location.href = '/login';
}

function guardrailRenderNavbar(activePage, session) {
  const isAdmin = session.role === 'admin';
  const links = [
    { href: '/', label: 'Live Feed', show: true },
    { href: '/review', label: 'Review', show: true },
    { href: '/analytics', label: 'Analytics', show: true },
    { href: '/admin', label: 'Admin', show: isAdmin },
    { href: '/demo', label: 'API Demo', show: true },
  ];
  const linksHtml = links
    .filter(l => l.show)
    .map(l => `<a href="${l.href}" class="${l.href === activePage ? 'active' : ''}">${l.label}</a>`)
    .join('');

  return `
    <div class="navbar">
      <div class="brand">
        <div class="logo">🛡️</div>
        Guardrail
      </div>
      <nav>${linksHtml}</nav>
      <div class="userbox">
        <span>${session.username}</span>
        <span class="role-badge">${session.role}</span>
        <button class="logout" onclick="guardrailLogout()">Sign out</button>
      </div>
    </div>
  `;
}

async function guardrailApiFetch(session, path, options = {}) {
  const headers = Object.assign({}, options.headers || {}, {
    'Authorization': `Bearer ${session.token}`,
  });
  const res = await fetch(`${session.baseUrl}${path}`, { ...options, headers });
  if (res.status === 401) {
    guardrailLogout();
    throw new Error('Session expired');
  }
  return res;
}

function guardrailShowToast(message) {
  let toast = document.getElementById('guardrailToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'guardrailToast';
    toast.className = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(window._guardrailToastTimer);
  window._guardrailToastTimer = setTimeout(() => toast.classList.remove('show'), 2500);
}

function guardrailEsc(s) {
  const d = document.createElement('div');
  d.innerText = s ?? '';
  return d.innerHTML;
}
