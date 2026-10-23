from django.core.management.base import BaseCommand, CommandError

from accounts.gmail_oauth import GmailOAuthError
from campaigns.gmail_sync import sync_gmail_replies


class Command(BaseCommand):
    help = "Sync Gmail metadata and mark matching email campaign replies"

    def handle(self, *args, **options):
        try:
            processed_count = sync_gmail_replies()
        except GmailOAuthError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Gmail sync complete; processed {processed_count} new message(s)."
            )
        )
