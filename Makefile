.PHONY: setup up test lint gen

setup:
	pip install -e libs/quant-core -e libs/quant-io
	pip install ruff mypy pytest import-linter
	cd apps/dashboard && npm install
	mvn -f services/core-service/pom.xml install -DskipTests

up:
	docker compose up -d

test:
	pytest libs services --ignore=services/core-service -q
	mvn -f services/core-service/pom.xml test
	cd apps/dashboard && npx vitest run

lint:
	ruff check libs services apps --exclude apps/dashboard
	mypy --strict libs
	PYTHONPATH=libs/quant-core lint-imports --config libs/quant-core/.importlinter
	mvn -f services/core-service/pom.xml spotless:check
	cd apps/dashboard && npx tsc --noEmit && npx eslint .

gen:
	python3 tools/codegen/generate.py contracts/
