"""Copies the player wiki from the game's repository into this site's wiki/.

The wiki is written in the game's repository (`wiki/`), beside the code it
was checked against, so that a change to a recipe and the page that names
it land in one commit. The site carries a copy. This script makes that copy
and adds the one thing only the site has: a link back to the site's front
page in every wiki header. Run it again whenever the wiki changes:

    python tools/sync_wiki.py [path to the game's wiki folder]

It deletes this site's wiki/ first, so a page removed in the game is
removed here too.
"""
import pathlib
import re
import shutil
import sys

SITE = pathlib.Path(__file__).resolve().parent.parent
SOURCE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\projects\rust\primitive\wiki")
if not SOURCE.exists():
    SOURCE = pathlib.Path(r"C:\Users\Admin\Downloads\flatcraft\wiki")

BACK = {"en": "&larr; site", "pl": "&larr; strona", "ru": "&larr; сайт", "es": "&larr; sitio"}

dest = SITE / "wiki"
if dest.exists():
    shutil.rmtree(dest)
shutil.copytree(SOURCE, dest)

pages = 0
for page in dest.rglob("*.html"):
    text = page.read_text(encoding="utf-8")
    lang = page.parent.name
    if lang in BACK:
        # after the brand, in the header row: the site's root is two up
        text = re.sub(
            r'(<a class="brand"[^>]*>.*?</a>)',
            lambda m: m.group(1) + '\n<a class="site" href="../../index.html">' + BACK[lang] + "</a>",
            text, count=1, flags=re.S)
    else:
        # the language picker, wiki/index.html: the root is one up
        text = text.replace(
            "</main>",
            '<p><a class="site" href="../index.html">&larr; сайт &middot; site</a></p>\n</main>', 1)
    # The site's icon, the game's kiln: the wiki in the game's repository
    # has none of its own, so every copy takes it here.
    if 'rel="icon"' not in text:
        up = "../" * (len(page.relative_to(SITE).parts) - 1)
        text = text.replace("</title>", "</title>
<link rel=\"icon\" type=\"image/png\" href=\"" + up + "img/favicon.png\">
<link rel=\"apple-touch-icon\" href=\"" + up + "img/apple-touch-icon.png\">", 1)
    page.write_text(text, encoding="utf-8")
    pages += 1

# The game keeps `.html` in its links, so the wiki also opens from a folder
# on disk; the site serves pages without it (`clean_urls`).
sys.path.insert(0, str(SITE / "tools"))
import clean_urls  # noqa: E402
clean_urls.main([str(dest)])

print(f"copied {SOURCE} -> {dest}, {pages} pages")
