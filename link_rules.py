import re
from typing import List, Tuple

# Transform HTML text (message.html_text / caption) replacing URLs per rules.
# Rules: list of (pattern, replacement), applied sequentially with re.sub
def replace_links_in_html(html: str, rules: List[Tuple[str, str]]) -> str:
    if not html or not rules:
        return html or ""

    # Replace inside href="..."
    def repl_href(match):
        url = match.group(1)
        new = url
        for pat, rep in rules:
            try:
                new = re.sub(pat, rep, new, flags=re.IGNORECASE)
            except re.error:
                pass
        return f'href="{new}"'

    html = re.sub(r'href="([^"]+)"', repl_href, html)

    # Replace visible raw URLs (not all will be caught, but good coverage)
    def repl_raw(match):
        orig = match.group(0)
        new = orig
        for pat, rep in rules:
            try:
                new = re.sub(pat, rep, new, flags=re.IGNORECASE)
            except re.error:
                pass
        return new

    # Basic URL regex
    html = re.sub(r'(https?://[^\s<]+)', repl_raw, html)
    return html
