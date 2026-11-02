.PHONY: db ask eval web test clean

db:
	python scripts/build_db.py

ask:
	python -m datapilot.cli ask "$(q)"

eval:
	python -m datapilot.cli eval --output eval

web:
	python web/server.py --port 8000

test:
	python -m unittest discover -s tests -v

clean:
	rm -rf __pycache__ datapilot/__pycache__ web/__pycache__ tests/__pycache__ .test_tmp
