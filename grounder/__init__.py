"""Grounder package for GUI Agent"""

from grounder.grounder import ground
from grounder.models import OmniParserResult, ParsedElement

__all__ = ["ground", "OmniParserResult", "ParsedElement"]

# ground() return type:  Tuple[Image.Image, str, List[ParsedElement]]
#   [0] enhanced_image  — annotated PIL Image
#   [1] screen_info     — set-of-mark text for MLLM prompt injection
#   [2] interactable    — List[ParsedElement] for executor element resolution
