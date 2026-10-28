"""Takes `.html` out of every link between the site's own pages.

GitHub Pages serves `guide.html` at `/guide` and `wiki/en/index.html` at
`/wiki/en/`, so a link may name the page without its extension -- and the
address a reader copies out of the bar is then `/wiki/en/animals`, not
`/wiki/en/animals.html`. The files keep their names: renaming them to
`animals/index.html` folders would do the same for the bar, and would also
break every link anyone has already shared.

Only links the site writes itself are touched: a relative `href` with no
scheme. `index.html` becomes its folder (`./` when it is this one), and a
`#fragment` rides along. The language picker's script names its target the
same way and is rewritten with it.

Why links and not the server: Pages cannot be told to redirect, so the old
`.html` addresses keep working beside the new ones -- nothing shared breaks.

    python -I tools/clean_urls.py [file or folder ...]   # default: the site
"""
import pathlib
import re
import sys

SITE = pathlib.Path(__file__).resolve().parent.parent

HREF = re.compile(r'href="(?![a-z][a-z0-9+.-]*:|#|/)([^"#]*?)\.html(#[^"]*)?"')


def clean_href(match: re.Match) -> str:
    path, fragment = match.group(1), match.group(2) or ""
    if path == "index" or path.endswith("/index"):
        path = path[: -len("index")] or "./"
    return f'href="{path}{fragment}"'


def clean(text: str) -> str:
    text = HREF.sub(clean_href, text)
    # wiki/lang.js: the picker sends a first visit to "<code>/index.html"
    return text.replace('code + "/index.html"', 'code + "/"')


def main(targets: list[str]) -> None:
    roots = [pathlib.Path(t).resolve() for t in targets] or [SITE]
    changed = 0
    for root in roots:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.suffix in (".html", ".js")]
        for page in files:
            if "tools" in page.relative_to(SITE).parts:
                continue
            raw = page.read_bytes().decode("utf-8")
            new = clean(raw)
            if new != raw:
                page.write_bytes(new.encode("utf-8"))
                changed += 1
    print(f"clean urls: {changed} files rewritten")


if __name__ == "__main__":
    main(sys.argv[1:])
