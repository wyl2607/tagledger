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


def main():
    parser = argparse.ArgumentParser("tagledger-server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir")
    parser.add_argument("--log-dir")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["TAGLEDGER_DATA_DIR"] = args.data_dir
    if args.log_dir:
        os.environ["TAGLEDGER_LOG_DIR"] = args.log_dir

    port = pick_free_port(args.host, args.port)

    runtime = Path(args.data_dir or ".") / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "port").write_text(str(port))

    from backend.app.pairing import get_pair_token

    pair_token_path = runtime / "pair_token"
    pair_token_path.write_text(get_pair_token() or "")
    try:
        os.chmod(pair_token_path, 0o600)
    except OSError:
        pass

    root_logger = logging.getLogger()
    root_logger.addFilter(_TokenRedactingFilter())

    import uvicorn

    uvicorn.run("backend.app.main:app", host=args.host, port=port, log_level="info")
