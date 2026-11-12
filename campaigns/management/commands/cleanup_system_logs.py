from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from campaigns.models import SystemLog


class Command(BaseCommand):
    help = "Delete system logs older than 10 days"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=10)
        deleted_count, _ = SystemLog.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {deleted_count} system log(s) older than 10 days.")
        )
