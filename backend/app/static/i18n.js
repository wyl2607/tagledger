(function () {
  const SUPPORTED = ['en', 'de', 'zh'];
  const STORAGE_KEY = 'machine-label-ocr.locale';
  const state = {
    locale: 'en',
    messages: {},
    ready: null,
  };

  function normalizeLocale(value) {
    const lang = String(value || '').trim().toLowerCase();
    if (lang.startsWith('zh')) return 'zh';
    if (lang.startsWith('de')) return 'de';
    if (lang.startsWith('en')) return 'en';
    return '';
  }

  function localeFromUrl() {
    return normalizeLocale(new URLSearchParams(window.location.search).get('lang'));
  }

  function detectLocale() {
    return normalizeLocale(window.localStorage.getItem(STORAGE_KEY))
      || localeFromUrl()
      || normalizeLocale(window.navigator.language)
      || 'en';
  }

  async function loadLocale(locale) {
    const normalized = SUPPORTED.includes(locale) ? locale : 'en';
    const response = await fetch(`/static/i18n/${normalized}.json`, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`Unable to load locale ${normalized}`);
    state.messages = await response.json();
    state.locale = normalized;
    document.documentElement.lang = normalized === 'zh' ? 'zh-CN' : normalized;
    document.querySelectorAll('[data-locale]').forEach((button) => {
      const active = button.dataset.locale === normalized;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    return normalized;
  }

  function t(key, vars) {
    const template = state.messages[key] || key;
    return String(template).replace(/\{([^}]+)\}/g, (_, name) => {
      const value = vars && Object.prototype.hasOwnProperty.call(vars, name) ? vars[name] : '';
      return value == null ? '' : String(value);
    });
  }

  function applyDom(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-i18n]').forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    scope.querySelectorAll('[data-i18n-placeholder]').forEach((node) => {
      node.setAttribute('placeholder', t(node.dataset.i18nPlaceholder));
    });
    scope.querySelectorAll('[data-i18n-attr]').forEach((node) => {
      const attrs = node.dataset.i18nAttr.split(',').map((item) => item.trim()).filter(Boolean);
      for (const attr of attrs) {
        const key = node.getAttribute(`data-i18n-${attr}`)
          || node.dataset[`i18n${attr.replace(/(^|-)([a-z])/g, (_, __, char) => char.toUpperCase())}`]
          || node.dataset.i18n;
        if (key) node.setAttribute(attr, t(key));
      }
    });
    document.querySelectorAll('[data-locale]').forEach((button) => {
      const active = button.dataset.locale === state.locale;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }

  async function setLocale(locale) {
    const normalized = normalizeLocale(locale) || 'en';
    await loadLocale(normalized);
    window.localStorage.setItem(STORAGE_KEY, normalized);
    applyDom(document);
    window.dispatchEvent(new CustomEvent('i18n:change', { detail: { locale: normalized } }));
  }

  async function init() {
    if (state.ready) return state.ready;
    state.ready = loadLocale(detectLocale()).then((locale) => {
      applyDom(document);
      document.querySelectorAll('[data-locale]').forEach((button) => {
        button.addEventListener('click', () => setLocale(button.dataset.locale));
      });
      window.dispatchEvent(new CustomEvent('i18n:ready', { detail: { locale } }));
      return locale;
    });
    return state.ready;
  }

  window.I18n = {
    init,
    t,
    setLocale,
    applyDom,
    get locale() {
      return state.locale;
    },
  };
})();
