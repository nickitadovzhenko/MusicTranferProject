.PHONY: run down test migrate shell logs

run:
	docker-compose up --build

down:
	docker-compose down

migrate:
	docker-compose exec web python manage.py migrate

test:
	docker-compose exec web python manage.py test --settings=playlistTransfer.test_settings

shell:
	docker-compose exec web python manage.py shell

logs:
	docker-compose logs -f web worker
