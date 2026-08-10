from ksignal.render import CreativeRenderer
def test_render(tmp_path):
    m=CreativeRenderer(tmp_path).render("2","c",{"working_headline":"Signal"}); assert len(m.assets)==7; assert (tmp_path/"issues/2/creative/c/asset_manifest.json").exists(); assert all(__import__("pathlib").Path(a.output_path).exists() for a in m.assets)

