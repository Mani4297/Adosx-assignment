from django.db import models


class Location(models.Model):
    """
    Master location model representing physical branches and their tenant ownership.
    This is the single source of truth for organization ownership (ORG-A vs ORG-B).
    """
    location_id = models.CharField(max_length=50, primary_key=True)
    org_id = models.CharField(max_length=50, db_index=True)
    location_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.location_id} ({self.org_id})"


class SystemARecord(models.Model):
    """
    Represents an event recorded in System A.
    Contains base_value and adjustment which sum to total_value.
    State can be CONFIRMED or VOIDED.
    """
    record_id = models.CharField(max_length=50, unique=True, db_index=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="system_a_records",
        null=True,
        blank=True
    )
    event_date = models.DateField()
    category_code = models.CharField(max_length=50)
    actor_id = models.CharField(max_length=50, null=True, blank=True)
    base_value = models.DecimalField(max_digits=14, decimal_places=2)
    adjustment = models.DecimalField(max_digits=14, decimal_places=2)
    total_value = models.DecimalField(max_digits=14, decimal_places=2)
    state = models.CharField(max_length=20, default="CONFIRMED", db_index=True)

    def __str__(self):
        return f"{self.record_id} [{self.state}] - {self.total_value}"


class SystemBEntry(models.Model):
    """
    Represents an entry recorded in System B referencing System A's record.
    Multiple entries may point to the same record (splits or duplicates).
    Orphan entries may point to a record that does not exist in System A,
    so no database ForeignKey to SystemARecord is used.
    """
    entry_id = models.CharField(max_length=50, unique=True, db_index=True)
    record_ref_raw = models.CharField(max_length=100)
    record_ref = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="system_b_entries",
        null=True,
        blank=True
    )
    recorded_on = models.DateField(null=True, blank=True)
    value_raw = models.CharField(max_length=100, blank=True, default="")
    value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    label = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        return f"{self.entry_id} -> {self.record_ref} ({self.value})"
