import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from backend.app.models import AuditLog, SecuritySecret, User, UserSession, utc_now

ROLE_LEVELS = {
    "operator": 1,
    "supervisor": 2,
    "manager": 3,
    "it_admin": 3,
    "auditor": 1,
}

SESSION_COOKIE = "mlocr_session"
SESSION_HOURS = 12


def hash_password(password: str, *, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"pbkdf2_sha256$200000${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def users_exist(session: Session) -> bool:
    return session.exec(select(User.id).limit(1)).first() is not None


def normalize_assigned_order_no(value: str | None) -> str | None:
    cleaned = "".join(ch for ch in (value or "").upper() if ch.isalnum())
    if not cleaned:
        return None
    if cleaned.startswith("5"):
        cleaned = "S" + cleaned[1:]
    return cleaned[:80]


def audit_event(
    session: Session,
    *,
    event_type: str,
    action: str,
    actor: User | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    reason: str | None = None,
    success: bool = True,
    detail: dict[str, object] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    row = AuditLog(
        event_type=event_type,
        actor_user_id=actor.id if actor else None,
        actor_username=actor.username if actor else None,
        target_type=target_type,
        target_id=target_id,
        action=action,
        reason=reason,
        success=success,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def create_user(
    session: Session,
    *,
    username: str,
    display_name: str,
    password: str,
    role: str,
    actor: User | None = None,
    outbound_last_order_no: str | None = None,
) -> User:
    username = username.strip().lower()
    if not username:
        raise RuntimeError("username is required")
    if role not in ROLE_LEVELS:
        raise RuntimeError(f"unknown role: {role}")
    if session.exec(select(User).where(User.username == username)).first() is not None:
        raise RuntimeError(f"user already exists: {username}")
    user = User(
        username=username,
        display_name=(display_name.strip() or username)[:120],
        password_hash=hash_password(password),
        role=role,
        status="active",
        outbound_last_order_no=normalize_assigned_order_no(outbound_last_order_no),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    audit_event(
        session,
        event_type="user_created",
        action="create_user",
        actor=actor,
        target_type="user",
        target_id=str(user.id),
        detail={
            "username": user.username,
            "role": user.role,
            "outbound_last_order_no": user.outbound_last_order_no,
        },
    )
    return user


def update_user_account(
    session: Session,
    *,
    user: User,
    actor: User,
    display_name: str | None = None,
    role: str | None = None,
    status: str | None = None,
    must_change_password: bool | None = None,
    outbound_last_order_no: str | None = None,
) -> User:
    if role is not None and role not in ROLE_LEVELS:
        raise RuntimeError(f"unknown role: {role}")
    if status is not None and status not in {"active", "disabled"}:
        raise RuntimeError(f"unknown status: {status}")
    changes: dict[str, object] = {}
    if display_name is not None:
        user.display_name = (display_name.strip() or user.username)[:120]
        changes["display_name"] = user.display_name
    if role is not None:
        user.role = role
        changes["role"] = role
    if status is not None:
        user.status = status
        changes["status"] = status
    if must_change_password is not None:
        user.must_change_password = must_change_password
        changes["must_change_password"] = must_change_password
    if outbound_last_order_no is not None:
        user.outbound_last_order_no = normalize_assigned_order_no(outbound_last_order_no)
        changes["outbound_last_order_no"] = user.outbound_last_order_no
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    session.refresh(user)
    audit_event(
        session,
        event_type="user_updated",
        action="update_user",
        actor=actor,
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username, "changes": changes},
    )
    return user


def change_password(
    session: Session,
    *,
    user: User,
    new_password: str,
    actor: User | None = None,
    current_password: str | None = None,
) -> None:
    if current_password is not None and not verify_password(current_password, user.password_hash):
        raise RuntimeError("current password is incorrect")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    audit_event(
        session,
        event_type="password_changed",
        action="change_password",
        actor=actor or user,
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username, "self_service": actor is None or actor.id == user.id},
    )


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.username == username.strip().lower())).first()
    if user is None or user.status != "active":
        return None
    return user if verify_password(password, user.password_hash) else None


def create_session(
    session: Session,
    user: User,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(32)
    row = UserSession(
        session_token_hash=token_hash(token),
        user_id=user.id or 0,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500],
        expires_at=datetime.now(UTC) + timedelta(hours=SESSION_HOURS),
    )
    user.last_login_at = utc_now()
    user.updated_at = utc_now()
    session.add(user)
    session.add(row)
    session.commit()
    session.refresh(row)
    audit_event(
        session,
        event_type="login",
        action="login",
        actor=user,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return token, row


def get_user_by_session_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = session.exec(
        select(UserSession).where(UserSession.session_token_hash == token_hash(token))
    ).first()
    if row is None or row.revoked_at is not None or as_utc(row.expires_at) <= datetime.now(UTC):
        return None
    user = session.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    row.last_seen_at = utc_now()
    session.add(row)
    session.commit()
    return user


def revoke_session(session: Session, token: str | None, reason: str = "logout") -> None:
    if not token:
        return
    row = session.exec(
        select(UserSession).where(UserSession.session_token_hash == token_hash(token))
    ).first()
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = utc_now()
    row.revoked_reason = reason
    session.add(row)
    session.commit()


def set_security_secret(
    session: Session,
    *,
    key: str,
    secret: str,
    actor: User,
) -> SecuritySecret:
    row = session.exec(select(SecuritySecret).where(SecuritySecret.key == key)).first()
    if row is None:
        row = SecuritySecret(key=key, secret_hash=hash_password(secret))
    else:
        row.secret_hash = hash_password(secret)
    row.updated_by_user_id = actor.id
    row.updated_at = utc_now()
    session.add(row)
    session.commit()
    session.refresh(row)
    audit_event(
        session,
        event_type="security_secret_updated",
        action="set_security_secret",
        actor=actor,
        target_type="security_secret",
        target_id=key,
    )
    return row


def verify_security_secret(session: Session, *, key: str, secret: str | None) -> bool:
    if not secret:
        return False
    row = session.exec(select(SecuritySecret).where(SecuritySecret.key == key)).first()
    return bool(row and verify_password(secret, row.secret_hash))


def has_role(user: User, required_role: str) -> bool:
    return ROLE_LEVELS.get(user.role, 0) >= ROLE_LEVELS.get(required_role, 999)
