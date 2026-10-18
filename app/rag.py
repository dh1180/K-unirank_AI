"""Operator-curated PDF retrieval with cited pages. No arbitrary URL fetching."""
import argparse
import hashlib
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    question: str = Field(min_length=2, max_length=300)
    university: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=2000, le=2100)
    limit: int = Field(default=5, ge=1, le=10)


class Passage(BaseModel):
    university: str
    year: int
    title: str
    page: int
    source_url: str
    text: str


class SearchResult(BaseModel):
    passages: list[Passage]
    retrieval: str = "sqlite-fts5"


def validated_url(url: str) -> str:
    info = urlparse(url)
    if info.scheme != "https" or not info.hostname or "." not in info.hostname:
        raise ValueError("검수된 HTTPS 원문 URL이 필요합니다.")
    if info.username or info.password:
        raise ValueError("URL에 계정정보를 포함할 수 없습니다.")
    return url


def chunks(text: str, maximum: int = 900, overlap: int = 120):
    normalized = re.sub(r"\s+", " ", text or "").strip()
    pos = 0
    while pos < len(normalized):
        stop = min(len(normalized), pos + maximum)
        if stop < len(normalized):
            space = normalized.rfind(" ", pos + maximum // 2, stop)
            if space > pos:
                stop = space
        yield normalized[pos:stop].strip()
        if stop >= len(normalized):
            return
        pos = max(pos + 1, stop - overlap)


class DocumentSearch:
    def __init__(self, database_path: str):
        self.path = Path(database_path)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("""
            CREATE TABLE IF NOT EXISTS passages (
              id INTEGER PRIMARY KEY,
              fingerprint TEXT NOT NULL,
              university TEXT NOT NULL,
              year INTEGER NOT NULL,
              title TEXT NOT NULL,
              page INTEGER NOT NULL,
              chunk_number INTEGER NOT NULL,
              source_url TEXT NOT NULL,
              text TEXT NOT NULL,
              UNIQUE(fingerprint, page, chunk_number)
            )
        """)
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5(text, tokenize='unicode61')")
        return db

    def ingest_pages(self, pages, *, university: str, year: int, title: str,
                     source_url: str, fingerprint: str) -> int:
        validated_url(source_url)
        if not (2000 <= year <= 2100) or not university.strip() or not title.strip():
            raise ValueError("유효한 대학·학년도·문서명을 입력하세요.")
        inserted = 0
        with self.connect() as db:
            for number, text in pages:
                for index, part in enumerate(chunks(text)):
                    cur = db.execute("""
                        INSERT OR IGNORE INTO passages
                          (fingerprint,university,year,title,page,chunk_number,source_url,text)
                        VALUES (?,?,?,?,?,?,?,?)
                    """, (fingerprint, university.strip(), year, title.strip(),
                          number, index, source_url, part))
                    if cur.rowcount:
                        db.execute("INSERT INTO doc_fts(rowid,text) VALUES (?,?)", (cur.lastrowid, part))
                        inserted += 1
        return inserted

    def ingest_pdf(self, filename: str, *, university: str, year: int,
                   title: str, source_url: str) -> int:
        from pypdf import PdfReader

        path = Path(filename)
        if not path.is_file() or path.suffix.lower() != ".pdf" or path.stat().st_size > 30 * 1024**2:
            raise ValueError("최대 30MB의 로컬 PDF 파일만 사용할 수 있습니다.")
        digest = hashlib.sha256(path.read_bytes() + f"{university}:{year}:{title}".encode()).hexdigest()
        reader = PdfReader(filename, strict=True)
        if reader.is_encrypted or len(reader.pages) > 500:
            raise ValueError("암호화 또는 500페이지 초과 PDF는 지원하지 않습니다.")
        pages = ((i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages))
        return self.ingest_pages(pages, university=university, year=year, title=title,
                                 source_url=source_url, fingerprint=digest)

    def search(self, request: SearchQuery) -> list[Passage]:
        if not self.path.exists():
            return []
        words = re.findall(r"[^\W_]+", request.question, flags=re.UNICODE)[:12]
        if not words:
            return []
        fts = " OR ".join('"' + word + '"' for word in words)
        with self.connect() as db:
            rows = db.execute("""
                SELECT p.* FROM doc_fts JOIN passages p ON doc_fts.rowid=p.id
                WHERE doc_fts MATCH ?
                  AND (? IS NULL OR p.university=?)
                  AND (? IS NULL OR p.year=?)
                ORDER BY bm25(doc_fts) LIMIT ?
            """, (fts, request.university, request.university, request.year, request.year,
                  request.limit)).fetchall()
        return [
            Passage(university=x["university"], year=x["year"], title=x["title"],
                    page=x["page"], source_url=x["source_url"] + "#page=" + str(x["page"]),
                    text=x["text"][:900])
            for x in rows
        ]


def main():
    parser = argparse.ArgumentParser(description="Operator-only official PDF indexing")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("ingest")
    add.add_argument("file")
    add.add_argument("--university", required=True)
    add.add_argument("--year", required=True, type=int)
    add.add_argument("--title", required=True)
    add.add_argument("--source-url", required=True)
    lookup = commands.add_parser("search")
    lookup.add_argument("question")
    lookup.add_argument("--university")
    lookup.add_argument("--year", type=int)
    args = parser.parse_args()
    from app.config import get_settings

    index = DocumentSearch(get_settings().rag_db_path)
    if args.command == "ingest":
        count = index.ingest_pdf(args.file, university=args.university, year=args.year,
                                 title=args.title, source_url=args.source_url)
        print(f"신규 색인 passage: {count}")
    else:
        for passage in index.search(SearchQuery(question=args.question,
                 university=args.university, year=args.year)):
            print(f"{passage.university} / {passage.year} / {passage.page}쪽\n"
                  f"{passage.source_url}\n{passage.text[:250]}\n")


if __name__ == "__main__":
    main()
