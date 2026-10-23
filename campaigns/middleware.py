import logging
from time import perf_counter

from django.http import HttpRequest, HttpResponse


logger = logging.getLogger("email_campaign")

CAMPAIGN_API_PREFIXES = (
    "/api/email-templates/",
    "/api/email-sequences/",
    "/api/sequence-steps/",
    "/api/batches/",
    "/api/leads/",
    "/api/lead-options/",
    "/api/email-logs/",
    "/api/inbound-replies/",
    "/api/email/unsubscribe/",
    "/api/webhooks/mailgun/",
)


def _campaign_endpoint(path: str) -> str | None:
    for prefix in CAMPAIGN_API_PREFIXES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return prefix
    return None


class EmailCampaignRequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        endpoint = _campaign_endpoint(request.path_info)
        if endpoint is None:
            return self.get_response(request)

        started_at = perf_counter()
        try:
            response = self.get_response(request)
        except Exception as error:
            logger.log(
                logging.ERROR,
                "event=api.request.failed method=%s endpoint=%s actor_id=%s "
                "error_type=%s duration_ms=%.2f",
                request.method,
                self._route_name(request, endpoint),
                self._actor_id(request),
                type(error).__name__,
                (perf_counter() - started_at) * 1000,
            )
            raise

        status_code = response.status_code
        logger.log(
            logging.ERROR if status_code >= 500 else (
                logging.WARNING if status_code >= 400 else logging.INFO
            ),
            "event=api.request method=%s endpoint=%s actor_id=%s status=%s "
            "duration_ms=%.2f",
            request.method,
            self._route_name(request, endpoint),
            self._actor_id(request),
            status_code,
            (perf_counter() - started_at) * 1000,
        )
        return response

    @staticmethod
    def _actor_id(request: HttpRequest) -> str | int:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user.pk
        return "unknown"

    @staticmethod
    def _route_name(request: HttpRequest, fallback: str) -> str:
        match = getattr(request, "resolver_match", None)
        if match is None:
            return fallback
        return match.route
