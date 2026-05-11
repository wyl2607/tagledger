import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from backend.app.auth import current_user_optional, require_manager
from backend.app.config import get_settings
from backend.app.database import get_session
from backend.app.models import AuditLog, OutboundScan, Record, User, utc_now
from backend.app.services.auth_service import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    SESSION_HOURS,
    authenticate_user,
    create_session,
    create_user,
    has_role,
    normalize_assigned_order_numbers,
    revoke_session,
    update_user_account,
    users_exist,
)
from backend.app.services.outbound_reconciliation import normalize_order_no

router = APIRouter(prefix="/api/auth")
admin_router = APIRouter(prefix="/api/admin")
workbench_router = APIRouter(prefix="/api")


class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    display_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=10, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    display_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=10, max_length=256)
    role: str = "operator"
    outbound_last_order_no: str | None = Field(default=None, max_length=80)


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = None
    status: str | None = None
    must_change_password: bool | None = None
    outbound_last_order_no: str | None = Field(default=None, max_length=80)


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=10, max_length=256)


def _user_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "status": user.status,
        "outbound_last_order_no": user.outbound_last_order_no,
        "capabilities": {
            "can_view_global_stats": has_role(user, "supervisor"),
            "can_manage_inventory": has_role(user, "supervisor"),
            "can_manage_transfers": has_role(user, "supervisor"),
            "can_manage_users": has_role(user, "manager"),
            "can_view_audit_logs": has_role(user, "manager"),
            "can_manage_signoff": has_role(user, "supervisor") or has_role(user, "manager"),
        },
        "must_change_password": user.must_change_password,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_HOURS * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=SESSION_HOURS * 60 * 60,
        httponly=False,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )


@router.get("/setup-status")
def setup_status(session: Session = Depends(get_session)) -> dict[str, bool]:
    return {"initialized": users_exist(session)}


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup_first_manager(
    payload: SetupRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if users_exist(session):
        raise HTTPException(status_code=409, detail="system already initialized")
    user = create_user(
        session,
        username=payload.username,
        display_name=payload.display_name or payload.username,
        password=payload.password,
        role="manager",
    )
    token, _ = create_session(
        session,
        user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, token)
    return {"user": _user_payload(user)}


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    user = authenticate_user(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login failed")
    token, _ = create_session(
        session,
        user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, token)
    return {"user": _user_payload(user)}


@router.post("/logout")
def logout(
    response: Response,
    mlocr_session: Annotated[str | None, Cookie()] = None,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    revoke_session(session, mlocr_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User | None = Depends(current_user_optional)) -> dict[str, object | None]:
    return {"user": _user_payload(user) if user else None}


@router.get("/current-user")
def current_user(user: User | None = Depends(current_user_optional)) -> dict[str, object | None]:
    return me(user)


def _fallback_order_no(order_numbers: list[str]) -> str | None:
    cleaned = [normalize_order_no(order) for order in order_numbers if normalize_order_no(order)]
    return sorted(cleaned)[-1] if cleaned else None


def _allowed_order_numbers(user: User) -> list[str] | None:
    if has_role(user, "supervisor"):
        return None
    return normalize_assigned_order_numbers(user.outbound_last_order_no)


def _module_payload(user: User) -> list[dict[str, object]]:
    modules = [
        {
            "id": "mobile",
            "title": "手机扫码",
            "description": "现场扫码、拍照、录入当前发货单。",
            "href": "/mobile",
            "group": "today",
        },
        {
            "id": "outbound",
            "title": "我的发货单",
            "description": "只显示分配给当前账号的发货单和核对进度。",
            "href": "/outbound",
            "group": "today",
        },
        {
            "id": "my_stats",
            "title": "我的近 7 天",
            "description": "查看本人扫码数量和最近作业趋势。",
            "href": "/workbench#my-stats",
            "group": "records",
        },
    ]
    if has_role(user, "supervisor"):
        modules.extend(
            [
                {
                    "id": "inbound",
                    "title": "采购入库",
                    "description": "按物料、库位和数量登记来料。",
                    "href": "/inbound",
                    "group": "inventory",
                },
                {
                    "id": "inventory",
                    "title": "库存与库位",
                    "description": "按工厂、物料和库位查看库存，手工调整数量或挪动库位。",
                    "href": "/inventory",
                    "group": "inventory",
                },
                {
                    "id": "transfers",
                    "title": "跨场子调拨",
                    "description": "发起和查看三场子调拨流水。",
                    "href": "/transfers",
                    "group": "inventory",
                },
                {
                    "id": "dashboard",
                    "title": "全局录入统计",
                    "description": "查看整体录入、OCR 和出库处理指标。",
                    "href": "/dashboard",
                    "group": "records",
                },
                {
                    "id": "signoff",
                    "title": "退货签核",
                    "description": "查看候选单、生成配对链接，并跟踪人工处理状态。",
                    "href": "/signoff",
                    "group": "admin",
                },
            ]
        )
    if has_role(user, "manager"):
        modules.extend(
            [
                {
                    "id": "signoff",
                    "title": "退货签核",
                    "description": "查看候选单、生成配对链接，并跟踪人工处理状态。",
                    "href": "/signoff",
                    "group": "admin",
                },
                {
                    "id": "admin",
                    "title": "账号与权限",
                    "description": "管理账号等级、停用账号和重置密码。",
                    "href": "/admin",
                    "group": "admin",
                },
            ]
        )
    return modules


def _my_stats_payload(
    session: Session,
    *,
    user: User,
    allowed_orders: list[str] | None,
    days: int = 7,
) -> dict[str, object]:
    since = utc_now() - timedelta(days=days)
    statement = select(OutboundScan).where(
        OutboundScan.operator_id == user.username,
        OutboundScan.status == "active",
        OutboundScan.created_at >= since,
    )
    if allowed_orders is not None:
        statement = statement.where(OutboundScan.order_no.in_(allowed_orders))
    rows = session.exec(statement).all()
    daily: dict[str, dict[str, int]] = {}
    for row in rows:
        key = row.created_at.date().isoformat()
        daily.setdefault(key, {"scan_count": 0, "quantity": 0})
        daily[key]["scan_count"] += 1
        daily[key]["quantity"] += int(row.quantity or 0)
    return {
        "days": days,
        "scan_count": len(rows),
        "scan_quantity": sum(int(row.quantity or 0) for row in rows),
        "daily": [{"date": date, **values} for date, values in sorted(daily.items(), reverse=True)],
    }


def _global_stats_payload(session: Session) -> dict[str, object]:
    from backend.app.services import outbound_reconciliation

    try:
        choices = outbound_reconciliation.outbound_order_choices()
    except RuntimeError:
        choices = {"order_numbers": {"shipping": []}}
    orders = choices.get("order_numbers", {}).get("shipping", [])
    scan_count = session.exec(
        select(func.count()).select_from(OutboundScan).where(OutboundScan.status == "active")
    ).one()
    scan_quantity = session.exec(
        select(func.coalesce(func.sum(OutboundScan.quantity), 0)).where(
            OutboundScan.status == "active"
        )
    ).one()
    record_count = session.exec(select(func.count()).select_from(Record)).one()
    return {
        "order_count": len(orders) if isinstance(orders, list) else 0,
        "scan_count": int(scan_count or 0),
        "scan_quantity": int(scan_quantity or 0),
        "record_count": int(record_count or 0),
    }


@workbench_router.get("/workbench")
def workbench(
    user: User = Depends(current_user_optional),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    allowed_orders = _allowed_order_numbers(user)
    return {
        "user": _user_payload(user),
        "scope": {
            "kind": "global" if allowed_orders is None else "assigned_orders",
            "allowed_order_numbers": allowed_orders,
        },
        "modules": _module_payload(user),
        "my_stats": _my_stats_payload(
            session,
            user=user,
            allowed_orders=allowed_orders,
        ),
        "global_stats": _global_stats_payload(session) if has_role(user, "supervisor") else None,
    }


@admin_router.get("/users")
def list_users(
    _: User = Depends(require_manager),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    return {"users": [_user_payload(user) for user in users]}


@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
def create_account(
    payload: UserCreateRequest,
    actor: User = Depends(require_manager),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        user = create_user(
            session,
            username=payload.username,
            display_name=payload.display_name or payload.username,
            password=payload.password,
            role=payload.role,
            actor=actor,
            outbound_last_order_no=payload.outbound_last_order_no,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"user": _user_payload(user)}


@admin_router.patch("/users/{user_id}")
def update_account(
    user_id: int,
    payload: UserUpdateRequest,
    actor: User = Depends(require_manager),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    try:
        updated = update_user_account(
            session,
            user=user,
            actor=actor,
            display_name=payload.display_name,
            role=payload.role,
            status=payload.status,
            must_change_password=payload.must_change_password,
            outbound_last_order_no=payload.outbound_last_order_no,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"user": _user_payload(updated)}


@admin_router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: PasswordResetRequest,
    actor: User = Depends(require_manager),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    from backend.app.services.auth_service import change_password

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    change_password(session, user=user, new_password=payload.password, actor=actor)
    user.must_change_password = True
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"user": _user_payload(user)}


@admin_router.get("/audit-logs")
def list_audit_logs(
    _: User = Depends(require_manager),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    rows = session.exec(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(50)).all()
    return {
        "logs": [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "event_type": row.event_type,
                "action": row.action,
                "actor_username": row.actor_username,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "success": row.success,
            }
            for row in rows
        ]
    }
