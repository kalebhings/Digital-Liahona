from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

import json
import re
import unicodedata

from neo4j import GraphDatabase, Driver

################################################################################
# connection & directory constants
################################################################################

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "password"

SCRIPTURE_ROOT = Path("data")                   # DIGITAL-LIAHONA/data

SCRIPTURE_VOLUMES = {
    "bookofmormon": "Book of Mormon",
    "newtestament": "New Testament",
    "oldtestament": "Old Testament",
    "doctrineandcovenants": "Doctrine & Covenants",
    "pearlofgreatprice": "Pearl of Great Price",
}

CONFERENCE_FILE        = SCRIPTURE_ROOT / "conference_talks.json"
CONFERENCE_TOPICS_FILE = SCRIPTURE_ROOT / "topic_talk_mapping.json"
TOPICAL_GUIDE_FILE     = SCRIPTURE_ROOT / "topical_guide.json"
BIBLE_DICT_FILE        = SCRIPTURE_ROOT / "bible_dictionary.json"

################################################################################
# schema (constraints / indexes)
################################################################################

CYPHER_CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT volume_id   IF NOT EXISTS FOR (v:Volume)  REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT book_id     IF NOT EXISTS FOR (b:Book)    REQUIRE b.id IS UNIQUE",
    "CREATE CONSTRAINT chapter_id  IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT verse_id    IF NOT EXISTS FOR (v:Verse)   REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT talk_id     IF NOT EXISTS FOR (t:Talk)    REQUIRE t.id IS UNIQUE",
    # add Speaker, Topic, etc. later
]

################################################################################
# helpers
################################################################################


class DataCleaner:
    """Normalise whitespace, remove combining marks, etc."""

    _COMBINING = re.compile(r"[\u0300-\u036f]")

    def _clean_string(self, s: str) -> str:
        s = s.replace("\\/", "/")  # fix double-escaped slashes
        s = unicodedata.normalize("NFKD", s)
        s = self._COMBINING.sub("", s)  # drop combining marks (e.g. \u0302)
        s = s.replace("\u00a0", " ").replace("\n", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def clean(self, obj: Any) -> Any:  # noqa: ANN401 – generic JSON value
        if isinstance(obj, dict):
            return {k: self.clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.clean(v) for v in obj]
        if isinstance(obj, str):
            return self._clean_string(obj)
        return obj


def add_verse_numbers(chapter_json: Dict[str, Any], key: str = "verses") -> Dict[str, Any]:
    """Ensure each verse dict has a field `verse` (1-based)."""
    verses = chapter_json.get(key)
    if not isinstance(verses, list):
        return chapter_json

    numbered: List[Dict[str, Any]] = []
    for i, v in enumerate(verses, 1):
        if isinstance(v, dict):
            v.setdefault("verse", i)
        else:
            v = {"text": v, "verse": i}
        numbered.append(v)
    chapter_json[key] = numbered
    return chapter_json


################################################################################
# Neo4j wrapper
################################################################################


class Neo4jImporter:
    """Thin convenience wrapper around neo4j.Driver."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    # --- low-level helpers ----------------------------------------------------

    def _write(self, cypher: str, **params):
        with self.driver.session() as s:
            s.write_transaction(lambda tx: tx.run(cypher, **params))

    def _batch(self, statements: Iterable[tuple[str, dict]]):
        with self.driver.session() as s:

            def _run(tx):
                for cypher, params in statements:
                    tx.run(cypher, **params)

            s.write_transaction(_run)

    # --- schema --------------------------------------------------------------

    def initialize_schema(self):
        for stmt in CYPHER_CONSTRAINTS:
            self._write(stmt)

    # --- scriptures ----------------------------------------------------------

    def import_scripture_volume(self, volume_dir: Path, volume_meta: dict):
        """Create Volume + its Books; then drill down to chapters / verses."""
        vol_id = volume_meta["_id"]

        # Volume node ---------------------------------------------------------
        self._write(
            """
            MERGE (v:Volume {id:$id})
            SET  v.title=$title,
                 v.titleShort=$titleShort,
                 v.titleOfficial=$titleOfficial
            """,
            id=vol_id,
            title=volume_meta["title"],
            titleShort=volume_meta.get("titleShort"),
            titleOfficial=volume_meta.get("titleOfficial"),
        )

        # Books ---------------------------------------------------------------
        for book_info in volume_meta["books"]:
            book_id = book_info["_id"]
            book_path = volume_dir / book_id                        # e.g. data/bookofmormon/1nephi
            if not book_path.is_dir():
                print(f"⚠  Folder {book_path} missing; skipping")
                continue

            self._write(
                """
                MERGE (b:Book {id:$id})
                ON CREATE SET b.title=$title
                WITH b
                MATCH (v:Volume {id:$vol_id})
                MERGE (v)-[:CONTAINS]->(b)
                """,
                id=book_id,
                title=book_info["title"],
                vol_id=vol_id,
            )

            self.import_chapters_for_book(book_id, book_path)

    def import_chapters_for_book(self, book_id: str, book_path: Path):
        """
        Create Chapter + Verse nodes for a given book folder.

        Handles nested JSON like:

            {
              "_id": "1nephi1",
              "book": {...},
              "chapter": { "number": 1, "verses":[ ... ] }
            }
        """
        cleaner = DataCleaner()

        for chapter_file in sorted(book_path.glob(f"{book_id}_*.json")):
            with chapter_file.open(encoding="utf-8") as f:
                root = cleaner.clean(json.load(f))

            chap_meta = root.get("chapter", {})
            chap_meta = add_verse_numbers(chap_meta)

            chap_id     = root["_id"]                    # e.g. '1nephi1'
            chap_num    = chap_meta.get("number")        # int
            chap_summary = chap_meta.get("summary", "")

            # Chapter node ---------------------------------------------------
            self._write(
                """
                MERGE (c:Chapter {id:$id})
                SET   c.number=$num,
                      c.summary=$summary
                WITH c
                MATCH (b:Book {id:$book})
                MERGE (b)-[:CONTAINS]->(c)
                """,
                id=chap_id,
                num=chap_num,
                summary=chap_summary,
                book=book_id,
            )

            # Verses ---------------------------------------------------------
            verse_statements: list[tuple[str, dict]] = []
            for verse in chap_meta["verses"]:
                v_id = f"{chap_id}_{verse['verse']}"
                verse_statements.append(
                    (
                        """
                        MERGE (v:Verse {id:$id})
                        SET   v.text=$text,
                              v.number=$num
                        WITH v
                        MATCH (c:Chapter {id:$chap})
                        MERGE (c)-[:CONTAINS]->(v)
                        """,
                        dict(
                            id=v_id,
                            text=verse["text"],
                            num=verse["verse"],
                            chap=chap_id,
                        ),
                    )
                )
            self._batch(verse_statements)

    # --- conference talks & reference works ----------------------------------

    def import_conference_talks(self, talks_file: Path):
        cleaner = DataCleaner()
        data = cleaner.clean(json.load(talks_file.open(encoding="utf-8")))

        for talk in data:
            stmts: list[tuple[str, dict]] = [
                (
                    """
                    MERGE (t:Talk {id:$id})
                    SET t.title=$title,
                        t.year=$year,
                        t.month=$month,
                        t.session=$session
                    """,
                    dict(
                        id=talk["_id"],
                        title=talk["title"],
                        year=talk["year"],
                        month=talk["month"],
                        session=talk.get("session"),
                    ),
                )
            ]

            if spkr := talk.get("speaker"):
                stmts.append(
                    (
                        """
                        MERGE (s:Speaker {name:$speaker})
                        MERGE (s)-[:GAVE]->(t:Talk {id:$id})
                        """,
                        dict(speaker=spkr, id=talk["_id"]),
                    )
                )

            self._batch(stmts)

    def import_topical_guide(self, guide_file: Path):
        """Stub - fill in later when you decide on a TG schema."""
        print(f"Topical guide import stub ({guide_file})")

    def import_bible_dictionary(self, dict_file: Path):
        """Stub - fill in later when you decide on a BD schema."""
        print(f"Bible dictionary import stub ({dict_file})")

    # --- convenience ---------------------------------------------------------

    def close(self):
        self.driver.close()


################################################################################
# orchestration
################################################################################


def import_all_scriptures(imp: Neo4jImporter):
    cleaner = DataCleaner()

    for vol_key, _vol_name in SCRIPTURE_VOLUMES.items():
        volume_dir = SCRIPTURE_ROOT / vol_key
        meta_file  = volume_dir / f"{vol_key}_data.json"

        if not meta_file.exists():
            print(f"⚠  metadata {meta_file} missing - skipping {vol_key}")
            continue

        with meta_file.open(encoding="utf-8") as f:
            meta = cleaner.clean(json.load(f))

        imp.import_scripture_volume(volume_dir, meta)


def main():
    imp = Neo4jImporter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    imp.initialize_schema()

    # scriptures --------------------------------------------------------------
    import_all_scriptures(imp)

    # general conference ------------------------------------------------------
    if CONFERENCE_FILE.exists():
        imp.import_conference_talks(CONFERENCE_FILE)
    else:
        print(f"⚠  {CONFERENCE_FILE} not found - skipping conference talks")

    # reference works ---------------------------------------------------------
    if TOPICAL_GUIDE_FILE.exists():
        imp.import_topical_guide(TOPICAL_GUIDE_FILE)
    if BIBLE_DICT_FILE.exists():
        imp.import_bible_dictionary(BIBLE_DICT_FILE)

    imp.close()
    print("📥  Import finished.")


if __name__ == "__main__":
    main()
