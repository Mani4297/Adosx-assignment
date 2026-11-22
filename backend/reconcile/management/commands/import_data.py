from pathlib import Path
from django.core.management.base import BaseCommand
from reconcile.importer import import_all_data


class Command(BaseCommand):
    help = "Import CSV datasets (locations, system_a, system_b) idempotently into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            type=str,
            default=None,
            help="Directory containing locations.csv, system_a.csv, system_b.csv",
        )

    def handle(self, *args, **options):
        data_dir = options.get("data_dir")
        self.stdout.write(self.style.NOTICE("Starting CSV data import..."))

        stats = import_all_data(data_dir)

        loc = stats["locations"]
        a = stats["system_a"]
        b = stats["system_b"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Locations: {loc['read']} read, {loc['saved']} saved\n"
                f"A: {a['read']} read, {a['saved']} saved (blank actors: {a.get('blank_actors', 0)})\n"
                f"B: {b['read']} read, {b['saved']} saved; values left empty: {b['values_left_empty']}; refs cleaned: {b['refs_cleaned']}"
            )
        )
