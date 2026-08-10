from ksignal.engine.velocity import compute_velocity
def test_velocity():
    v=compute_velocity("s","24h",{"sources":[1,2],"platforms":["a","b"],"metrics":{"likes":100},"roles":["official_context"]},{"sources":[1],"platforms":["a"],"metrics":{"likes":20}}); assert v.source_count_delta==1 and v.cross_platform_spread==2 and v.model_dump()["window"]=="24h"

