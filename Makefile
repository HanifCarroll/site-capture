.PHONY: test install-local build

test:
	PYTHONPATH=src python -m unittest discover -s tests

install-local:
	python -m pip install --upgrade --force-reinstall .

build:
	python -m pip wheel . -w dist
