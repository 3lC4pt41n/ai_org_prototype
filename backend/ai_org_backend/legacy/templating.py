from pathlib import Path
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent / "prompts"

class TemplateStore:
    """Loads and renders Jinja2 prompt templates for each agent role."""

    def __init__(self, template_dir: Path = TEMPLATE_DIR):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(enabled_extensions=(".j2",)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, role: str, **context: Dict[str, Any]) -> str:
        """Render template `role.j2` with the given context."""
        tmpl_name = f"{role}.j2"
        try:
            template = self.env.get_template(tmpl_name)
            return template.render(**context)
        except Exception as e:
            raise FileNotFoundError(f"Template '{tmpl_name}' not found or failed to render: {e}")

# Convenience singleton
TEMPLATES = TemplateStore()
