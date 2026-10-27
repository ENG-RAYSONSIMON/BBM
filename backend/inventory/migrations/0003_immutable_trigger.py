from django.db import migrations

# Append-only, like the audit log: the model refuses changes in Python; this
# trigger also stops QuerySet.update() and raw SQL. TRUNCATE (used by test
# database flushes) doesn't fire row triggers.
FORWARD = """
CREATE FUNCTION inventory_stockmovement_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Stock movements cannot be changed or deleted; record a new adjustment.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER inventory_stockmovement_immutable
    BEFORE UPDATE OR DELETE ON inventory_stockmovement
    FOR EACH ROW EXECUTE FUNCTION inventory_stockmovement_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS inventory_stockmovement_immutable ON inventory_stockmovement;
DROP FUNCTION IF EXISTS inventory_stockmovement_immutable();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_stockmovement_return'),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
