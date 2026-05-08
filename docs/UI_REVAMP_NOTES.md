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

## Mobile Capture Handoff

Baseline commit: `9167fc8 style(mobile): refine phone capture proportions`.

Validated devices:

- Pixel 10 Pro, Chrome, 1280 x 2856 physical, 385 dp effective width, browser `visualViewport.scale=1`.
- OPPO CPH2653, Chrome, 1440 x 3168 physical, 360 dp effective width, browser `visualViewport.scale=1`.

Current mobile capture intent:

- The first screen should prioritize scan work: category, runtime status, locator frame, photo action, gallery action, then outbound order context.
- The locator frame should stay visible and usable without pushing the photo buttons below the first viewport.
- The bottom sticky "upload and scan" action must stay hidden on the initial capture step because there is no selected photo yet.
- After gallery selection, the sticky upload action appears and remains the explicit upload path.
- Camera capture keeps auto-upload behavior after file selection.
- Outbound order context is secondary to scanning, but its select should remain reachable near the first screen for assigned-order operators.

Do not regress:

- Do not make the locator a fixed 420px block on phones; it makes Pixel/OPPO first-screen proportions feel wrong.
- Do not show the sticky upload bar before a file exists; it covers outbound content and looks like a duplicate primary action.
- Do not move outbound order controls above the locator on the capture step; operators need the camera target before order analytics.
- Do not use viewport-scaled font sizes. Keep text-size adjust locked and verify real `visualViewport.scale`.

Verification artifacts from the Pixel pass:

- `data/screenshots/adb-ui-audit/pixel-initial-adb.png`
- `data/screenshots/adb-ui-audit/pixel-gallery-selected-adb.png`
- `data/screenshots/adb-ui-audit/pixel-shipper-mobile.png`

Recommended validation for the next device pass:

1. Run `adb devices -l` and lock every command to the target serial with `adb -s <serial>`.
2. Use `adb reverse tcp:<port> tcp:<port>` so the phone Chrome opens the local dev server.
3. Measure `innerWidth`, `innerHeight`, `devicePixelRatio`, and `visualViewport.scale` through Chrome DevTools Protocol.
4. Capture two screenshots: initial capture screen and gallery-selected screen.
5. Run `scripts/browser_role_flow.py` plus `scripts/run_preflight.sh` before committing.
