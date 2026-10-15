.DEFAULT_GOAL := pyside6

PYTHON ?= python3
INPUT ?= input.json
WEB_PYTHON ?= env/bin/python
WEB_BIND ?= localhost:8866
WEB_BASE_URL ?= /shapecmd
WEB_ALLOW_HOSTS ?= *
WEB_TRUSTED_PROXIES ?= 127.0.0.0/8 ::1/128 unix

.PHONY: pyside6 wx flet web

pyside6:
	$(PYTHON) shapecmd.py $(INPUT) pyside6

wx:
	$(PYTHON) shapecmd.py $(INPUT) wx

flet:
	$(PYTHON) shapecmd.py $(INPUT) flet

web:
	SHAPECMD_INPUT="$(abspath $(INPUT))" $(WEB_PYTHON) -m PUI.web shapecmd:WebShapeCmd --bind "$(WEB_BIND)" --base-url "$(WEB_BASE_URL)" $(foreach host,$(WEB_ALLOW_HOSTS),--allow-host "$(host)") $(if $(strip $(WEB_TRUSTED_PROXIES)),$(foreach proxy,$(WEB_TRUSTED_PROXIES),--trusted-proxy "$(proxy)"),--no-trusted-proxy)
