from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.db.dependencies import get_db
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyCreate, CompanyRead

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyRead])
def list_companies(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Company]:
    return list(db.scalars(select(Company).order_by(Company.name)).all())


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Company:
    company = Company(**payload.model_dump())
    db.add(company)
    try:
        db.commit()
        db.refresh(company)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this name or ATS board slug already exists",
        ) from error
    return company
