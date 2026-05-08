import argparse
import logging
import os
import socket
from pathlib import Path


class _TokenRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        from backend.app.pairing import get_pair_token

        token = get_pair_token()
        if token and isinstance(record.msg, str):
            record.msg = record.msg.replace(token, "<REDACTED>")
        if token and record.args:
            args = list(record.args)
            for i, arg in enumerate(args):
                if isinstance(arg, str):
                    args[i] = arg.replace(token, "<REDACTED>")
            record.args = tuple(args)
        return True


def pick_free_port(host: str, port: int) -> int:
    if port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, 0))
            return s.getsockname()[1]
    for candidate in range(port, port + 51):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, candidate))
                return candidate
        except OSError:
            continue
    raise RuntimeError(f"No free port in range {port}-{port + 50}")


def _write_secret(path: Path, content: str) -> None:
    path.write_text(content)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _configure_logging(log_dir: Path | None) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    redactor = _TokenRedactingFilter()
    root.addFilter(redactor)
    if log_dir is None:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "server.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(redactor)
    root.addHandler(handler)


def main():
    parser = argparse.ArgumentParser("tagledger-server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir")
    parser.add_argument("--log-dir")
    parser.add_argument(
        "--pair-token-out",
        help="Optional extra path to write the pair token (in addition to <data-dir>/runtime/pair_token).",
    )
    args = parser.parse_args()

    if args.data_dir:
        os.environ["TAGLEDGER_DATA_DIR"] = args.data_dir
    if args.log_dir:
        os.environ["TAGLEDGER_LOG_DIR"] = args.log_dir

    port = pick_free_port(args.host, args.port)

    runtime = Path(args.data_dir or ".") / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "port").write_text(str(port))
    (runtime / "pid").write_text(str(os.getpid()))

    from backend.app.pairing import get_pair_token

    token = get_pair_token() or ""
    _write_secret(runtime / "pair_token", token)
    if args.pair_token_out:
        _write_secret(Path(args.pair_token_out), token)

    log_dir = Path(args.log_dir) if args.log_dir else None
    _configure_logging(log_dir)

    import uvicorn

    uvicorn.run("backend.app.main:app", host=args.host, port=port, log_level="info")
