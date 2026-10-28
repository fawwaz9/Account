"""Schemas for the in-app survey: which question to ask, and an answer to it."""

from enum import Enum

from pydantic import BaseModel


class Question(str, Enum):
    """The survey questions that can be asked."""
    #: The Sean Ellis test: "How would you feel if you could no longer use Account?"
    DISAPPOINTMENT = "disappointment"


class Answer(str, Enum):
    """The answers a question accepts; "dismissed" means never ask again."""
    VERY = "very"
    SOMEWHAT = "somewhat"
    NOT = "not"
    #: "Don't ask again" is an answer, and it is final.
    DISMISSED = "dismissed"


class Pending(BaseModel):
    """The question the client should ask now.

    Attributes:
        question: The question to ask, or null when there is none.
    """
    #: The question to ask now, or null for none.
    question: Question | None = None


class ResponseCreate(BaseModel):
    """Request body answering a survey question; each question is answered once.

    Attributes:
        question: The question answered.
        answer: The answer given.
    """
    question: Question
    answer: Answer
