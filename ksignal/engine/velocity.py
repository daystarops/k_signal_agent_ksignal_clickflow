from datetime import datetime,timezone
from .models import SignalVelocity
def compute_velocity(signal_id,window,current,previous=None):
    previous=previous or {}; sc=len(current.get("sources",[]))-len(previous.get("sources",[])); platforms=len(set(current.get("platforms",[]))); metrics={k:current.get("metrics",{}).get(k,0)-previous.get("metrics",{}).get(k,0) for k in set(current.get("metrics",{}))|set(previous.get("metrics",{}))}; roles=sorted(set(current.get("roles",[]))-set(previous.get("roles",[]))); recurrence=current.get("recurrence",0); decay=current.get("freshness_decay",0); score=max(0,min(10,sc*1.5+platforms+sum(max(0,v) for v in metrics.values())/1000+recurrence-decay)); prior_score=previous.get("velocity_score",0); acceleration=round(score-prior_score,2)
    return SignalVelocity(signal_id=signal_id,window=window,velocity_score=round(score,2),acceleration=acceleration,source_count_delta=sc,cross_platform_spread=platforms,new_roles_detected=roles,metric_delta_summary=metrics,interpretation="accelerating" if acceleration>1 else "decaying" if acceleration<0 else "stable")

