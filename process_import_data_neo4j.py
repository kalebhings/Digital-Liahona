"""Neo4j bulk importer for
- Standard Works (JSON export from Digital‑Liahona project)
- General‑Conference talks + topic mappings
- Topical Guide + Bible Dictionary

Highlights
==========
* **Uniform leaf nodes** – scripture `Verse` and conference‐talk `Paragraph` nodes
  share identical properties (`text`, `number`, `embedding`, `reference`).
* **Semantic ready** – every leaf node stores a 768‑d cosine embedding (Ollama
  **nomic‑embed‑text**) with 2 vector indexes.
* **Single topic graph** – topics coming from *topic_talk_mappings.json*,
  *topical_guide.json*, and the Bible Dictionary are all consolidated to
  `(:Topic)` and connected via `[:MENTIONS]` to either talks, paragraphs or
  verses.
* **Source abstraction** – every top‑level document (scripture volume | GC talk
  | BD entry) gets a `(:Source)` wrapper to enable uniform traversals.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List
import json
import re
import unicodedata

import ollama                      # local inference server
from neo4j import GraphDatabase, Driver

###############################################################################
# connection & directory constants – edit to suit your box
###############################################################################
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "password"

OLLAMA_MODEL   = "nomic-embed-text"   # 768‑d cosine space

DATA_ROOT              = Path("data")   # Digital‑Liahona JSON dump + extras
SCRIPTURE_VOLUMES      = {
    "bookofmormon":        "Book of Mormon",
    "newtestament":       "New Testament",
    "oldtestament":       "Old Testament",
    "doctrineandcovenants":"Doctrine & Covenants",
    "pearlofgreatprice":  "Pearl of Great Price",
}
CONFERENCE_FILE         = DATA_ROOT / "conference_talks.json"
TOPIC_TALK_MAPPING_FILE = DATA_ROOT / "topic_talk_mappings.json"
TOPICAL_GUIDE_FILE      = DATA_ROOT / "topical_guide.json"
BIBLE_DICT_FILE         = DATA_ROOT / "bible_dictionary.json"

###############################################################################
# schema  (constraints + indexes)
###############################################################################
CYPHER_CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT volume_id    IF NOT EXISTS FOR (v:Volume)    REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT book_id      IF NOT EXISTS FOR (b:Book)      REQUIRE b.id IS UNIQUE",
    "CREATE CONSTRAINT chapter_id   IF NOT EXISTS FOR (c:Chapter)   REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT verse_id     IF NOT EXISTS FOR (v:Verse)     REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT talk_id      IF NOT EXISTS FOR (t:Talk)      REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT paragraph_id IF NOT EXISTS FOR (p:Paragraph) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT source_id    IF NOT EXISTS FOR (s:Source)    REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT speaker_name IF NOT EXISTS FOR (s:Speaker)   REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT topic_name   IF NOT EXISTS FOR (t:Topic)     REQUIRE t.name IS UNIQUE",
]

CYPHER_INDEXES: list[str] = [
    # vector indexes
    """
    CREATE VECTOR INDEX verse_embedding IF NOT EXISTS
    FOR (v:Verse) ON (v.embedding)
    OPTIONS {indexConfig:{`vector.dimensions`:768,`vector.similarity_function`:'cosine'}}
    """,
    """
    CREATE VECTOR INDEX paragraph_embedding IF NOT EXISTS
    FOR (p:Paragraph) ON (p.embedding)
    OPTIONS {indexConfig:{`vector.dimensions`:768,`vector.similarity_function`:'cosine'}}
    """,
    # fast lookup by reference string
    "CREATE INDEX verse_ref IF NOT EXISTS FOR (v:Verse) ON (v.reference)",
]

###############################################################################
# tiny helpers
###############################################################################
class Cleaner:
    _COMBINING = re.compile(r"[\u0300-\u036f]")
    _WS        = re.compile(r"\s+")

    def _clean(self, s: str) -> str:
        s = s.replace("\\/", "/")
        s = unicodedata.normalize("NFKD", s)
        s = self._COMBINING.sub("", s)
        s = s.replace("\u00a0", " ")
        s = self._WS.sub(" ", s).strip()
        return s

    def __call__(self, obj: Any) -> Any:  # noqa: ANN401
        if isinstance(obj, dict):
            return {k: self(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self(v) for v in obj]
        if isinstance(obj, str):
            return self._clean(obj)
        return obj


def slugify(text: str, max_len: int = 110) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:max_len]


def build_reference(book: str, chap: int | str, verse: int | str) -> str:
    return f"{book} {chap}:{verse}"


def embedding(text: str) -> list[float]:
    try:
        return ollama.embeddings(model=OLLAMA_MODEL, prompt=text)["embedding"]
    except Exception as exc:  # noqa: BLE001
        print(f"⚠ embedding failed – {exc}\n → {text[:80]}…")
        return []

###############################################################################
# Neo4j wrapper
###############################################################################
class Neo4jImporter:
    def __init__(self, uri: str, user: str, pwd: str):
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, pwd))

    # —— helpers ——
    def _run(self, cypher: str, **params):
        with self.driver.session() as s:
            s.write_transaction(lambda tx: tx.run(cypher, **params))

    def _batch(self, statements: Iterable[tuple[str, dict]]):
        with self.driver.session() as s:
            def tx_fn(tx):
                for c, p in statements:
                    tx.run(c, **p)
            s.write_transaction(tx_fn)

    # —— schema ——
    def init_schema(self):
        for stmt in CYPHER_CONSTRAINTS + CYPHER_INDEXES:
            self._run(stmt)

    ############################################################################
    # scriptures (Volumes → Books → Chapters → Verses)
    ############################################################################
    def import_volume(self, vol_dir: Path, meta: dict):
        vol_id, title = meta["_id"], meta["title"]
        self._run(
            """
            MERGE (v:Volume {id:$id})
            SET v.title=$title, v.titleShort=$short, v.titleOfficial=$official
            MERGE (s:Source {id:$sid}) SET s.kind='Volume', s.name=$title
            MERGE (s)-[:SOURCE_OF]->(v)
            """,
            id=vol_id, title=title, short=meta.get("titleShort"),
            official=meta.get("titleOfficial"), sid=f"src-{vol_id}",
        )
        cln = Cleaner()
        for book_meta in meta["books"]:
            self._import_book(vol_dir, vol_id, cln(book_meta))

    def _import_book(self, vol_dir: Path, vol_id: str, book_meta: dict):
        book_id, book_title = book_meta["_id"], book_meta["title"]
        book_path = vol_dir / book_id
        if not book_path.is_dir():
            print(f"⚠ {book_path} missing – skip book")
            return
        # Book node & containment
        self._run(
            """
            MERGE (b:Book {id:$bid}) SET b.title=$title
            WITH b MATCH (v:Volume {id:$vid}) MERGE (v)-[:CONTAINS]->(b)
            """,
            bid=book_id, title=book_title, vid=vol_id,
        )
        cln = Cleaner()
        for ch_file in sorted(book_path.glob(f"{book_id}_*.json")):
            root = cln(json.load(ch_file.open("r", encoding="utf-8")))
            chapter = root["chapter"]
            chap_id  = root["_id"]
            chap_num = int(chapter["number"])
            verses   = chapter["verses"]
            # ensure verse numbers present
            for i, v in enumerate(verses, 1):
                v.setdefault("verse", i)
            # Chapter node
            self._run(
                """
                MERGE (c:Chapter {id:$cid}) SET c.number=$num, c.summary=$summary
                WITH c MATCH (b:Book {id:$bid}) MERGE (b)-[:CONTAINS]->(c)
                """,
                cid=chap_id, num=chap_num, summary=chapter.get("summary"), bid=book_id,
            )
            # Verses (batch)
            stmts: list[tuple[str, dict]] = []
            for v in verses:
                vnum, text = v["verse"], v["text"]
                vid  = f"{chap_id}_{vnum}"
                ref  = build_reference(book_title, chap_num, vnum)
                stmts.append((
                    """
                    MERGE (v:Verse {id:$id})
                    SET v.text=$text, v.number=$num, v.reference=$ref, v.embedding=$emb
                    WITH v MATCH (c:Chapter {id:$cid}) MERGE (c)-[:CONTAINS]->(v)
                    """,
                    dict(id=vid, text=text, num=vnum, ref=ref, emb=embedding(text), cid=chap_id),
                ))
            self._batch(stmts)

    ############################################################################
    # general conference talks + speakers + paragraphs
    ############################################################################
    def import_conference_talks(self, talks_file: Path):
        cln = Cleaner()
        talks = cln(json.load(talks_file.open("r", encoding="utf-8")))
        for talk in talks:
            tid   = slugify(talk["title"])
            year  = int(talk.get("year", 0))
            season= talk.get("season")
            self._run(
                """
                MERGE (t:Talk {id:$id})
                SET t.title=$title, t.year=$year, t.season=$season, t.url=$url
                MERGE (s:Source {id:$sid}) SET s.kind='Talk', s.name=$title, s.year=$year
                MERGE (s)-[:SOURCE_OF]->(t)
                """,
                id=tid, title=talk["title"], year=year, season=season,
                url=talk.get("url"), sid=f"src-{tid}",
            )
            if spkr := talk.get("speaker"):
                self._run(
                    "MERGE (sp:Speaker {name:$n}) MERGE (sp)-[:GAVE]->(t:Talk {id:$tid})",
                    n=spkr, tid=tid,
                )
            # paragraphs
            stmts: list[tuple[str, dict]] = []
            for para in talk.get("content", []):
                num, text = para["paragraph_number"], para["paragraph"]
                pid = f"{tid}_{num}"
                stmts.append((
                    """
                    MERGE (p:Paragraph {id:$id})
                    SET p.text=$text, p.number=$num, p.embedding=$emb
                    WITH p MATCH (t:Talk {id:$tid}) MERGE (t)-[:CONTAINS]->(p)
                    """,
                    dict(id=pid, text=text, num=num, emb=embedding(text), tid=tid),
                ))
            self._batch(stmts)

    ############################################################################
    # Topic helpers (TG & mapping & BD)
    ############################################################################
    def _merge_topic(self, name: str, **extra):
        self._run("MERGE (tp:Topic {name:$n}) SET tp += $extra", n=name, extra=extra)

    def _link_topic_to_verse(self, topic: str, reference: str):
        self._run(
            """
            MATCH (tp:Topic {name:$topic})
            MATCH (v:Verse {reference:$ref})
            MERGE (tp)-[:MENTIONS]->(v)
            """,
            topic=topic, ref=reference,
        )

    ############################################################################
    # topic ↔ talk mapping  (topic_talk_mappings.json)
    ############################################################################
    def import_topic_talk_mapping(self, mapping_file: Path):
        cln = Cleaner(); mappings = cln(json.load(mapping_file.open("r", encoding="utf-8")))
        for m in mappings:
            tname = m["topic"]
            self._merge_topic(tname, url=m.get("topic_url"))
            for t in m["talks"]:
                tid = slugify(t["title"])
                self._run(
                    """
                    MERGE (t:Talk {id:$tid}) SET t.title=$title, t.year=$year, t.season=$season, t.url=$url
                    WITH t MERGE (tp:Topic {name:$topic}) MERGE (tp)-[:MENTIONS]->(t)
                    """,
                    tid=tid, title=t["title"], year=int(t.get("year",0)), season=t.get("season"),
                    url=t.get("url"), topic=tname,
                )

    ############################################################################
    # Topical Guide – links topics → verse
    ############################################################################
    def import_topical_guide(self, tg_file: Path):
        cln = Cleaner(); entries = cln(json.load(tg_file.open("r", encoding="utf-8")))
        for e in entries:
            name = e["entry"]
            self._merge_topic(name, tg_url=e.get("entry_url"))
            # gather verse refs appearing in paragraphs
            refs: list[str] = []
            for p in e.get("paragraphs", []):
                refs.extend(p.get("scripture_references", []))
            for r in refs:
                self._link_topic_to_verse(name, r)

    ############################################################################
    # Bible Dictionary – create BDEntry nodes & topic links + verse links
    ############################################################################
    def import_bible_dictionary(self, bd_file: Path):
        cln = Cleaner(); entries = cln(json.load(bd_file.open("r", encoding="utf-8")))
        for e in entries:
            name = e["entry"]
            self._merge_topic(name, bd_url=e.get("entry_url"))
            # Source node
            sid = f"src-bd-{slugify(name)}"
            self._run(
                """
                MERGE (src:Source {id:$sid}) SET src.kind='BDEntry', src.name=$name
                WITH src MERGE (tp:Topic {name:$name}) MERGE (src)-[:SOURCE_OF]->(tp)
                """,
                sid=sid, name=name,
            )
            refs: list[str] = []
            for p in e.get("paragraphs", []):
                refs.extend(p.get("scripture_references", []))
            for r in refs:
                self._link_topic_to_verse(name, r)

    # —— close ——
    def close(self):
        self.driver.close()

###############################################################################
# Orchestration helpers
###############################################################################

def import_all_scriptures(imp: Neo4jImporter):
    cln = Cleaner()
    for vol_key in SCRIPTURE_VOLUMES:
        vdir = DATA_ROOT / vol_key
        meta_file = vdir / f"{vol_key}_data.json"
        if not meta_file.exists():
            print(f"⚠️  missing {meta_file}")
            continue
        imp.import_volume(vdir, cln(json.load(meta_file.open("r", encoding="utf-8"))))

###############################################################################
# CLI
###############################################################################

def main():
    imp = Neo4jImporter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    imp.init_schema()

    import_all_scriptures(imp)

    if CONFERENCE_FILE.exists():     imp.import_conference_talks(CONFERENCE_FILE)
    if TOPIC_TALK_MAPPING_FILE.exists(): imp.import_topic_talk_mapping(TOPIC_TALK_MAPPING_FILE)
    if TOPICAL_GUIDE_FILE.exists():  imp.import_topical_guide(TOPICAL_GUIDE_FILE)
    if BIBLE_DICT_FILE.exists():     imp.import_bible_dictionary(BIBLE_DICT_FILE)

    imp.close(); print("✅  Import finished")


if __name__ == "__main__":
    main()
