setup:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -r requirements.txt && python -m playwright install chromium
	@if [ ! -f .env ]; then cp .env.example .env; fi

run:
	. .venv/bin/activate && python main.py run --limit-per-source 3 --max-cards 5 --download-images true --render-screenshots true --vision true

cheap:
	. .venv/bin/activate && python main.py run --limit-per-source 5 --max-cards 10 --vision false --render-screenshots false
