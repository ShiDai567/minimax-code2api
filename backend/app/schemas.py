from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Region = Literal["cn", "global"]


class AccountCreate(BaseModel):
    region: Region
    name: str = Field(min_length=1, max_length=120)
    identifier: str = Field(min_length=1, max_length=255)
    real_user_id: str | None = None
    credential: str = Field(min_length=1)
    group_id: int | None = None
    note: str = ""


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    identifier: str | None = Field(default=None, min_length=1, max_length=255)
    real_user_id: str | None = None
    credential: str | None = None
    group_id: int | None = None
    note: str | None = None
    enabled: bool | None = None


class GroupCreate(BaseModel):
    region: Region
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    note: str = ""
    permissions: list[str] = ["gateway"]
