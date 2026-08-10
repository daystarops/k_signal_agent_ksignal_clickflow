from ksignal.engine.provider_health import ProviderHealthStore
def test_health(tmp_path):
    h=ProviderHealthStore(tmp_path/"health.json").update("a","down","AUTH_MISSING"); assert h.status.value=="down" and h.failure_mode=="AUTH_MISSING"
