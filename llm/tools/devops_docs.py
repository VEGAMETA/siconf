"""
title: Офлайн-документация DevOps
description: Поиск и чтение официальной документации без интернета: Kubernetes, Prometheus, Helm (из репозиториев проектов), справочники DevDocs (Docker, Terraform, Ansible, nginx, PostgreSQL, Python, Bash, Git, Go, kubectl, Vagrant, jq, HTTP, Redis, RabbitMQ, SQLite) и ArchWiki. База D:\\llm\\docs\\docs.db собирается скриптом D:\\llm\\docs\\build_docs.py.
author: local
version: 0.1.0
"""

import os
import re
import sqlite3

DB = r"D:\llm\docs\docs.db"
RESULTS = 8
PAGE_CHARS = 9000


def _connect():
    if not os.path.exists(DB):
        raise FileNotFoundError(f"no docs database {DB}; run D:\\llm\\docs\\build_docs.py")
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _fts_query(text, joiner):
    words = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*", text or "")
    return f" {joiner} ".join(f'"{w}"' for w in words[:12])


class Tools:
    def search_docs(self, query: str, source: str = "") -> str:
        """
        Search official technical documentation offline (works without internet). Use it for exact syntax, flags, config keys, API fields and how-to steps instead of answering from memory.
        Sources: kubernetes, prometheus, helm (full official docs), and references docker, terraform, ansible, nginx, postgresql, python, bash, git, go, kubectl, vagrant, jq, http, redis, rabbitmq, sqlite, archwiki (Linux).
        :param query: English keywords, e.g. "ingress tls secret", "pod readiness probe", "terraform for_each", "systemd timer".
        :param source: Optional source name from the list to search only there.
        :return: Numbered results with source, title, id and a snippet; read a page with read_doc(id).
        """
        try:
            con = _connect()
        except FileNotFoundError as e:
            return str(e)
        source = (source or "").strip().lower()
        sql = ("select rowid, source, title, path, snippet(docs, 3, '«', '»', ' … ', 24) from docs where docs match ?"
               + (" and source = ?" if source else "") + " order by bm25(docs, 0.0, 6.0, 1.0, 1.0) limit ?")
        rows = []
        try:
            for joiner in ("AND", "OR"):  # сначала все слова сразу, если пусто — любое из них
                q = _fts_query(query, joiner)
                if not q:
                    return "Pass English keywords."
                rows = con.execute(sql, (q, source, RESULTS) if source else (q, RESULTS)).fetchall()
                if rows:
                    break
            sources = [r[0] for r in con.execute("select distinct source from docs")] if not rows else []
        finally:
            con.close()
        if not rows:
            return f'Nothing found for "{query}"' + (f' in "{source}"' if source else "") + f". Sources: {', '.join(sorted(sources))}."
        lines = [f'Offline docs: "{query}"' + (f" in {source}" if source else ""), ""]
        for n, (rowid, src, title, path, snip) in enumerate(rows, 1):
            lines.append(f"[{n}] id={rowid} | {src} | {title} | {path}")
            lines.append("    " + re.sub(r"\s+", " ", snip))
        lines.append("\nOpen the most relevant pages with read_doc(id) before answering; cite the source and title.")
        return "\n".join(lines)

    def read_doc(self, doc_id: int, offset: int = 0) -> str:
        """
        Read a documentation page found with search_docs.
        :param doc_id: The id from search_docs results.
        :param offset: Character offset for long pages (the result says the next offset).
        :return: Page text with its source, title and path.
        """
        try:
            con = _connect()
        except FileNotFoundError as e:
            return str(e)
        try:
            row = con.execute("select source, title, path, body from docs where rowid = ?", (int(doc_id),)).fetchone()
        finally:
            con.close()
        if not row:
            return f"No page with id {doc_id}."
        src, title, path, body = row
        offset = max(0, int(offset or 0))
        part = body[offset:offset + PAGE_CHARS]
        tail = f"\n\n[… page continues: read_doc({doc_id}, offset={offset + PAGE_CHARS})]" if len(body) > offset + PAGE_CHARS else ""
        return f"{src} | {title} | {path}\n\n{part}{tail}"
