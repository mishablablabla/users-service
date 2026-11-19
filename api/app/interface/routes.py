from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..application.user_service import UserService
from ..domain.user import EmailAlreadyExists, UserNotFound
from ..infrastructure.db import get_session
from ..infrastructure.sqlalchemy_user_repository import SqlAlchemyUserRepository
from .schemas import UserIn, UserOut

router = APIRouter(prefix="/api")


def get_service(session: Session = Depends(get_session)) -> UserService:
    return UserService(SqlAlchemyUserRepository(session))


@router.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@router.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(svc: UserService = Depends(get_service)):
    return svc.list_users()


@router.get("/users/{user_id}", response_model=UserOut, tags=["users"])
def get_user(user_id: int, svc: UserService = Depends(get_service)):
    try:
        return svc.get_user(user_id)
    except UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["users"])
def create_user(payload: UserIn, response: Response, svc: UserService = Depends(get_service)):
    try:
        user = svc.create_user(payload.name, payload.email)
    except EmailAlreadyExists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
    response.headers["Location"] = f"/api/users/{user.id}"
    return user


@router.put("/users/{user_id}", response_model=UserOut, tags=["users"])
def update_user(user_id: int, payload: UserIn, svc: UserService = Depends(get_service)):
    try:
        return svc.update_user(user_id, payload.name, payload.email)
    except UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    except EmailAlreadyExists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["users"])
def delete_user(user_id: int, svc: UserService = Depends(get_service)):
    try:
        svc.delete_user(user_id)
    except UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
