"""
Prompt library - loads LLM prompt templates from the prompts/ directory.

Why this exists: every tracker's summarizer used to hardcode its own prompt
strings, and they drifted - critically, the anti-fabrication guardrails existed
only in some copies (threat_intel had full IOC rules; defender/microsoft_products
and thirdparty had none). Templates now live in prompts/*.yaml with shared
blocks (guardrails, injection delimiters, no-questions rules) defined once in
prompts/common.yaml and referenced by name from every template.

Template syntax: string.Template ($var / ${var}) - chosen over str.format so
prompts containing literal JSON braces (threat_intel asks for JSON output)
need no escaping. A literal dollar sign in a prompt must be written as $$.

Usage:
    from core.prompt_library import render

    user_prompt = render('threat_intel.advisory.user', title=..., content=..., iocs_text=...)
    system_prompt = render('threat_intel.advisory.system')

Names are '<file>.<dotted.path>' into the YAML, e.g. 'youtube.article.user'
-> prompts/youtube.yaml -> article: -> user:. Shared blocks from common.yaml
are auto-available in every template as $BLOCK_<UPPERCASED_KEY>, e.g. a
common.yaml key 'no_questions' is referenced as $BLOCK_NO_QUESTIONS.

Substitution is strict: a template variable with no value raises KeyError so a
renamed placeholder fails loudly in tests rather than emitting '$title' to the
LLM.
"""

import logging
import os
from string import Template

import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")

_cache = {}        # filename -> parsed YAML dict
_blocks_cache = None  # common.yaml blocks as $BLOCK_* substitution vars


def _load_file(name):
    if name not in _cache:
        path = os.path.join(PROMPTS_DIR, f"{name}.yaml")
        with open(path, "r", encoding="utf-8") as f:
            _cache[name] = yaml.safe_load(f) or {}
    return _cache[name]


def _blocks():
    """common.yaml entries exposed as BLOCK_<KEY> substitution variables."""
    global _blocks_cache
    if _blocks_cache is None:
        common = _load_file("common")
        _blocks_cache = {f"BLOCK_{k.upper()}": str(v).rstrip("\n") for k, v in common.items()}
    return _blocks_cache


def get_template(name):
    """
    Fetch the raw template string for a dotted name like 'youtube.article.user'.

    Raises KeyError with a helpful message if the path doesn't exist.
    """
    parts = name.split(".")
    node = _load_file(parts[0])
    for key in parts[1:]:
        if not isinstance(node, dict) or key not in node:
            raise KeyError(f"Prompt '{name}' not found (missing '{key}' in prompts/{parts[0]}.yaml)")
        node = node[key]
    if not isinstance(node, str):
        raise KeyError(f"Prompt '{name}' resolves to a section, not a template string")
    return node


def render(name, **variables):
    """
    Render the named template with strict substitution.

    Shared common.yaml blocks are always available as $BLOCK_*; caller-supplied
    variables fill the rest. Missing variables raise KeyError.
    """
    template = Template(get_template(name))
    return template.substitute({**_blocks(), **variables}).strip()


def clear_cache():
    """Drop cached YAML (used by tests that write temporary prompt files)."""
    global _blocks_cache
    _cache.clear()
    _blocks_cache = None
