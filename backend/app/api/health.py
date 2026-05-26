from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session

from app.core.database import get_session

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str


class DBHealthResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check():
    return HealthResponse(status="ok", service="training-companion-api")


@router.get("/health/db", response_model=DBHealthResponse, tags=["health"])
def db_health_check(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return DBHealthResponse(status="ok", database="reachable")
