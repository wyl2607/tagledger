from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from backend.app.database import get_session
from backend.app.services import metrics

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/summary")
def metrics_summary(session: Session = Depends(get_session)) -> dict:
    return metrics.summary(session)


@router.get("/throughput")
def metrics_throughput(
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> list[dict]:
    return metrics.daily_throughput(session, days=days)


@router.get("/processing-time")
def metrics_processing_time(session: Session = Depends(get_session)) -> dict:
    return metrics.avg_processing_time(session)


@router.get("/ocr-quality")
def metrics_ocr_quality(session: Session = Depends(get_session)) -> dict:
    return metrics.ocr_quality(session)


@router.get("/savings")
def metrics_savings(session: Session = Depends(get_session)) -> dict:
    return metrics.estimated_savings(session)


@router.get("/logistics")
def metrics_logistics(
    days: int = Query(default=7, ge=1, le=365),
    session: Session = Depends(get_session),
) -> dict:
    return metrics.logistics_metrics(session, days=days)


@router.get("/all")
def metrics_all(
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> dict:
    return metrics.all_metrics(session, days=days)
