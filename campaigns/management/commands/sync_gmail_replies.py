from django.core.management.base import BaseCommand, CommandError

from accounts.gmail_oauth import GmailOAuthError
from campaigns.gmail_sync import sync_gmail_replies


class Command(BaseCommand):
    help = "Sync new Gmail replies for all connected tenant mailboxes"

    def handle(self, *args, **options):
        try:
            processed_count = sync_gmail_replies()
        except GmailOAuthError as error:
            raise CommandError(str(error)) from error
        reply_label = "reply" if processed_count == 1 else "replies"
        self.stdout.write(
            self.style.SUCCESS(
                f"Gmail reply sync complete; imported {processed_count} new {reply_label}."
            )
        )
