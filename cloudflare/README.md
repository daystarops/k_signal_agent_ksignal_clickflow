# Cloudflare Worker — corrections endpoint

The publication is static. This Worker adds exactly one dynamic route, `POST /api/corrections`,
which replaces the Netlify Forms submission path the site used before the migration.

```
POST /api/corrections  ->  Worker  ->  D1 (corrections, status='pending')
everything else        ->  Static Assets, without invoking the Worker
```

| File | Purpose |
| --- | --- |
| `worker.js` | Request handler. Only export is the default handler — workerd rejects non-function named exports from an entrypoint. |
| `contract.js` | Limits, copy, column order and the INSERT statement, shared by the Worker and its tests. |
| `migrations/0001_create_corrections.sql` | The `corrections` table and its two indexes. |
| `wrangler.jsonc` | Local development and QA only. **Not** the deployed config — see below. |

## Where the client side comes from

The correction form markup and its submission script are emitted by `ksignal/_issue_builder_original.pyc`,
which is sourceless bytecode, into immutable issue outputs. Neither can be edited here. Both are
re-projected onto the published site by `core/site_assembler.py`:

- `_project_interaction_scripts()` rewrites the transport (`fetch('/')` → `fetch('/api/corrections')`,
  plus the JSON-`ok` check and the in-flight guard).
- `_project_correction_form()` rewrites the markup (drops `data-netlify`, `data-netlify-honeypot`
  and the hidden `form-name`; sets `action="/api/corrections"`).

Both fail the build loudly if the producer drifts. Do not hand-edit `outputs/`.

## Local development

```sh
npx wrangler d1 migrations apply k-signal-production --local --config cloudflare/wrangler.jsonc
npx wrangler dev --config cloudflare/wrangler.jsonc --port 8787
node --test tests/worker/corrections.test.mjs
```

`wrangler dev` serves `outputs/site` through the same Static Assets binding production uses, so
static routes are exercised exactly as deployed.

## Deploy-branch delta (`netlify-publish`)

Cloudflare deploys the generated `netlify-publish` branch. After the source side is approved, that
branch needs the publication as it is generated today **plus**:

```
netlify-publish/
  cloudflare/worker.js            <- copied from this directory
  cloudflare/contract.js          <- copied from this directory
  cloudflare/migrations/0001_create_corrections.sql
  wrangler.jsonc                  <- replaced, see below
  .assetsignore                   <- extended, see below
```

`wrangler.jsonc` (replaces the current assets-only config). The binding must be `DB` — that is
what `worker.js` reads; Cloudflare's dashboard snippet suggests `k_signal_production`, which
would leave `env.DB` undefined at runtime:

```jsonc
{
  "name": "k-signal",
  "main": "cloudflare/worker.js",
  "compatibility_date": "2026-08-20",
  "assets": {
    "directory": ".",
    "binding": "ASSETS",
    "run_worker_first": ["/api/*"]
  },
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "k-signal-production",
      "database_id": "153a6823-7de3-4969-8f1e-d95e97a9a0b5",
      // Root-relative here; the source config in `cloudflare/` says just "migrations".
      "migrations_dir": "cloudflare/migrations"
    }
  ]
}
```

`.assetsignore` — the Worker source, its config and its migrations must not be uploaded as public
static files. `main` is bundled separately, so ignoring `cloudflare/` does not affect the Worker:

```
wrangler.jsonc
.assetsignore
.git
cloudflare/
```

The remote migration is **already applied** (`0001_create_corrections.sql`, 2026-08-21), so the
deploy does not need to run it again.

`_headers` is unchanged. The `NETLIFY_HEADERS` constant in `core/host_packager.py` still produces
it; the name is historical and renaming it is out of scope for this migration.
