"""SQLite implementation of RequestRepository."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.request import RequestModel
from app.repositories.base import RequestRepository


class SQLiteRequestRepository(RequestRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, request: RequestModel) -> RequestModel:
        self._db.add(request)
        self._db.commit()
        self._db.refresh(request)
        return request

    def get_by_id(self, request_id: int) -> RequestModel | None:
        return self._db.get(RequestModel, request_id)

    def list_by_requester(self, requester_email: str) -> list[RequestModel]:
        return (
            self._db.query(RequestModel)
            .filter(RequestModel.requester_email == requester_email)
            .order_by(RequestModel.created_at.desc())
            .all()
        )

    def list_all(self, status: str | None = None) -> list[RequestModel]:
        q = self._db.query(RequestModel)
        if status:
            q = q.filter(RequestModel.status == status)
        return q.order_by(RequestModel.created_at.desc()).all()

    def update(self, request: RequestModel) -> RequestModel:
        self._db.commit()
        self._db.refresh(request)
        return request

    def get_overlapping(
        self,
        equipment_id: str,
        needed_from: str,
        needed_to: str,
        statuses: list[str],
        exclude_id: int | None = None,
    ) -> list[RequestModel]:
        """Return requests that overlap the given date range for specified statuses.

        Overlap condition: start_a <= end_b AND start_b <= end_a
        Dates are ISO strings (YYYY-MM-DD), which sort lexicographically.
        """
        q = (
            self._db.query(RequestModel)
            .filter(
                RequestModel.equipment_id == equipment_id,
                RequestModel.status.in_(statuses),
                RequestModel.needed_from <= needed_to,
                RequestModel.needed_to >= needed_from,
            )
        )
        if exclude_id is not None:
            q = q.filter(RequestModel.id != exclude_id)
        return q.all()

    def count_by_status(self) -> dict[str, int]:
        rows = (
            self._db.query(RequestModel.status, func.count(RequestModel.id))
            .group_by(RequestModel.status)
            .all()
        )
        return {status: count for status, count in rows}
