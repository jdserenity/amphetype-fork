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

**App:** On launch, `typing_program/license.py` calls Lemon Squeezy’s public License API (`/v1/licenses/activate` and `/validate`). No merchant API key in the app. Stored in settings: `license_key`, `license_instance_id`, `license_machine_id`.

**Dev without a key:** `typing-program --skip-license` or `TYPING_PROGRAM_SKIP_LICENSE=1`.

**Optional:** set `TYPING_PROGRAM_CHECKOUT_URL` so the in-app “Buy” button matches your checkout link.

## Packaging (installers for sale)

Turns the app into a self-contained download so buyers need no Python. Tool: **PyInstaller** (recipe in `typing_program.spec`, launcher `typing_program/main_entry.py`).

**Key rule:** PyInstaller can only build for the OS it runs on. A Windows build must run on Windows, a Mac build on a Mac, a Linux build on Linux. There is no cross-compile.

### macOS (.app + .dmg)

From repo root on a Mac:

```sh
./scripts/build-mac-dmg.sh
```

Output:

- `dist/Typing Program.app` — the app bundle
- `dist/Typing Program.dmg` — drag-to-Applications disk image (upload this to Lemon Squeezy)
- `dist/Typing Program-mac.zip` — for in-app updates: `python scripts/mac_app_zip.py` after the PyInstaller step

The script creates a venv, installs PyInstaller + Pillow, runs `typing_program.spec`, then wraps the `.app` in a `.dmg` via `scripts/mac_dmg.py` (`hdiutil`).

Smoke-test the frozen app:

```sh
TYPING_PROGRAM_SKIP_LICENSE=1 TYPING_PROGRAM_LOGFILE=- dist/Typing\ Program.app/Contents/MacOS/Typing\ Program
```

v1 ships **unsigned** — buyers see macOS Gatekeeper’s “unverified developer” warning until Apple code signing + notarization is added. A `.dmg` does not bypass that; it only improves the download experience.

### Windows (.zip)

From repo root on Windows (PowerShell):

```powershell
.\scripts\build-windows.ps1
```

Output: `dist/Typing Program-win.zip` — extract the `Typing Program` folder and run `Typing Program.exe`.

v1 ships **unsigned** — SmartScreen may warn until code signing is added.

### Linux (.tar.gz)

From repo root on Linux:

```sh
./scripts/build-linux.sh
```

Output: `dist/Typing Program-linux.tar.gz` — extract and run `./Typing\ Program/Typing\ Program`.

### GitHub Actions (manual builds, one workflow per OS)

Each workflow triggers **only** via **workflow_dispatch** (GitHub → Actions → pick the workflow → **Run workflow**). Nothing runs on push or pull request. Run them separately when you need that platform’s installer.

| Workflow | File | Artifact |
|----------|------|----------|
| Build macOS installer | `.github/workflows/build-mac.yml` | `Typing Program.dmg` |
| Build Windows installer | `.github/workflows/build-windows.yml` | `Typing Program-win.zip` |
| Build Linux installer | `.github/workflows/build-linux.yml` | `Typing Program-linux.tar.gz` |

Download the artifact from the completed run, then upload to Lemon Squeezy.

### Ship

Upload per-OS installers to Lemon Squeezy → product → **Files**; LS emails download links to buyers.

For **in-app updates**, also publish zip/tar.gz builds to R2 (see below). Mac first-install email can stay `.dmg`; the updater uses `Typing Program-mac.zip`.

## In-app updates (R2 + Cloudflare)

Paying users update from **Preferences → General Options → Check for updates…** without re-entering a license key.

### One-time Cloudflare setup

1. Create the R2 bucket (once):
   ```sh
   npx wrangler r2 bucket create typing-program-updates
   ```
2. Cloudflare dashboard → **Workers & Pages** → **typing-program** → **Settings → Environment variables** (production + preview):
   - `UPDATE_SIGNING_SECRET` — long random string (signs short-lived download tokens). Copy into `website/.dev.vars` for local preview.
   - `LEMONSQUEEZY_API_KEY` — already used for `/thanks.html`; license validation for updates uses the public License API (no extra LS key in the app).
3. `wrangler.jsonc` binds R2 as `UPDATES` → `typing-program-updates`. Redeploy Pages after changing `wrangler.jsonc`.

### Publish a release to R2

After building installers:

| OS | Build output for R2 | Notes |
|----|---------------------|-------|
| macOS | `dist/Typing Program-mac.zip` | `python scripts/mac_app_zip.py` after PyInstaller (`.dmg` is email-only) |
| Windows | `dist/Typing Program-win.zip` | from `scripts/build-windows.ps1` |
| Linux | `dist/Typing Program-linux.tar.gz` | from `scripts/build-linux.sh` |

From repo root (requires `npx wrangler login`):

```sh
./scripts/publish-update.sh 1.3.0 darwin "dist/Typing Program-mac.zip"
./scripts/publish-update.sh 1.3.0 win32 "dist/Typing Program-win.zip"
./scripts/publish-update.sh 1.3.0 linux "dist/Typing Program-linux.tar.gz"
```

Each run uploads the file to `releases/<version>/…`, updates `manifest.json` in R2, and sets `release_notes` when you edit the manifest locally before the last platform upload (or edit manifest in R2). Bump `typing_program/VERSION` before building.

Manifest shape: `updates/manifest.example.json`.

### API routes (Pages Functions)

- `POST /api/check-update` — body: `license_key`, `instance_id`, `platform` (`darwin` / `win32` / `linux`), `current_version`. Returns `update_available`, and when true: `version`, `sha256`, `download_url`, `release_notes`.
- `GET /api/download-update?token=…` — streams the R2 object after HMAC token check.

Local preview: `website/.dev.vars` with `UPDATE_SIGNING_SECRET`; upload a test manifest + file to R2, or mock R2 in dev.

Override update URL in the app: `TYPING_PROGRAM_UPDATE_API=https://YOUR_DOMAIN/api/check-update`.


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
typing-program --skip-license
```

(`--skip-license` or `TYPING_PROGRAM_SKIP_LICENSE=1` skips the Lemon Squeezy gate during development.)

Or:

```sh
python -c "from typing_program.main import main_normal; main_normal()"
```

Subsequent runs: `source venv/bin/activate` then `typing-program`.
