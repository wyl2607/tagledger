# UI Style Guide

This UI is optimized for field operators using desktop and phone screens around physical machine labels.

## Palette

- Background: `#fefefe`
- Primary orange: `#ff6b35`
- Text: `#111`
- Success: `#16a34a`
- Warning: `#facc15`
- Error: `#dc2626`
- Info: `#0284c7`

## Typography

- Font stack: `-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', sans-serif`
- Body text: `18px`
- Buttons: `22px`
- Status badges: `24px`
- Avoid viewport-based font scaling. Keep letter spacing at `0`.

## Spacing And Shape

- Use the `8 / 16 / 24 / 32` spacing system.
- Buttons: height `56px`, radius `16px`, text color `#111`.
- Inputs and selects: height at least `56px`, radius `12px`, font size at least `18px`.
- Cards and panels: white surface, `16px` radius, border `#e5e5e5`, shadow only when floated: `0 1px 3px rgba(0,0,0,0.08)`.

## Layout Rules

- `demo.html`: desktop two-column card layout, upload on the left and result/board on the right.
- `history.html`: compact table layout, 48 x 48 thumbnails.
- `mobile.html`: full-width single-column phone flow with bottom-sticky actions.
- Mobile capture area: black camera frame with orange border.
- Primary action should be orange. Secondary actions use outline or plain white surfaces.
- Success and error feedback should use a top toast that auto-dismisses after 4 seconds.

## I18n Rules

- Translation files live in `backend/app/static/i18n/`.
- `zh.json` is the source of truth.
- Keys are flat and follow `<page>.<section>.<element>`.
- Use `data-i18n="key"` for text and `data-i18n-placeholder="key"` for placeholders.
- Runtime status names must cover `uploaded`, `ocr_done`, `confirmed`, `submitted`, `submission_failed`, `duplicate`, and `needs_review`.
