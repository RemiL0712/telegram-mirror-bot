import re
from typing import List, Tuple, Optional

# Патерн якірів <a href="...">текст</a>
A_TAG_RE = re.compile(
    r'(<a\s+[^>]*?href=")([^"]+)(".*?>)(.*?)(</a>)',
    re.IGNORECASE | re.DOTALL
)

# rules: list of (pattern, new_url, new_text_or_None)
def replace_links_in_html(html: str, rules: List[Tuple[str, str, Optional[str]]]) -> str:
    if not html or not rules:
        return html or ""

    def replace_a_tag(m: re.Match) -> str:
        prefix, href, mid, text, suffix = m.groups()
        new_href = href
        new_text = text
        for pat, url_repl, text_repl in rules:
            try:
                if re.search(pat, href, flags=re.IGNORECASE):
                    new_href = re.sub(pat, url_repl, href, flags=re.IGNORECASE)
                    if text_repl is not None:
                        new_text = text_repl
            except re.error:
                # некоректний regex — ігноруємо
                pass
        return f"{prefix}{new_href}{mid}{new_text}{suffix}"

    # 1) Замінюємо у <a href="...">...</a>
    html = A_TAG_RE.sub(replace_a_tag, html)

    # 2) Замінюємо «голі» URL у тексті (поза тегами) — лише URL, текст залишаємо як є
    def repl_raw(m: re.Match) -> str:
        orig = m.group(0)
        new_val = orig
        for pat, rep, _ in rules:
            try:
                new_val = re.sub(pat, rep, new_val, flags=re.IGNORECASE)
            except re.error:
                pass
        return new_val

    html = re.sub(r'(https?://[^\s<]+)', repl_raw, html)
    return html
