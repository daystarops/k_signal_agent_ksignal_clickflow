from pydantic import BaseModel,Field
class RenderAsset(BaseModel):
    asset_id:str; render_target:str; template:str; html_path:str|None=None; output_path:str; width:int=1080; height:int=1350; status:str="pending"
class AssetManifest(BaseModel):
    issue_id:str; candidate_id:str; assets:list[RenderAsset]=Field(default_factory=list)

