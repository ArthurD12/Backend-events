"""Dependencias de FastAPI del módulo assistant. En las pruebas se reemplazan por fakes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.assistant import composition
from local_eventos.modules.assistant.application.ports.feedback_log import FeedbackLog
from local_eventos.modules.assistant.application.ports.language_model import LanguageModel
from local_eventos.modules.assistant.application.ports.query_log import Clock, QueryLog
from local_eventos.modules.assistant.application.tools import ToolRegistry
from local_eventos.modules.identity.public_api import UserNamesLookup, user_names
from local_eventos.shared.presentation.database import get_session


async def get_language_model() -> LanguageModel | None:
    return composition.language_model()


async def get_tools(session: Annotated[AsyncSession, Depends(get_session)]) -> ToolRegistry:
    return composition.tools(session)


async def get_query_log(session: Annotated[AsyncSession, Depends(get_session)]) -> QueryLog:
    return composition.query_log(session)


async def get_feedback_log(session: Annotated[AsyncSession, Depends(get_session)]) -> FeedbackLog:
    return composition.feedback_log(session)


async def get_clock() -> Clock:
    return composition.clock()


async def get_user_names(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserNamesLookup:
    return user_names(session)


ModelDep = Annotated[LanguageModel | None, Depends(get_language_model)]
ToolsDep = Annotated[ToolRegistry, Depends(get_tools)]
QueryLogDep = Annotated[QueryLog, Depends(get_query_log)]
FeedbackLogDep = Annotated[FeedbackLog, Depends(get_feedback_log)]
ClockDep = Annotated[Clock, Depends(get_clock)]
UserNamesDep = Annotated[UserNamesLookup, Depends(get_user_names)]
