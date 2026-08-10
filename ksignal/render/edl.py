def build_edl(assets,duration=3): return {"version":1,"timebase":30,"clips":[{"asset":a.output_path,"start":i*duration,"duration":duration} for i,a in enumerate(assets)]}

