.DEFAULT_GOAL := pyside6

PYTHON ?= python3
INPUT ?= input.json

.PHONY: pyside6 wx flet

pyside6:
	$(PYTHON) shapecmd.py $(INPUT) pyside6

wx:
	$(PYTHON) shapecmd.py $(INPUT) wx

flet:
	$(PYTHON) shapecmd.py $(INPUT) flet
