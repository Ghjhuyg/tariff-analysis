from django.apps import AppConfig


class ComparisonConfig(AppConfig):
    name = 'comparison'

# app/apps.py
class AppConfig(AppConfig):
    # ...
    def ready(self):
        import comparison.signals