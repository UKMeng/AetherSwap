# Repository Guidelines

## Project Structure & Module Organization

AetherSwap is a Python 3.10+ FastAPI application with a static web dashboard.
Core backend code lives in `app/`: API setup is in `app/api.py`, desktop/server startup in `app/main.py`, route modules in `app/routes/`, background workers in `app/services/`, and buy/sell pipeline logic in `app/pipeline*.py` and `app/sell_pipeline.py`. External platform integrations are separated into `steam/`, `buff/`, and `steamdt/`. Shared helpers are in `utils/`, stability analysis in `analysis/`, static UI files in `web/`, and images in `images/`. Tests live in `tests/` and generally mirror the backend feature under test.

## Build, Test, and Development Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python run.py
python -m app
python -m uvicorn app.api:app --host 0.0.0.0 --port 28472
pytest tests/ -v
pytest tests/test_pipeline_steps.py -v
```

Use `python run.py` or `python -m app` for the normal desktop/webview flow. Use the `uvicorn` command when you only need the FastAPI service. Run the full pytest suite before submitting pipeline, config, database, or market-integration changes.

## Coding Style & Naming Conventions

Follow the existing lightweight style: 4-space Python indentation, snake_case modules/functions, descriptive constants in UPPER_CASE, and small route/service modules grouped by domain. Keep FastAPI route handlers thin and put reusable logic in `app/services/`, `utils/`, or the relevant integration package. JavaScript in `web/js/` uses 2-space indentation, `const`/`let`, semicolons, and camelCase names. No formatter config is checked in, so keep diffs consistent with surrounding files.

## Testing Guidelines

Tests use `pytest` plus `unittest.mock` where external Steam/Buff/network behavior must be isolated. Name files `tests/test_<feature>.py` and test functions `test_<expected_behavior>()`; Chinese test names already exist and are acceptable when they improve clarity. Prefer deterministic unit tests over live network tests. Add or update tests when changing pipeline filtering, config validation, database calculations, proxy behavior, or currency/listing guards.

## Commit & Pull Request Guidelines

Recent history uses short, imperative summaries in either English or Chinese, for example `Harden Steam market variant filter parsing` or `修复任务线并行问题以及细化buff错误状态`. Keep commits focused and mention the affected feature. PRs should include a concise summary, test results, any config or migration notes, linked issues when applicable, and screenshots for visible `web/` UI changes.

## Security & Configuration Tips

Never commit local secrets or runtime state. `.gitignore` already excludes `config/credentials.json`, `config/app_config.json`, `config/accounts.json`, Playwright profiles, SQLite files, exchange-rate/userdata caches, and `log/`. Treat Steam cookies, Buff credentials, proxy credentials, and token secrets as sensitive.
