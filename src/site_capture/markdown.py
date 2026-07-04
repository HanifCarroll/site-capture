from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin


class HTMLToMarkdown(HTMLParser):
    def __init__(self, *, base_url: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.link_stack: list[str | None] = []
        self.skip_depth = 0
        self.heading_level: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value for key, value in attrs}
        if tag in {"script", "style", "svg", "noscript"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"p", "div", "section", "article", "main", "header", "footer", "br"}:
            self._newline()
        elif tag in {"li"}:
            self._newline()
            self.parts.append("- ")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._newline()
            self.heading_level = int(tag[1])
            self.parts.append("#" * self.heading_level + " ")
        elif tag == "a":
            href = attrs_dict.get("href")
            self.link_stack.append(urljoin(self.base_url, href) if href and self.base_url else href)
            self.parts.append("[")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("_")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "a":
            href = self.link_stack.pop() if self.link_stack else None
            self.parts.append(f"]({href})" if href else "]")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("_")
        elif tag in {"p", "div", "section", "article", "main", "header", "footer", "li"}:
            self._newline()
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_level = None
            self._newline()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self.parts and self.parts[-1] and not self.parts[-1].endswith(("\n", " ", "[", "- ")):
            self.parts.append(" ")
        self.parts.append(text)

    def markdown(self) -> str:
        text = "".join(self.parts)
        lines = [line.rstrip() for line in text.splitlines()]
        compact: list[str] = []
        blank = False
        for line in lines:
            if not line:
                if not blank:
                    compact.append("")
                blank = True
                continue
            compact.append(line)
            blank = False
        return "\n".join(compact).strip() + "\n"

    def _newline(self) -> None:
        if not self.parts:
            return
        current = "".join(self.parts[-2:])
        if current.endswith("\n\n"):
            return
        if current.endswith("\n"):
            self.parts.append("\n")
        else:
            self.parts.append("\n\n")


def html_to_markdown(html: str, *, base_url: str | None = None) -> str:
    parser = HTMLToMarkdown(base_url=base_url)
    parser.feed(html)
    return parser.markdown()
