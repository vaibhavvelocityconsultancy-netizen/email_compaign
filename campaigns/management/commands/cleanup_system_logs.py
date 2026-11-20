from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from campaigns.backup import archive_and_delete_queryset
from campaigns.models import SystemLog


class Command(BaseCommand):
    help = "Delete system logs older than 10 days"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=10)
        expired_logs = SystemLog.objects.filter(created_at__lt=cutoff)
        deleted_count = archive_and_delete_queryset(
            expired_logs, None, "System logs"
        )
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {deleted_count} system log(s) older than 10 days.")
        )
