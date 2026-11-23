from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

from poc_toolbox.repositories import EncryptionConfigurationError


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


async def api_error_response(_request: Request, error: APIError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content={'error': {'code': error.code, 'message': error.message}})


async def validation_error_response(_request: Request, error: RequestValidationError) -> JSONResponse:
    details = [{'location': list(item['loc']), 'type': item['type']} for item in error.errors()]
    return JSONResponse(
        status_code=422,
        content={'error': {'code': 'VALIDATION_ERROR', 'message': 'Invalid request', 'details': details}},
    )


async def integrity_error_response(request: Request, error: IntegrityError) -> JSONResponse:
    sqlstate = getattr(error.orig, 'sqlstate', None)
    if sqlstate == '23505':
        failure = APIError(409, 'NAME_CONFLICT', 'A record with this name already exists')
    elif sqlstate == '23503' and request.method in {'POST', 'PATCH'}:
        failure = APIError(422, 'INVALID_REFERENCE', 'Referenced model configuration does not exist')
    else:
        failure = APIError(409, 'REFERENCE_CONFLICT', 'The operation conflicts with existing records')
    return await api_error_response(request, failure)


async def encryption_error_response(request: Request, _error: EncryptionConfigurationError) -> JSONResponse:
    failure = APIError(503, 'ENCRYPTION_UNAVAILABLE', 'API key encryption is unavailable')
    return await api_error_response(request, failure)


async def database_error_response(request: Request, _error: SQLAlchemyError) -> JSONResponse:
    return await api_error_response(request, APIError(503, 'DATABASE_UNAVAILABLE', 'Database operation failed'))


async def http_error_response(request: Request, error: HTTPException) -> JSONResponse:
    failure = APIError(error.status_code, 'HTTP_ERROR', 'Request could not be completed')
    return await api_error_response(request, failure)


async def unexpected_error_response(request: Request, _error: Exception) -> JSONResponse:
    return await api_error_response(request, APIError(500, 'INTERNAL_ERROR', 'Internal server error'))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, api_error_response)
    app.add_exception_handler(RequestValidationError, validation_error_response)
    app.add_exception_handler(IntegrityError, integrity_error_response)
    app.add_exception_handler(EncryptionConfigurationError, encryption_error_response)
    app.add_exception_handler(SQLAlchemyError, database_error_response)
    app.add_exception_handler(HTTPException, http_error_response)
    app.add_exception_handler(Exception, unexpected_error_response)
