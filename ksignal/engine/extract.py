import hashlib
def content_hash(text): return hashlib.sha256((text or "").encode()).hexdigest()
def extract_visible_metrics(payload): return {k:payload.get(k) for k in ("likesCount","commentsCount","videoViewCount") if payload.get(k) is not None}

