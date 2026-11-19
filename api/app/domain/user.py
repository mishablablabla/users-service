"""Domain layer: entity, repository port and domain errors. No framework imports here."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class User:
    name: str
    email: str
    id: int | None = None


class UserNotFound(Exception):
    pass


class EmailAlreadyExists(Exception):
    pass


class UserRepository(Protocol):
    def list(self) -> list[User]: ...

    def get(self, user_id: int) -> User | None: ...

    def add(self, user: User) -> User:
        """Persist a new user. Raises EmailAlreadyExists on duplicate email."""

    def update(self, user: User) -> User:
        """Persist changes. Raises EmailAlreadyExists on duplicate email."""

    def delete(self, user_id: int) -> None: ...
