"""Pure unit tests of the application layer with an in-memory fake repository."""
import pytest

from app.application.user_service import UserService
from app.domain.user import EmailAlreadyExists, User, UserNotFound


class FakeRepo:
    def __init__(self):
        self.items: dict[int, User] = {}
        self.seq = 0

    def list(self):
        return list(self.items.values())

    def get(self, user_id):
        return self.items.get(user_id)

    def add(self, user):
        if any(u.email == user.email for u in self.items.values()):
            raise EmailAlreadyExists()
        self.seq += 1
        user.id = self.seq
        self.items[user.id] = user
        return user

    def update(self, user):
        self.items[user.id] = user
        return user

    def delete(self, user_id):
        self.items.pop(user_id, None)


def test_create_and_get():
    svc = UserService(FakeRepo())
    u = svc.create_user("Ada", "ada@example.com")
    assert svc.get_user(u.id).email == "ada@example.com"


def test_get_missing_raises():
    with pytest.raises(UserNotFound):
        UserService(FakeRepo()).get_user(1)


def test_duplicate_email_raises():
    svc = UserService(FakeRepo())
    svc.create_user("Ada", "ada@example.com")
    with pytest.raises(EmailAlreadyExists):
        svc.create_user("Other", "ada@example.com")


def test_update_and_delete():
    svc = UserService(FakeRepo())
    u = svc.create_user("Ada", "ada@example.com")
    assert svc.update_user(u.id, "Grace", "g@example.com").name == "Grace"
    svc.delete_user(u.id)
    with pytest.raises(UserNotFound):
        svc.delete_user(u.id)
