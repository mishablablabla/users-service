from pydantic import BaseModel, ConfigDict, Field


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["Ada Lovelace"])
    email: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        examples=["ada@example.com"],
    )


class UserOut(UserIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
