#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Подсветка синтаксиса, впечатанная прямо в HTML.

Сайт — статика без сборки и без JavaScript, и подсветка не повод это
менять: подключать highlight.js ради восьми блоков команд значит поставить
страницы в зависимость от чужого CDN и от того, включён ли у посетителя
скрипт. Здесь разметка кладётся в файл один раз, а браузеру остаётся
только раскрасить готовые <span> по CSS.

Скрипт идемпотентен: перед работой он снимает свои прежние <span>, так
что повторный запуск после правки текста даёт тот же результат, а не
подсветку поверх подсветки.

    python tools/highlight.py            # все страницы рядом со скриптом
    python tools/highlight.py index.html # только эти
"""

import io
import os
import re
import sys

# Команды, которые в начале строки означают именно команду, а не слово.
COMMANDS = {
    "cargo", "git", "cd", "cp", "copy", "sudo", "apt-get", "bash", "sh",
    "pwsh", "python", "python3", "adb", "curl", "mkdir", "rm", "ls",
    "./package-android.sh", "./primitive_client", "primitive_client.exe",
    "primitive_server.exe",
}

# Позиция команды открывается заново после этих разделителей.
SEPARATORS = {"&amp;&amp;", "|", ";", "&amp;"}

SPAN = '<span class="tok-{}">{}</span>'

RE_BLOCK = re.compile(r"(<pre(?P<attrs>[^>]*)><code>)(?P<body>.*?)(</code></pre>)", re.S)
RE_SPAN_OPEN = re.compile(r'<span class="tok-[a-z]+">')
RE_SPAN_CLOSE = re.compile(r"</span>")
RE_ENTITY = re.compile(r"&[a-z]+;")


def strip_spans(text):
    """Снять подсветку прошлого запуска — ради идемпотентности."""
    return RE_SPAN_CLOSE.sub("", RE_SPAN_OPEN.sub("", text))


def classify(word, at_command_position):
    if word in SEPARATORS:
        return "op"
    if word.startswith("--") or (
        len(word) > 1 and word[0] == "-" and (word[1].isalpha() or word[1] == "-")
    ):
        return "flag"
    if word.startswith("&lt;") or word.startswith("["):
        return "arg"
    if len(word) > 1 and word[0] in "\"'" and word[-1] == word[0]:
        return "str"
    if at_command_position and word in COMMANDS:
        return "cmd"
    return None


# Строка в кавычках может содержать пробелы, поэтому разбор идёт
# сканером, а не разбиением по пробелам: "зашёл на сервер" — это один
# токен, а не три.
RE_TOKEN = re.compile(
    r'(?P<space>\s+)'
    r'|(?P<comment>\#[^\n]*)'
    r'|(?P<dstr>"[^"\n]*")'
    r"|(?P<sstr>'[^'\n]*')"
    r'|(?P<word>[^\s"\']+)'
)

# Ключевые слова Rhai — для блоков, помеченных lang-rhai.
KEYWORDS = {"fn", "let", "const", "if", "else", "for", "in", "while",
            "return", "true", "false"}


def highlight_shell(body, keywords=False):
    """Команды оболочки: команда, ключи, строки, подстановки, комментарии."""
    out_lines = []
    for line in body.split("\n"):
        out = []
        at_command = True
        for m in RE_TOKEN.finditer(line):
            kind_name = m.lastgroup
            text = m.group()
            if kind_name == "space":
                out.append(text)
                continue
            if kind_name == "comment":
                out.append(SPAN.format("comment", text))
                continue
            if kind_name in ("dstr", "sstr"):
                out.append(SPAN.format("str", text))
                at_command = False
                continue
            kind = classify(text, at_command)
            if kind is None and keywords and text.strip("(){};,") in KEYWORDS:
                kind = "cmd"
            out.append(SPAN.format(kind, text) if kind else text)
            at_command = text in SEPARATORS
        out_lines.append("".join(out))
    return "\n".join(out_lines)


def highlight_cmdlist(body):
    """Список команд «имя  аргументы  пояснение» — как в справке сервера."""
    out_lines = []
    for line in body.split("\n"):
        if not line.strip():
            out_lines.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        rest = line[len(indent):]
        # Пояснение начинается там, где идут два пробела и больше.
        parts = re.split(r"(\s{2,})", rest, maxsplit=1)
        head = parts[0]
        gap = parts[1] if len(parts) > 2 else ""
        tail = parts[2] if len(parts) > 2 else ""

        words = re.split(r"(\s+)", head)
        marked = []
        first = True
        for word in words:
            if word.strip() == "":
                marked.append(word)
                continue
            if first:
                marked.append(SPAN.format("cmd", word))
                first = False
            elif word.startswith("&lt;") or word.startswith("["):
                # <x> и [n] — то, что игрок подставляет сам.
                marked.append(SPAN.format("arg", word))
            else:
                # Синонимы и готовые значения (day night, clear|rain|storm)
                # печатаются буквально, поэтому это тоже команда, а не ключ.
                marked.append(SPAN.format("lit", word))
        out = indent + "".join(marked) + gap
        if tail:
            out += SPAN.format("comment", tail)
        out_lines.append(out)
    return "\n".join(out_lines)


# Rust, а заодно WGSL и RON — у всех трёх комментарий `//`, строка в
# двойных кавычках и `fn`. Разбирать их как оболочку нельзя: там `#`
# открывает комментарий, и `#[allow(...)]` посерел бы целиком, а `// ...`
# не посерел бы вовсе.
RUST_KEYWORDS = {
    "fn", "pub", "mod", "use", "let", "mut", "const", "static", "struct",
    "enum", "impl", "trait", "match", "if", "else", "for", "in", "while",
    "loop", "return", "as", "where", "self", "Self", "crate", "true",
    "false", "Some", "None", "Ok", "Err",
}

RE_RUST = re.compile(
    r'(?P<comment>//[^\n]*)'
    r'|(?P<str>"(?:[^"\\\n]|\\.)*")'
    r'|(?P<attr>#!?\[[^\]\n]*\])'
    r'|(?P<entity>&[a-z]+;)'
    r'|(?P<macro>\b[A-Za-z_][A-Za-z0-9_]*!)'
    r'|(?P<word>\b[A-Za-z_][A-Za-z0-9_]*\b)'
)


def highlight_rust(body):
    """Rust, WGSL и RON: ключевые слова, макросы, строки, атрибуты, комментарии."""
    def repl(m):
        kind, text = m.lastgroup, m.group()
        if kind == "comment":
            return SPAN.format("comment", text)
        if kind == "str":
            return SPAN.format("str", text)
        if kind == "attr":
            return SPAN.format("arg", text)
        if kind == "macro":
            return SPAN.format("lit", text)
        if kind == "word" and text in RUST_KEYWORDS:
            return SPAN.format("cmd", text)
        # Сущности (&amp;, &lt;) — как есть: «amp» внутри них не слово.
        return text
    return RE_RUST.sub(repl, body)


def process(path):
    src = io.open(path, encoding="utf-8").read()

    def repl(m):
        body = strip_spans(m.group("body"))
        attrs = m.group("attrs") or ""
        if "lang-cmdlist" in attrs:
            body = highlight_cmdlist(body)
        elif "lang-rust" in attrs:
            body = highlight_rust(body)
        else:
            body = highlight_shell(body, keywords="lang-rhai" in attrs)
        return m.group(1) + body + m.group(4)

    out = RE_BLOCK.sub(repl, src)
    if out != src:
        io.open(path, "w", encoding="utf-8").write(out)
        return True
    return False


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = sys.argv[1:] or [
        os.path.join(root, name)
        for name in ("index.html", "download.html", "guide.html",
                     "server.html", "code.html", "modding.html")
    ]
    for path in targets:
        changed = process(path)
        print(("обновлено " if changed else "без изменений ") + os.path.basename(path))


if __name__ == "__main__":
    main()
