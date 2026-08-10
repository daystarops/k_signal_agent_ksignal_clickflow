# Low-touch local setup

## macOS

1. Unzip the folder.
2. Double-click `setup.command`.
3. Add your `OPENAI_API_KEY` when `.env` opens.
4. Double-click `inspect.command` to test one Korean URL.
5. Double-click `run.command` to run the configured sources.

If macOS blocks the `.command` file, right-click it, choose **Open**, then approve it.

## Windows

Use the click-flow files:

1. Double-click `setup_windows.bat` once.
2. Add your `OPENAI_API_KEY` and optional `WEBHOOK_URL` in `.env`.
3. Double-click `launcher_windows.bat`.
4. Pick option 2 for newsletter draft, option 3 to push to n8n, or option 4 to do both.

See `README_WINDOWS_CLICK_FLOW.md` for the full Windows flow.

## Docker option

Docker keeps Python/Playwright inside a container so your machine stays cleaner:

```bash
docker compose build
docker compose run --rm ksignal python main.py run --limit-per-source 3 --max-cards 5 --download-images true --render-screenshots true --vision true
```

Create `.env` first from `.env.example` and add your keys.
