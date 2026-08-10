# Creative Render Pipeline

Template → HTML render → PNG capture → asset manifest → EDL → optional ffmpeg export. Candidate data populates Jinja templates. Playwright is preferred for screenshots; a clearly degraded placeholder preserves pipeline continuity if browser rendering fails. ffmpeg is an exporter only.

