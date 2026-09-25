from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.errors import NotFoundError
from app.schemas.evaluation import EvaluationRead, EvaluationRunRequest
from app.services.evaluation import run_evaluation

router = APIRouter(prefix="/api")


@router.post("/evaluations/run", response_model=EvaluationRead)
def post_run_evaluation(
    payload: EvaluationRunRequest,
    session: Session = Depends(get_db),
) -> EvaluationRead:
    try:
        return run_evaluation(session, payload.business_id, payload.reference_time)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
