# Requires GNU make. On Windows without make, run the commands shown in README.md.
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python
else
PY := .venv/bin/python
endif

.PHONY: install build start dev-api dev-web clean

install:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt
	cd frontend && npm install

build:
	cd frontend && npm run build

start: build
	$(PY) -m server

dev-api:
	$(PY) -m server --reload --no-browser

dev-web:
	cd frontend && npm run dev

clean:
	rm -rf .chroma .cache frontend/dist
