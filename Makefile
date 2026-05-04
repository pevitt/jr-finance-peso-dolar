.PHONY: build up down logs shell bash migrate makemigrations test lint superuser bot

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f web

shell:
	docker compose exec web python manage.py shell

bash:
	docker compose exec web bash

migrate:
	docker compose exec web python manage.py migrate

makemigrations:
	docker compose exec web python manage.py makemigrations $(app)

test:
	docker compose exec web pytest

lint:
	docker compose exec web ruff check .

superuser:
	docker compose exec web python manage.py createsuperuser

bot:
	docker compose exec web python manage.py run_bot
