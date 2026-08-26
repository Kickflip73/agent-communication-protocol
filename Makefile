PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
PYTHON_SMOKE_TESTS ?= \
	tests/cert \
	tests/integration \
	tests/test_acp_json_media_type.py \
	tests/test_batch_message.py \
	tests/test_message_ack.py \
	tests/test_messages_stream.py \
	tests/test_v15_hybrid_identity.py \
	sdk/python/tests

.PHONY: install-dev lint test test-python test-node test-go test-rust build docs

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]" -e "./sdk/python[dev]"

lint:
	$(PYTHON) -m ruff check .
	(cd sdk/node && npm run lint)

test: test-python test-node test-go test-rust

test-python:
	$(PYTHON) -m pytest -q $(PYTHON_SMOKE_TESTS)

test-node:
	(cd sdk/node && npm test)

test-go:
	(cd sdk/go && go test ./...)

test-rust:
	(cd sdk/rust && cargo test)

build:
	$(PYTHON) -m build
	(cd sdk/python && $(PYTHON) -m build)

docs:
	mkdocs build --strict
