from ksignal.engine.models import *
def test_status_exactly_six(): assert {x.value for x in AccessStatus}=={"captured","degraded","denied","lost","error","pending"}
def test_source_and_capture_serialize():
    c=CaptureVersion(provider="x",access_status="captured"); n=SourceNode(issue_id="1",candidate_id="c",url="https://example.com",capture_versions=[c],source_roles=["receipt"])
    assert n.model_dump(mode="json")["capture_versions"][0]["access_status"]=="captured"; assert n.source_roles==[SourceRole.RECEIPT]

