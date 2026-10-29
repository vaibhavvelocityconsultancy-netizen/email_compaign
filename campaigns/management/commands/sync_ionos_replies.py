from django.core.management.base import BaseCommand, CommandError

from campaigns.ionos_sync import IonosMailboxError, sync_ionos_replies


class Command(BaseCommand):
    help = "Sync new IONOS inbox messages and mark matched campaign replies"

    def handle(self, *args, **options):
        try:
            processed_count = sync_ionos_replies()
        except IonosMailboxError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"IONOS sync complete; processed {processed_count} new message(s)."
            )
        )
