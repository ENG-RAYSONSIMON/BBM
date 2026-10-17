FROM python:3.12-slim
# gettext: makemessages / compilemessages for the Kiswahili translations.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN django-admin compilemessages -l sw --force \
    && groupadd --gid 10001 bbm \
    && useradd --uid 10001 --gid bbm --no-create-home bbm \
    && mkdir -p /app/staticfiles /app/media /app/private_media \
    && chown bbm:bbm /app/staticfiles /app/media /app/private_media
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER bbm
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "--access-logformat", "%(h)s %(m)s %(U)s %(s)s %(L)s"]