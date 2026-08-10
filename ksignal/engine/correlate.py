def correlate(nodes,lane=None):
    entity_map={}
    for node in nodes:
        for value in set(node.entities+node.hashtags+node.mentions): entity_map.setdefault(value.lower(),[]).append(node.source_id)
    links=[]
    ids=list(nodes)
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            shared=sorted((set(a.entities+a.hashtags+a.mentions)&set(b.entities+b.hashtags+b.mentions)))
            if shared: links.append({"source_a":a.source_id,"source_b":b.source_id,"shared":shared,"cross_platform":a.platform!=b.platform})
    return {"entity_map":entity_map,"source_links":links,"cross_platform_mirror_links":[x for x in links if x["cross_platform"]],"candidate_clusters":[{"candidate_id":k,"source_ids":[n.source_id for n in nodes if n.candidate_id==k],"lane":lane} for k in sorted({n.candidate_id for n in nodes})]}

