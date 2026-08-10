from pathlib import Path
from jinja2 import Environment,FileSystemLoader,select_autoescape
TEMPLATE_DIR=Path(__file__).parent/"templates"
def render_template(name,data): return Environment(loader=FileSystemLoader(TEMPLATE_DIR),autoescape=select_autoescape(["html"])).get_template(name).render(**data)

