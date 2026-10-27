from django.db import migrations

# Append-only, like the audit log: the model refuses changes in Python; this
# trigger also stops QuerySet.update() and raw SQL. TRUNCATE (used by test
# database flushes) doesn't fire row triggers.
FORWARD = """
CREATE FUNCTION sales_payment_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Payments cannot be changed or deleted; void the sale instead.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sales_payment_immutable
    BEFORE UPDATE OR DELETE ON sales_payment
    FOR EACH ROW EXECUTE FUNCTION sales_payment_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS sales_payment_immutable ON sales_payment;
DROP FUNCTION IF EXISTS sales_payment_immutable();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
