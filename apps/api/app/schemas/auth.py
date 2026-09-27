import re
import uuid

from pydantic import BaseModel, Field, field_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if _EMAIL.fullmatch(email) is None:
        raise ValueError("Enter a valid email address.")
    return email


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def email_shape(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("name")
    @classmethod
    def name_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name is required.")
        return stripped


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_shape(cls, value: str) -> str:
        return normalize_email(value)


class CurrentBusinessRequest(BaseModel):
    business_id: uuid.UUID


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str


class MembershipBusinessRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    default_currency: str
    role: str


class SessionRead(BaseModel):
    user: UserRead
    businesses: list[MembershipBusinessRead]
    current_business: MembershipBusinessRead | None
