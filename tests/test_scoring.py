from ksignal.engine.scoring import CandidateScore,WEIGHTS
def test_weighted_and_queue():
    s=CandidateScore(**{k:8 for k in WEIGHTS}); assert s.total_weighted==8; assert s.auto_queue_eligible
def test_gate(): assert not CandidateScore(cultural_signal_strength=10).auto_queue_eligible

