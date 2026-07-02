# Deploy

## Website (Cloudflare Pages)

Static landing page in `website/` — no build step.

### Local preview

```sh
cd website
npm install
npm run dev
```

Wrangler picks port 8788, or the next free port if that one is taken (printed in the terminal).

### Deploy (CLI)

From repo root (uses `wrangler.jsonc`):

```sh
cd website && npm install
npx wrangler pages deploy . --project-name=typing-program
```

First run creates the Pages project if it does not exist (`npx wrangler login` required).

### Deploy (Git)

Cloudflare dashboard → Workers & Pages → Create → Connect to Git → select this repo:

| Setting | Value |
|---------|-------|
| Production branch | `main` (or your release branch) |
| Root directory | `website` |
| Build command | *(leave empty)* |
| Build output directory | `/` |

Preview deployments are created automatically for other branches/PRs.

### Lemon Squeezy (checkout + license)

**Lemon Squeezy generates license keys** — no library needed. Enable them on the product; each sale gets a unique key in the receipt email.

**Your checklist** (Lemon Squeezy dashboard):

1. Create a store and a **digital product** — $5, one-time.
2. Product → **License keys** → enable. Set **activation limit** (e.g. `3` for a few machines/reinstalls).
3. Product → **Files** → upload installers when you have them (`.exe`, `.dmg`, `.zip`). Lemon Squeezy emails download links to buyers — simplest way to deliver the app; no R2 required for v1.
4. Copy the **checkout URL** (Share → checkout link for the variant).
5. Paste it into `website/checkout.json` as `checkout_url` and deploy.
6. Product → **Confirmation modal** / **Receipt button** → redirect URL:
   ```
   https://YOUR_DOMAIN/thanks.html?order_id=[order_id]
   ```
   Lemon Squeezy replaces `[order_id]` after checkout. The thanks page calls `/api/verify-order` (Cloudflare Pages Function) to confirm the order is paid before showing instructions.
7. Cloudflare Pages → **Settings → Environment variables** → add secret `LEMONSQUEEZY_API_KEY` (from LS Settings → API). Optional: `LEMONSQUEEZY_STORE_ID` so only your store’s orders count.
8. Local function preview: copy `website/.dev.vars.example` to `website/.dev.vars`, then `npm run dev` from `website/`.

**Website:** `website/main.js` reads `checkout.json` and wires `[data-checkout]` links to Lemon Squeezy.

**App:** On launch, `amphetype/license.py` calls Lemon Squeezy’s public License API (`/v1/licenses/activate` and `/validate`). No merchant API key in the app. Stored in settings: `license_key`, `license_instance_id`, `license_machine_id`.

**Dev without a key:** `amphetype --skip-license` or `TYPING_PROGRAM_SKIP_LICENSE=1`.

**Optional:** set `TYPING_PROGRAM_CHECKOUT_URL` so the in-app “Buy” button matches your checkout link.

## Packaging (installers for sale)

Turns the app into a self-contained download so buyers need no Python. Tool: **PyInstaller** (recipe in `amphetype.spec`, launcher `amphetype/main_entry.py`).

**Key rule:** PyInstaller can only build for the OS it runs on. A Windows build must run on Windows, a Mac build on a Mac, a Linux build on Linux. There is no cross-compile.

### Build (any platform)

From repo root, in the Python 3.11 venv (`docs/DEPLOY.md` → Dev), with build tools installed:

```sh
uv pip install pyinstaller pillow
pyinstaller amphetype.spec --noconfirm --clean
```

- macOS → `dist/Amphetype.app`
- Windows / Linux → `dist/Amphetype/` (whole folder is the app; the launcher is `Amphetype`/`Amphetype.exe` inside)

`pillow` lets PyInstaller convert `amphetype.ico` into the icon each OS wants.

### Smoke-test the build

Run the frozen binary with the license skipped and logging to stdout; it should open a window and load the bundled sample texts:

```sh
# macOS
TYPING_PROGRAM_SKIP_LICENSE=1 AMPH_LOGFILE=- dist/Amphetype.app/Contents/MacOS/Amphetype
```

If it exits immediately with "directory ... data not found" or "file ... VERSION not found", the spec failed to copy bundled files — check the `datas` block in `amphetype.spec`.

### Ship

Upload the per-OS installer to Lemon Squeezy → product → **Files**; LS emails download links to buyers (see the Lemon Squeezy section above). v1 ships **unsigned**, so buyers see an OS "unverified developer" warning; document the click-through for them until code signing is added.

**Not yet wired up (open work — see `docs/TODO.md`):** friendly installers (`.dmg` / Inno Setup `.exe` / AppImage), a GitHub Actions config to build all three OSes on a release tag, and code signing.

## Dev (local)

Requires Python 3.11 (PyQt5 does not install reliably on 3.12+).

From repo root, either run `./run-dev.sh` or:

```sh
uv venv venv --python 3.11
source venv/bin/activate

uv pip install -r requirements.txt
uv pip install -e .
```

Launch:

```sh
amphetype --skip-license
```

(`--skip-license` or `TYPING_PROGRAM_SKIP_LICENSE=1` skips the Lemon Squeezy gate during development.)

Or:

```sh
python -c "from amphetype.main import main_normal; main_normal()"
```

Subsequent runs: `source venv/bin/activate` then `amphetype`.
