.PHONY: setup up test lint gen

setup:
	pip install -e libs/quant-core -e libs/quant-io
	pip install ruff mypy pytest import-linter
	cd apps/dashboard && npm install
	mvn -pl services/core-service -am install -DskipTests

up:
	docker compose up -d

test:
	pytest libs services --ignore=services/core-service -q
	mvn -pl services/core-service -am test
	cd apps/dashboard && npx vitest run

lint:
	ruff check libs services apps --exclude apps/dashboard
	mypy --strict libs
	lint-imports --config libs/quant-core/.importlinter
	mvn -pl services/core-service spotless:check
	cd apps/dashboard && npx tsc --noEmit && npx eslint .

gen:
	python3 tools/codegen/generate.py contracts/
