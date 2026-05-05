#!/bin/sh
set -e
python manage.py migrate
python manage.py run_bot &
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
