-- Migration number: 0001 	 2026-08-20T00:00:00.000Z
--
-- Public "Correct the read" submissions, held for editorial review.
--
-- Nothing here identifies a submitter beyond what they chose to type: no IP address, no
-- geolocation, no request headers, no fingerprint. Reviewing a correction needs the correction and
-- the article it points at, and storing more would be a liability we have no use for.

CREATE TABLE corrections (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',

  -- Where the correction came from. Bounded and sanitised by the Worker, never trusted as
  -- authorisation data: this endpoint is public and grants nothing.
  issue_id TEXT,
  card_id TEXT,
  article_slug TEXT,
  source_page TEXT,

  -- What the reader chose to tell us. Only `comment` is required.
  name TEXT,
  email TEXT,
  comment TEXT NOT NULL,
  context_correction INTEGER NOT NULL DEFAULT 0,
  consent_state TEXT
);

-- The review queue is "pending, newest first", so one composite index serves both the filter and
-- the ordering. Its `status` prefix also covers status-only counts, and a separate `created_at`
-- index is not added because no query orders the whole table without filtering by status first.
CREATE INDEX idx_corrections_status_created_at ON corrections (status, created_at DESC);

-- The other way a correction is read: everything filed against one article, when an editor is
-- deciding whether a story needs amending.
CREATE INDEX idx_corrections_article_slug ON corrections (article_slug);
