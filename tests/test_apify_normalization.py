from ksignal.engine.providers.apify_instagram_provider import ApifyInstagramProvider
def test_missing_token(monkeypatch,tmp_path):
    monkeypatch.delenv("APIFY_TOKEN",raising=False); p=ApifyInstagramProvider(output_root=tmp_path); assert p.health()=={"provider_id":"apify_instagram","status":"down","failure_mode":"AUTH_MISSING"}
def test_normalization_preserves(tmp_path):
    item={"url":"https://instagram.com/p/x/","caption":"hi #tag @user","likesCount":9,"commentsCount":2,"videoViewCount":20,"ownerUsername":"owner","displayUrl":"https://image"}; n=ApifyInstagramProvider("token",tmp_path).normalize_to_source(item,{"issue_id":"002","candidate_id":"c"}); assert n.hashtags==["tag"]; assert n.mentions==["user"]; assert n.capture_versions[0].visible_metrics["likesCount"]==9; assert n.provider_metadata["ownerUsername"]=="owner"; assert n.raw_provider_payload_path

