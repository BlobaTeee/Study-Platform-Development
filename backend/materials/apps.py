from django.apps import AppConfig


class MaterialsConfig(AppConfig):
    name = 'materials'
    # The tables were made with 64-bit keys (0001_initial); without this the
    # project default (32-bit) would ask for a migration that shrinks them.
    default_auto_field = 'django.db.models.BigAutoField'
