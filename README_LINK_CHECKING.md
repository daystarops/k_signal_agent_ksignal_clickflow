# Future regional redirect layer

The static newsletter uses the tested Source and Backup URLs. It does not attempt client-side IP detection or regional redirection.

A hosted K-Signal can later expose:

- `/go/{issue_id}/{card_id}/source`
- `/go/{issue_id}/{card_id}/backup`

These routes can select a tested regional destination with a Cloudflare Worker (`cf-ipcountry`), Vercel Edge Middleware, or a FastAPI redirect endpoint. Optional probes from US and Korean cloud regions can feed the same link-audit format before publication.

## Internal article routes

Local builds use `articles/card_01.html`. Set `SITE_BASE_URL` to emit canonical hosted routes such as `/issues/001/card-01`. Newsletter hero, headline, and CTA links stay internal; `/go/{issue_id}/{card_id}/{source|backup|video}` remains the future analytics and regional-fallback layer.
