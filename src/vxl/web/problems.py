"""The form of every answer to a request that failed (RFC 9457 problem details)."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

type Statuses = Mapping[type[Exception], int]
"""The HTTP status of each kind of error, the most special kind first."""


class ProblemDetails(BaseModel):
    """An RFC 9457 answer for a request that failed. ``errors`` lists each refused argument, or each problem that the
    failure carries."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    errors: list[Any] | None = None

    @classmethod
    def install(cls, app: Starlette, statuses: Statuses | None = None) -> None:
        """Make ``app`` answer each failure as problem details. ``statuses`` gives the status of each kind of error,
        the most special kind first. An HTTP error keeps its own status, and any other error answers ``500``. An
        error with ``errors()`` has its refused arguments listed, and an error with ``problems`` has those listed. An
        error with ``problem_type`` answers with that ``type``."""
        kinds = dict(statuses or {})

        async def answer(request: Request, error: Exception) -> JSONResponse:
            return cls._of(request, error, kinds)

        for failure in (*kinds, HTTPException, Exception):
            app.add_exception_handler(failure, answer)

    @classmethod
    def described(cls) -> dict[int | str, dict[str, Any]]:
        """The problem answers of a route, for the API page."""
        return {status: {"model": cls} for status in (400, 404, 409, 412, 422)}

    @classmethod
    def response(
        cls,
        status: int,
        detail: str,
        instance: str,
        errors: list[Any] | None = None,
        headers: Mapping[str, str] | None = None,
        problem_type: str = "about:blank",
    ) -> JSONResponse:
        """A problem answer with ``status``, and with ``headers`` when given."""
        title = HTTPStatus(status).phrase if status in HTTPStatus else "Error"
        body = cls(type=problem_type, title=title, status=status, detail=detail, instance=instance, errors=errors)
        content = body.model_dump(mode="json", exclude_none=True)
        return JSONResponse(content, status_code=status, headers=headers, media_type="application/problem+json")

    @classmethod
    def _of(cls, request: Request, error: Exception, kinds: Statuses) -> JSONResponse:
        where = request.url.path
        if isinstance(error, HTTPException):
            detail: object = error.detail  # FastAPI's HTTPException takes any value as its detail
            return cls.response(error.status_code, str(detail), where, headers=error.headers)
        status = next((status for kind, status in kinds.items() if isinstance(error, kind)), 500)
        if status == HTTPStatus.INTERNAL_SERVER_ERROR:
            return cls.response(status, "the request failed; see the log", where)
        refused: Any = getattr(error, "errors", None)
        if callable(refused):
            listed: Any = refused()
            errors = [{name: found[name] for name in ("type", "loc", "msg")} for found in listed]
            return cls.response(status, f"{len(errors)} argument(s) refused", where, errors)
        carried: Any = getattr(error, "problems", ())
        problems = [
            problem.model_dump(mode="json") if isinstance(problem, BaseModel) else problem for problem in carried
        ]
        problem_type = str(getattr(error, "problem_type", "about:blank"))
        return cls.response(status, str(error), where, problems or None, problem_type=problem_type)


__all__ = ["ProblemDetails", "Statuses"]
