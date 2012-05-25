from django.dispatch import Signal


audit_special = Signal(providing_args=["instance", "field", "action", "value"])
