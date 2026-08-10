from .models import ConfidenceGrade
PREFIX={ConfidenceGrade.A:"Multiple sources confirm…",ConfidenceGrade.B:"{source} states…",ConfidenceGrade.C:"{platform} users report…",ConfidenceGrade.D:"{platform} discourse suggests…"}
def frame_claim(claim,source="Official source",platform="Platform"):
    prefix=PREFIX[claim.confidence_grade].format(source=source,platform=platform)
    return f"{prefix} {claim.claim_text}"

