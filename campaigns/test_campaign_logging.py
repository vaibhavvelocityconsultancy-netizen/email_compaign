import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

from campaigns.logging_handlers import LatestFirstTimedRotatingFileHandler
from campaigns.middleware import EmailCampaignRequestLoggingMiddleware


class LatestFirstTimedRotatingFileHandlerTests(SimpleTestCase):
    def test_prepends_new_records_without_splitting_multiline_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "email_campaign.log"
            handler = LatestFirstTimedRotatingFileHandler(
                log_path,
                when="midnight",
                backupCount=15,
                encoding="utf-8",
                delay=True,
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            try:
                handler.handle(
                    logging.LogRecord(
                        "email_campaign",
                        logging.ERROR,
                        __file__,
                        1,
                        "event=send.failed\nTraceback detail",
                        (),
                        None,
                    )
                )
                handler.handle(
                    logging.LogRecord(
                        "email_campaign",
                        logging.INFO,
                        __file__,
                        2,
                        "event=campaign.created",
                        (),
                        None,
                    )
                )
            finally:
                handler.close()

            self.assertEqual(
                log_path.read_text(encoding="utf-8"),
                "event=campaign.created\nevent=send.failed\nTraceback detail\n",
            )


class EmailCampaignRequestLoggingMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("campaigns.middleware.logger.log")
    def test_logs_campaign_get_without_query_parameters(self, log):
        request = self.factory.get(
            "/api/batches/?email=private@example.com&token=private-token"
        )
        middleware = EmailCampaignRequestLoggingMiddleware(
            lambda request: HttpResponse(status=200)
        )

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        log.assert_called_once()
        self.assertEqual(log.call_args.args[3], "/api/batches/")
        self.assertNotIn("private@example.com", str(log.call_args))
        self.assertNotIn("private-token", str(log.call_args))

    @patch("campaigns.middleware.logger.log")
    def test_logs_campaign_errors_and_reraises(self, log):
        request = self.factory.post("/api/batches/")

        def raise_error(_request):
            raise RuntimeError("request failed")

        middleware = EmailCampaignRequestLoggingMiddleware(raise_error)

        with self.assertRaisesRegex(RuntimeError, "request failed"):
            middleware(request)

        log.assert_called_once()
        self.assertIn("event=api.request.failed", log.call_args.args[1])

    @patch("campaigns.middleware.logger.log")
    def test_does_not_log_unrelated_endpoints(self, log):
        request = self.factory.get("/api/companies/")
        middleware = EmailCampaignRequestLoggingMiddleware(
            lambda request: HttpResponse(status=200)
        )

        middleware(request)

        log.assert_not_called()

    @patch("campaigns.middleware.logger.log")
    def test_does_not_log_unsubscribe_token(self, log):
        request = self.factory.get("/api/email/unsubscribe/private-token/")
        request.resolver_match = resolve(request.path_info)
        middleware = EmailCampaignRequestLoggingMiddleware(
            lambda request: HttpResponse(status=200)
        )

        middleware(request)

        self.assertNotIn("private-token", str(log.call_args))
        self.assertIn("<str:token>", log.call_args.args[3])
