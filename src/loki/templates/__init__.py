"""Text templates for generated artifacts (repro scripts, HTML report), kept out of Python source.

Templates use `string.Template` `$name` placeholders, so the Python, CSS and JS inside them
is written as-is: no doubled `{{ }}` braces or escaped quotes. A missing value raises KeyError
instead of silently rendering a broken artifact.
"""
from functools import cache
from importlib.resources import files
from string import Template


@cache
def _load(name: str) -> Template:
    return Template(files(__name__).joinpath(name).read_text(encoding="utf-8"))


def render(name: str, **values: object) -> str:
    """Renders template `name` (a file in this package) with the given placeholder values."""
    return _load(name).substitute({key: str(value) for key, value in values.items()})
