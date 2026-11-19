"""Application layer: use cases orchestrating the domain through the repository port."""
from ..domain.user import User, UserNotFound, UserRepository


class UserService:
    def __init__(self, repo: UserRepository):
        self._repo = repo

    def list_users(self) -> list[User]:
        return self._repo.list()

    def get_user(self, user_id: int) -> User:
        user = self._repo.get(user_id)
        if user is None:
            raise UserNotFound(user_id)
        return user

    def create_user(self, name: str, email: str) -> User:
        return self._repo.add(User(name=name, email=email))

    def update_user(self, user_id: int, name: str, email: str) -> User:
        user = self.get_user(user_id)
        user.name, user.email = name, email
        return self._repo.update(user)

    def delete_user(self, user_id: int) -> None:
        self.get_user(user_id)
        self._repo.delete(user_id)
