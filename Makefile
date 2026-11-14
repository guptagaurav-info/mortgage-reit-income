PY ?= python
export PYTHONPATH := src

.PHONY: all ingest run test
all: ingest run
ingest:
	$(PY) -m mrc.ingest
run:
	$(PY) -m mrc.pipeline
test:
	$(PY) -m pytest -q tests
