from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.user import EmailAlreadyExists, User
from .orm import UserRecord


def _to_entity(r: UserRecord) -> User:
    return User(id=r.id, name=r.name, email=r.email)


class SqlAlchemyUserRepository:
    def __init__(self, session: Session):
        self._s = session

    def list(self) -> list[User]:
        rows = self._s.scalars(select(UserRecord).order_by(UserRecord.id)).all()
        return [_to_entity(r) for r in rows]

    def get(self, user_id: int) -> User | None:
        r = self._s.get(UserRecord, user_id)
        return _to_entity(r) if r else None

    def add(self, user: User) -> User:
        r = UserRecord(name=user.name, email=user.email)
        self._s.add(r)
        self._commit()
        return _to_entity(r)

    def update(self, user: User) -> User:
        r = self._s.get(UserRecord, user.id)
        r.name, r.email = user.name, user.email
        self._commit()
        return _to_entity(r)

    def delete(self, user_id: int) -> None:
        r = self._s.get(UserRecord, user_id)
        if r:
            self._s.delete(r)
            self._s.commit()

    def _commit(self) -> None:
        try:
            self._s.commit()
        except IntegrityError as e:
            self._s.rollback()
            raise EmailAlreadyExists() from e
