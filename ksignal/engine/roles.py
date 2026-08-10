from .models import SourceRole

LAYER_ROLES = {
    "korean_native": {SourceRole.KOREAN_NATIVE_SIGNAL, SourceRole.ORIGIN_SIGNAL},
    "official": {SourceRole.OFFICIAL_CONTEXT},
    "western_global": {SourceRole.WESTERN_CONTEXT, SourceRole.GLOBAL_FANDOM_REACTION},
    "instagram_social": {SourceRole.INSTAGRAM_CONTEXT},
    "creative_reference": {SourceRole.VISUAL_REFERENCE, SourceRole.RECEIPT},
}

def layer_status(nodes):
    roles = {role for n in nodes for role in n.source_roles}
    return {name: ("present" if roles & expected else "missing") for name, expected in LAYER_ROLES.items()}

