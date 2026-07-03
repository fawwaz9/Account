from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Grades.schemas.course import CourseDetail


class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)

    @model_validator(mode="after")
    def validate_user_logic(self):
        if self.name.strip() == "":
            raise ValueError("User name cannot be empty")

        if "@" not in self.email or self.email.strip() == "":
            raise ValueError("Invalid email address")

        return self


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=255)

    @model_validator(mode="after")
    def validate_user_update(self):
        if self.name is not None and self.name.strip() == "":
            raise ValueError("User name cannot be empty")

        if self.email is not None and ("@" not in self.email or self.email.strip() == ""):
            raise ValueError("Invalid email address")

        return self


class User(UserBase):
    id: UUID = Field(default_factory=uuid4)

    class Config:
        from_attributes = True


class UserDetail(User):
    courses: list[CourseDetail] = Field(default_factory=list)

    class Config:
        from_attributes = True
