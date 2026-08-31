.PHONY: setup up test lint gen

setup:
	pip install -e libs/quant-core -e libs/quant-io -e contracts/generated/python
	pip install ruff mypy pytest import-linter avro
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
	PYTHONPATH=libs/quant-core lint-imports --config libs/quant-core/.importlinter
	mvn -pl services/core-service com.diffplug.spotless:spotless-maven-plugin:check
	cd apps/dashboard && npx tsc --noEmit && npx eslint .

gen:
	python3 tools/codegen/generate.py contracts/
