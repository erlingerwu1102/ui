import logging
import traceback
import time
import uuid
from flask import jsonify, request, current_app
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class APIException(Exception):
    """Application-level exception that carries an HTTP status code and optional payload."""

    def __init__(self, message, status_code=400, payload=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


def _make_request_id():
    # Prefer client-supplied header for tracing, otherwise generate one
    rid = request.headers.get("X-Request-ID") if request else None
    if not rid:
        rid = str(uuid.uuid4())
    return rid


def _build_error_body(request_id, error_type, message, status_code, details=None, include_trace=False):
    # Standardized response envelope: { code, msg, data }
    data = {
        "request_id": request_id,
        "type": error_type,
        "timestamp": int(time.time()),
    }
    if details is not None:
        data["details"] = details
    if include_trace:
        # include minimal trace information for debugging (enable only in debug/dev)
        data["trace"] = traceback.format_exc()

    body = {
        "code": status_code,
        "msg": message,
        "data": data,
    }
    # backward-compatibility: include legacy `error` object used by existing tests/clients
    legacy = {
        "type": error_type,
        "message": message,
        "code": status_code,
        "request_id": request_id,
        "timestamp": data.get("timestamp"),
    }
    if details is not None:
        legacy["details"] = details
    if include_trace:
        legacy["trace"] = data.get("trace")

    body["error"] = legacy
    return body


def _error_response(request_id, error_type, message, status_code=500, details=None, include_trace=False):
    body = _build_error_body(request_id, error_type, message, status_code, details=details, include_trace=include_trace)
    resp = jsonify(body)
    resp.status_code = status_code
    # echo request id header for tracing
    try:
        resp.headers["X-Request-ID"] = request_id
    except Exception:
        pass
    return resp


def handle_api_exception(error):
    request_id = _make_request_id()
    logger.warning("APIException [%s]: %s payload=%s", request_id, getattr(error, "message", str(error)), getattr(error, "payload", None))
    return _error_response(
        request_id,
        "APIException",
        getattr(error, "message", str(error)),
        status_code=getattr(error, "status_code", 400),
        details=getattr(error, "payload", None),
    )


def handle_http_exception(error):
    # werkzeug HTTPException
    request_id = _make_request_id()
    message = getattr(error, "description", str(error))
    status = getattr(error, "code", 500)
    logger.info("HTTPException [%s] %s: %s", request_id, status, message)
    return _error_response(request_id, "HTTPException", message, status_code=status)


def handle_generic_exception(error):
    request_id = _make_request_id()
    # log traceback for server-side inspection but avoid leaking internals to clients
    logger.exception("Unhandled Exception [%s]: %s", request_id, str(error))
    include_trace = bool(current_app and current_app.config.get("DEBUG", False))
    return _error_response(
        request_id,
        "InternalError",
        "An internal error occurred",
        status_code=500,
        include_trace=include_trace,
    )


def handle_validation_error(error):
    request_id = _make_request_id()
    # lazy import marshmallow ValidationError
    try:
        from marshmallow import ValidationError

        if isinstance(error, ValidationError):
            logger.debug("Validation error [%s]: %s", request_id, getattr(error, "messages", None))
            return _error_response(
                request_id, "ValidationError", "Invalid input", status_code=400, details=getattr(error, "messages", None)
            )
    except Exception:
        pass
    # fallback: stringified error
    logger.debug("Validation error (fallback) [%s]: %s", request_id, str(error))
    return _error_response(request_id, "ValidationError", str(error), status_code=400)


def register_error_handlers(app):
    """Register centralized error handlers on a Flask app.

    - Adds request tracing via `X-Request-ID` (if provided) or generates a UUID.
    - In `DEBUG` mode the internal exception handler will include a trace field.
    """
    app.register_error_handler(APIException, handle_api_exception)
    app.register_error_handler(HTTPException, handle_http_exception)
    # marshmallow ValidationError (if marshmallow is installed)
    try:
        from marshmallow import ValidationError

        app.register_error_handler(ValidationError, handle_validation_error)
    except Exception:
        # marshmallow not installed — skip
        pass

    # Catch-all
    app.register_error_handler(Exception, handle_generic_exception)

    # Ensure BadRequest JSON parsing errors also return our structured JSON
    try:
        from werkzeug.exceptions import BadRequest

        def _handle_badrequest(err):
            request_id = _make_request_id()
            msg = getattr(err, "description", str(err))
            logger.info("BadRequest [%s]: %s", request_id, msg)
            return _error_response(request_id, "BadRequest", msg, status_code=getattr(err, "code", 400))

        app.register_error_handler(BadRequest, _handle_badrequest)
    except Exception:
        pass
