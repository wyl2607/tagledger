(function initAuthUI(global) {
  function parseJsonText(text, status) {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (_error) {
      return { detail: text || `HTTP ${status}` };
    }
  }

  function nextPathOrCurrent(nextPath) {
    if (typeof nextPath === 'string' && nextPath) {
      return nextPath;
    }
    return window.location.pathname;
  }

  function cookieValue(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    return document.cookie
      .split(';')
      .map((item) => item.trim())
      .find((item) => item.startsWith(prefix))
      ?.slice(prefix.length) || '';
  }

  function csrfHeaders(options) {
    const method = String(options?.method || 'GET').toUpperCase();
    if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) return options || {};
    const token = cookieValue('tagledger_csrf');
    if (!token) return options || {};
    const headers = new Headers(options?.headers || {});
    headers.set('X-CSRF-Token', token);
    return { ...(options || {}), headers };
  }

  const AuthUI = {
    loginPath(nextPath) {
      return `/login?next=${encodeURIComponent(nextPathOrCurrent(nextPath))}`;
    },

    redirectToLogin(nextPath) {
      window.location.href = this.loginPath(nextPath);
    },

    async fetchJson(url, options) {
      const response = await fetch(url, csrfHeaders(options));
      const text = await response.text();
      const data = parseJsonText(text, response.status);
      if (response.status === 401) {
        this.redirectToLogin();
        const error = new Error('login required');
        error.status = 401;
        throw error;
      }
      if (!response.ok) {
        const error = new Error(data?.detail || `HTTP ${response.status}`);
        error.status = response.status;
        error.payload = data;
        throw error;
      }
      return data;
    },

    async currentUser() {
      const payload = await this.fetchJson('/api/auth/me');
      return payload?.user || null;
    },

    hasCapability(user, capabilityName) {
      return Boolean(user?.capabilities?.[capabilityName]);
    },

    async logout() {
      try {
        await this.fetchJson('/api/auth/logout', { method: 'POST' });
      } catch (_error) {
        // keep historical behavior: ignore logout errors and continue navigation
      }
    },

    csrfHeaders,
  };

  global.AuthUI = AuthUI;
})(window);
