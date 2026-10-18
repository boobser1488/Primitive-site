#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Безопасная проверка доступности серверов Primitive.

## Почему это не делается в браузере

У игры нет анонимного запроса статуса: `Ping` в протоколе — это
keepalive **внутри установленной сессии**, а не «скажи, кто ты» с улицы.
Даже если бы он был, браузеру нечем его отправить: сырых сокетов на
странице нет, а игровой сервер не слушает HTTP.

Поэтому проверка живёт здесь, запускается владельцем сайта, а результат
впечатывается в `server.html` — как и подсветка синтаксиса. На странице
не появляется ни строчки JavaScript, и ни один посетитель ничего никуда
не отправляет.

## Что значит «безопасная»

* **Только соединение.** Скрипт открывает TCP-соединение и сразу
  закрывает его. Он не шлёт рукопожатие, не притворяется клиентом и не
  занимает слот игрока — сервер видит оборванный коннект, а не вход.
* **Только свой список.** Адреса берутся из `tools/servers.json`, который
  правит владелец сайта. Посетитель не может подставить чужой хост:
  страница статическая, формы ввода нет. Иначе сайт был бы
  сканером портов чужими руками.
* **Без привилегированных портов.** Порт ниже 1024 отклоняется:
  проверять `22` или `3306` игровому сайту незачем, а вот выглядеть это
  будет ровно как разведка.
* **С таймаутом и потолком.** Три секунды на адрес, не больше двадцати
  адресов за запуск, не чаще раза в минуту.
* **Наружу — только то, что владелец и так опубликовал.** Имя, адрес,
  порт, «отвечает или нет» и задержка. Ни игроков, ни версий, ни того,
  что сервер о себе рассказал бы в сессии.

Соединение отвечает на вопрос «порт открыт», а не «там именно
Primitive» — и страница говорит ровно это.

    python tools/ping.py             # проверить и обновить server.html
    python tools/ping.py --dry-run   # только показать, ничего не писать
"""

import io
import json
import os
import re
import socket
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "tools", "servers.json")
STATUS = os.path.join(ROOT, "tools", "status.json")
PAGE = os.path.join(ROOT, "server.html")

MAX_SERVERS = 20
MIN_PORT = 1024
MAX_TIMEOUT = 10.0

START = "<!-- ping:start -->"
END = "<!-- ping:end -->"

# Имя хоста или IPv4-литерал. Всё остальное отклоняется до резолвинга:
# в список серверов не должны попадать ни схемы, ни пути, ни пробелы.
RE_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


def escape(text):
    """HTML-экранирование: в страницу попадает текст, а не разметка."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def validate(entry):
    """Проверить запись списка. Возвращает причину отказа или None."""
    host = entry.get("host", "")
    port = entry.get("port")
    if not isinstance(host, str) or not RE_HOST.match(host):
        return "недопустимый хост"
    if not isinstance(port, int) or not (MIN_PORT <= port <= 65535):
        return "порт вне диапазона %d-65535" % MIN_PORT
    return None


def probe(host, port, timeout):
    """Открыть соединение и сразу закрыть. Ничего не отправляя.

    Возвращает (доступен, задержка в мс или None, причина или None).
    """
    started = time.monotonic()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except socket.timeout:
        return False, None, "нет ответа"
    except socket.gaierror:
        return False, None, "имя не разрешается"
    except ConnectionRefusedError:
        return False, None, "соединение отклонено"
    except OSError as exc:
        return False, None, exc.strerror or "недоступен"
    latency = (time.monotonic() - started) * 1000.0
    try:
        # Закрыть, не сказав ни байта: слот игрока не занимаем.
        sock.close()
    except OSError:
        pass
    return True, round(latency, 1), None


def rate_limited(min_interval):
    """Не чаще, чем разрешено: защита и от себя, и от чужого сервера."""
    if not os.path.exists(STATUS):
        return False
    try:
        previous = json.load(io.open(STATUS, encoding="utf-8"))
        last = float(previous.get("checked_unix", 0))
    except (ValueError, OSError):
        return False
    waited = time.time() - last
    if waited < min_interval:
        print("проверка была %d с назад, минимум %d с — пропуск"
              % (waited, min_interval))
        return True
    return False


def render(results, checked_iso):
    """Готовый кусок HTML — тот же, что и в остальной вёрстке сайта."""
    rows = []
    for r in results:
        if r["ok"]:
            state = '<strong>отвечает</strong>'
            detail = "%s мс" % r["latency_ms"]
        else:
            state = "не отвечает"
            detail = escape(r["reason"] or "—")
        rows.append(
            "    <tr><td>%s</td><td><code>%s:%d</code></td><td>%s</td><td>%s</td></tr>"
            % (escape(r["name"]), escape(r["host"]), r["port"], state, detail)
        )
    if not rows:
        rows.append('    <tr><td colspan="4">Список серверов пуст.</td></tr>')

    return "\n".join(
        [
            START,
            '  <div class="tablewrap">',
            "  <table>",
            "    <tr><th>Сервер</th><th>Адрес</th><th>Состояние</th><th>Задержка</th></tr>",
        ]
        + rows
        + [
            "  </table>",
            "  </div>",
            '  <p class="dim">Проверено %s. Проверка выполняется на стороне сайта, '
            "а не в вашем браузере: открывается TCP-соединение и сразу закрывается. "
            "Открытый порт означает, что машина отвечает, — но не то, что за ним "
            "именно Primitive нужной версии.</p>" % escape(checked_iso),
            END,
        ]
    )


def main():
    dry_run = "--dry-run" in sys.argv

    config = json.load(io.open(CONFIG, encoding="utf-8"))
    timeout = min(float(config.get("timeout_seconds", 3)), MAX_TIMEOUT)
    min_interval = int(config.get("min_interval_seconds", 60))
    servers = config.get("servers", [])[:MAX_SERVERS]

    if not dry_run and rate_limited(min_interval):
        return 0

    results = []
    for entry in servers:
        refusal = validate(entry)
        if refusal:
            print("пропуск %r: %s" % (entry.get("host"), refusal))
            results.append({
                "name": entry.get("name", "?"), "host": str(entry.get("host", "?"))[:64],
                "port": entry.get("port", 0) if isinstance(entry.get("port"), int) else 0,
                "ok": False, "latency_ms": None, "reason": refusal,
            })
            continue
        ok, latency, reason = probe(entry["host"], entry["port"], timeout)
        print("%-14s %s:%-5d %s%s" % (
            entry.get("name", "?"), entry["host"], entry["port"],
            "отвечает" if ok else "не отвечает",
            (" %s мс" % latency) if ok else (" (%s)" % reason),
        ))
        results.append({
            "name": entry.get("name", "?"), "host": entry["host"],
            "port": entry["port"], "ok": ok, "latency_ms": latency, "reason": reason,
        })

    now = time.time()
    checked_iso = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if dry_run:
        print("--dry-run: файлы не тронуты")
        return 0

    io.open(STATUS, "w", encoding="utf-8").write(json.dumps(
        {"checked_unix": now, "checked": checked_iso, "servers": results},
        ensure_ascii=False, indent=2,
    ) + "\n")

    page = io.open(PAGE, encoding="utf-8").read()
    if START not in page or END not in page:
        print("в %s нет меток ping:start / ping:end — страница не тронута"
              % os.path.basename(PAGE))
        return 1
    block = render(results, checked_iso)
    page = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block,
                  page, flags=re.S)
    io.open(PAGE, "w", encoding="utf-8").write(page)
    print("обновлено server.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
