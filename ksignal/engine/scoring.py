from pydantic import BaseModel, Field, computed_field

WEIGHTS = {"cultural_signal_strength":1.5,"korean_source_quality":1.5,"cross_correlation":1.3,"signal_noise_ratio":1.2,"official_context_quality":1.0,"signal_velocity_score":1.0,"freshness":.8,"western_global_context_quality":.8,"instagram_context_quality":.7,"comment_context_richness":.6,"visual_availability":.6,"lane_fit":.5,"cross_language_relevance":.5}

class CandidateScore(BaseModel):
    cultural_signal_strength: float=Field(0,ge=0,le=10); cross_language_relevance: float=Field(0,ge=0,le=10)
    korean_source_quality: float=Field(0,ge=0,le=10); official_context_quality: float=Field(0,ge=0,le=10)
    western_global_context_quality: float=Field(0,ge=0,le=10); instagram_context_quality: float=Field(0,ge=0,le=10)
    comment_context_richness: float=Field(0,ge=0,le=10); visual_availability: float=Field(0,ge=0,le=10)
    freshness: float=Field(0,ge=0,le=10); lane_fit: float=Field(0,ge=0,le=10)
    signal_noise_ratio: float=Field(0,ge=0,le=10); cross_correlation: float=Field(0,ge=0,le=10)
    signal_velocity_score: float=Field(0,ge=0,le=10)

    @computed_field
    @property
    def total_weighted(self)->float:
        return round(sum(getattr(self,k)*w for k,w in WEIGHTS.items())/sum(WEIGHTS.values()),2)

    @computed_field
    @property
    def auto_queue_eligible(self)->bool:
        return self.total_weighted>=7.5 and self.cross_correlation>=6 and self.signal_noise_ratio>=6 and self.korean_source_quality>=7
