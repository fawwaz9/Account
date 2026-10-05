from enum import Enum

from pydantic import BaseModel


class Question(str, Enum):
    #: The Sean Ellis test: "How would you feel if you could no longer use Account?"
    DISAPPOINTMENT = "disappointment"


class Answer(str, Enum):
    VERY = "very"
    SOMEWHAT = "somewhat"
    NOT = "not"
    #: "Don't ask again" is an answer, and it is final.
    DISMISSED = "dismissed"


class Pending(BaseModel):
    #: The question to ask now, or null for none.
    question: Question | None = None


class ResponseCreate(BaseModel):
    question: Question
    answer: Answer
