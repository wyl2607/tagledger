from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlmodel import Session

from backend.app.database import get_session
from backend.app.models import User
from backend.app.services.auth_service import (
    get_user_by_session_token,
    has_role,
)

session_dep = Depends(get_session)


def current_user_optional(
    mlocr_session: Annotated[str | None, Cookie()] = None,
    session: Session = session_dep,
) -> User | None:
    return get_user_by_session_token(session, mlocr_session)


current_user_optional_dep = Depends(current_user_optional)


def require_login(user: User | None = current_user_optional_dep) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    return user


def require_role(required_role: str):
    require_login_dep = Depends(require_login)

    def dependency(user: User = require_login_dep) -> User:
        if has_role(user, required_role):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")

    return dependency


require_login_dep = Depends(require_login)


def require_supervisor(user: User = require_login_dep) -> User:
    if has_role(user, "supervisor"):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="需要主管或管理员权限 / Supervisor or manager permission required",
    )


def require_manager(user: User = require_login_dep) -> User:
    if has_role(user, "manager"):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
