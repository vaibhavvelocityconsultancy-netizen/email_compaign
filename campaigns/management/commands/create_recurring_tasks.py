import calendar
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from campaigns.models import Task


class Command(BaseCommand):
    help = "Create due instances of recurring tasks"

    def handle(self, *args, **options):
        today = timezone.localdate()
        parent_ids = Task.objects.filter(
            is_recurring=True,
            is_deleted=False,
            repeat_frequency__isnull=False,
        ).values_list("id", flat=True)

        created_count = 0
        for parent_id in parent_ids.iterator():
            with transaction.atomic():
                parent = (
                    Task.objects.select_for_update()
                    .filter(
                        pk=parent_id,
                        is_recurring=True,
                        is_deleted=False,
                        repeat_frequency__isnull=False,
                    )
                    .first()
                )
                if parent is None:
                    continue

                last_instance = (
                    Task.objects.filter(parent_task=parent)
                    .order_by("-followup_date", "-pk")
                    .first()
                )
                last_date = (
                    last_instance.followup_date if last_instance else parent.followup_date
                )
                next_date = self.get_next_date(last_date, parent)

                if parent.repeat_end_date and next_date > parent.repeat_end_date:
                    continue
                if next_date > today:
                    continue
                if Task.objects.filter(
                    parent_task=parent,
                    followup_date=next_date,
                ).exists():
                    continue

                instance = Task.objects.create(
                    title=parent.title,
                    description=parent.description,
                    module=parent.module,
                    task_regarding=parent.task_regarding,
                    reference_id=parent.reference_id,
                    company=parent.company,
                    followup_date=next_date,
                    priority=parent.priority,
                    status="PENDING",
                    assigned_to=parent.assigned_to,
                    created_by=parent.created_by,
                    remarks=parent.remarks,
                    parent_task=parent,
                    is_recurring=False,
                )

            created_count += 1
            self.stdout.write(f"Created: {instance.title} for {next_date}")

        self.stdout.write(self.style.SUCCESS(f"Total created: {created_count}"))

    @staticmethod
    def get_next_date(current_date: date, parent: Task) -> date:
        interval = parent.repeat_interval or 1
        if parent.repeat_frequency == "DAILY":
            return current_date + timedelta(days=interval)
        if parent.repeat_frequency == "WEEKLY":
            return current_date + timedelta(weeks=interval)
        if parent.repeat_frequency == "MONTHLY":
            month_index = current_date.month - 1 + interval
            year = current_date.year + month_index // 12
            month = month_index % 12 + 1
            day = min(current_date.day, calendar.monthrange(year, month)[1])
            return current_date.replace(year=year, month=month, day=day)
        if parent.repeat_frequency == "YEARLY":
            try:
                return current_date.replace(year=current_date.year + interval)
            except ValueError:
                return current_date.replace(year=current_date.year + interval, day=28)
        raise ValueError(f"Unsupported repeat frequency: {parent.repeat_frequency!r}")
