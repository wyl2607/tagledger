# UI Revamp Notes

## Palette

- Background: `#fefefe`
- Primary orange: `#ff6b35`
- Primary hover: `#e25a25`
- Success: `#16a34a`
- Warning: `#facc15`
- Error: `#dc2626`
- Info: `#0284c7`
- Border: `#e5e5e5`
- Text: `#0a0a0a`

## Type And Controls

- Font stack: `-apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Source Han Sans", sans-serif`
- Body text: `18px`
- Buttons: `22px`, `56px` minimum height, `16px` radius, bold dark text
- Page titles: `28px`
- Status badges: `24px`
- Inputs/selects: `56px` minimum height, `12px` radius, `#e5e5e5` border, `2px #ff6b35` focus border
- Cards: `16px` radius and `0 4px 12px rgba(0,0,0,0.06)` shadow
- Spacing scale: `8 / 16 / 24 / 32 / 48`

## I18n Key Steps

1. Add the new flat dot key to `backend/app/static/i18n/zh.json`.
2. Add the same key to `en.json` and `de.json`.
3. Use `data-i18n="key"` for element text.
4. Use `data-i18n-placeholder="key"` for placeholders.
5. Use `data-i18n-attr="title"` plus `data-i18n-title="key"` for translated attributes.
6. Run `pytest backend/tests/test_i18n.py` to verify identical key sets and non-empty translations.

## Default Language

The default fallback is controlled in `backend/app/static/i18n.js`. `I18n.init()` resolves language in this order:

1. `localStorage` key `tagledger.locale`
2. `?lang=` URL parameter
3. `navigator.language`
4. `en`

Change the final fallback in `detectLocale()` to alter the default for first-time users whose browser language is unsupported.
