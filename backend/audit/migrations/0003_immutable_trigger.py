from django.db import migrations

# Audit entries are append-only. The model and queryset already refuse
# changes in Python; this trigger also stops raw SQL. TRUNCATE (used by
# test database flushes) doesn't fire row triggers.
FORWARD = """
CREATE FUNCTION audit_auditlog_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Audit entries cannot be changed or deleted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_auditlog_immutable
    BEFORE UPDATE OR DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION audit_auditlog_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_auditlog_immutable ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_auditlog_immutable();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0002_staff_actions'),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
