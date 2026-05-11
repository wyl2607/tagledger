#!/usr/bin/env python3
"""Create or repair a local TagLedger user account.

Use this for local/Windows site setup tasks where operators need a daily
assigned outbound order. Passwords are read from TAGLEDGER_USER_PASSWORD or
from an interactive prompt so they are not stored in source files or shell
history by default.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlmodel import Session, select  # noqa: E402

from backend.app.database import create_db_and_tables, engine  # noqa: E402
from backend.app.models import User  # noqa: E402
from backend.app.services.auth_service import (  # noqa: E402
    change_password,
    create_user,
    update_user_account,
)
from backend.app.services.outbound_reconciliation import normalize_order_no  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", default=None)
    parser.add_argument(
        "--role", default="operator", choices=["operator", "auditor", "supervisor", "manager"]
    )
    parser.add_argument(
        "--orders",
        default="",
        help="Comma-separated outbound orders assigned to this account. Repeat the same order for multiple users by running the script for each user.",
    )
    parser.add_argument(
        "--password-env",
        default="TAGLEDGER_USER_PASSWORD",
        help="Environment variable that contains the password. Prompts if unset.",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Reset password for an existing user. New users always receive the supplied password.",
    )
    parser.add_argument(
        "--must-change-password",
        action="store_true",
        help="Mark the account so the UI can require changing the seeded password.",
    )
    return parser.parse_args()


def normalize_orders(value: str) -> str:
    orders: list[str] = []
    seen: set[str] = set()
    for raw in value.replace("，", ",").replace(";", ",").split(","):
        order = normalize_order_no(raw)
        if not order or order in seen:
            continue
        orders.append(order)
        seen.add(order)
    return ",".join(orders)


def password_from_env_or_prompt(env_name: str) -> str:
    import os

    password = os.environ.get(env_name)
    if not password:
        password = getpass.getpass(f"{env_name}: ")
    if len(password) < 10:
        raise SystemExit("password must be at least 10 characters")
    return password


def main() -> int:
    args = parse_args()
    password = password_from_env_or_prompt(args.password_env)
    username = args.username.strip().lower()
    display_name = args.display_name or username
    assigned_orders = normalize_orders(args.orders)

    create_db_and_tables()
    with Session(engine) as session:
        manager = session.exec(select(User).where(User.role.in_(["manager", "it_admin"]))).first()
        user = session.exec(select(User).where(User.username == username)).first()

        if user is None:
            user = create_user(
                session,
                username=username,
                display_name=display_name,
                password=password,
                role=args.role,
                actor=manager,
                outbound_last_order_no=assigned_orders,
            )
            action = "created"
        else:
            if manager is None:
                manager = user
            user = update_user_account(
                session,
                user=user,
                actor=manager,
                display_name=display_name,
                role=args.role,
                status="active",
                outbound_last_order_no=assigned_orders,
            )
            if args.reset_password:
                change_password(session, user=user, new_password=password, actor=manager)
            action = "updated"

        if args.must_change_password:
            user.must_change_password = True
            session.add(user)
            session.commit()
            session.refresh(user)

        print(f"{action}: {user.username}")
        print(f"role: {user.role}")
        print(f"status: {user.status}")
        print(f"assigned_orders: {user.outbound_last_order_no or ''}")
        print(f"must_change_password: {user.must_change_password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
