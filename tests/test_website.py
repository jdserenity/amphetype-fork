import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBSITE = REPO_ROOT / "website"
INDEX = WEBSITE / "index.html"
WRANGLER = REPO_ROOT / "wrangler.jsonc"


@pytest.fixture
def index_html():
  return INDEX.read_text(encoding="utf-8")


def test_website_files_exist():
  for path in (INDEX, WEBSITE / "styles.css", WEBSITE / "main.js", WEBSITE / "favicon.svg", WRANGLER):
    assert path.is_file(), f"missing {path.relative_to(REPO_ROOT)}"


def test_index_has_required_sections(index_html):
  for fragment in ("id=\"features\"", "id=\"pricing\"", "<main>", "<title>", "Typing Program"):
    assert fragment in index_html


def test_index_no_amphetype_branding(index_html):
  assert "amphetype" not in index_html.lower()


def test_index_pricing(index_html):
  assert "$5" in index_html
  assert "lifetime" in index_html.lower()
  assert "yours forever" in index_html.lower()


def test_index_meta_description(index_html):
  assert 'name="description"' in index_html
  assert "typing" in index_html.lower()


def test_index_links_stylesheet_and_script(index_html):
  assert 'href="styles.css"' in index_html
  assert 'src="main.js"' in index_html


def test_wrangler_pages_config():
  raw = WRANGLER.read_text(encoding="utf-8")
  cfg = json.loads(raw)
  assert cfg["name"] == "typing-program"
  assert cfg["pages_build_output_dir"] == "./website"
