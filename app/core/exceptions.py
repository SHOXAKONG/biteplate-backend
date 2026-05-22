from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class BitePlateError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(BitePlateError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(BitePlateError):
    status_code = status.HTTP_409_CONFLICT


class InvalidStateTransition(BitePlateError):
    status_code = status.HTTP_409_CONFLICT


class AuthError(BitePlateError):
    status_code = status.HTTP_401_UNAUTHORIZED


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BitePlateError)
    async def biteplate_error_handler(request: Request, exc: BitePlateError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "type": exc.__class__.__name__},
        )
