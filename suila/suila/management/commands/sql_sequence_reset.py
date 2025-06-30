from io import StringIO

from django.apps import apps
from django.core.management import BaseCommand, call_command
from django.db import connection


class Command(BaseCommand):
    filename = __file__

    def handle(self, *args, **options):
        commands = StringIO()
        cursor = connection.cursor()
        for app in apps.get_app_configs():
            call_command("sqlsequencereset", app.label, stdout=commands)
        cursor.execute(commands.getvalue())
