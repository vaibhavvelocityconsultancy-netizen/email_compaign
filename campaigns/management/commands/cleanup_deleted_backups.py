from django.core.management.base import BaseCommand

from campaigns.backup import purge_expired_backups


class Command(BaseCommand):
    help = "Permanently purge deleted records after their 30-day backup period."

    def handle(self, *args, **options):
        deleted = purge_expired_backups()
        self.stdout.write(self.style.SUCCESS(f"Purged {deleted} expired backup records."))
