import time

from django.core.management.base import BaseCommand

from services.checkin_service import run_one, schedule_due


class Command(BaseCommand):
    help = "Run scheduled and queued check-ins. Restarts resume from the database lease."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=10)

    def handle(self, *args, **options):
        while True:
            schedule_due()
            processed = run_one()
            if options["once"]:
                return
            if not processed:
                time.sleep(max(1, options["interval"]))
