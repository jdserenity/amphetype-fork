# Deploy

## Dev (local)

Requires Python 3.11 (PyQt5 does not install reliably on 3.12+).

From repo root:

```sh
uv venv venv --python 3.11
source venv/bin/activate

uv pip install -r requirements.txt
uv pip install -e .
```

Launch:

```sh
amphetype
```

Or:

```sh
python -c "from amphetype.main import main_normal; main_normal()"
```

Subsequent runs: `source venv/bin/activate` then `amphetype`.
