from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: print_lan_qr.py <url> [label]", file=sys.stderr)
        return 2
    url = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else "Scan URL"
    print()
    print(f"{label}: {url}")
    try:
        import qrcode
    except Exception:
        print("QR code unavailable: install with `python -m pip install qrcode[pil]`.")
        print()
        return 0

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    for row in qr.get_matrix():
        print("".join("██" if cell else "  " for cell in row))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
