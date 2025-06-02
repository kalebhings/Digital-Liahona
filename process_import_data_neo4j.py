from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List
import json, re, unicodedata
import time

import ollama
from neo4j import GraphDatabase, Driver

# ───────────────────────── connection ─────────────────────────
NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD = "bolt://localhost:7687", "neo4j", "password"
OLLAMA_MODEL = "nomic-embed-text"

DATA_ROOT = Path("data")
SCRIPTURE_VOLUMES = {
    "bookofmormon": "Book of Mormon",
    "newtestament": "New Testament",
    "oldtestament": "Old Testament",
    "doctrineandcovenants": "Doctrine & Covenants",
    "pearlofgreatprice": "Pearl of Great Price",
}
CONFERENCE_FILE         = DATA_ROOT / "conference_talks.json"
TOPIC_TALK_MAPPING_FILE = DATA_ROOT / "topic_talk_mappings.json"
TOPICAL_GUIDE_FILE      = DATA_ROOT / "topical_guide.json"
BIBLE_DICT_FILE         = DATA_ROOT / "bible_dictionary.json"

# ──────────────────────── schema helpers ──────────────────────
CONSTRAINTS = [
    ("volume_id",    "Volume",    "id"),
    ("book_id",      "Book",      "id"),
    ("chapter_id",   "Chapter",   "id"),
    ("verse_id",     "Verse",     "id"),
    ("talk_id",      "Talk",      "id"),
    ("paragraph_id", "Paragraph", "id"),
    ("source_id",    "Source",    "id"),
]
CYPHER_CONSTRAINTS = [
    f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
    for name, label, prop in CONSTRAINTS
] + [
    "CREATE CONSTRAINT speaker_name IF NOT EXISTS FOR (s:Speaker) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT topic_name   IF NOT EXISTS FOR (t:Topic)   REQUIRE t.name IS UNIQUE",
]
INDEXES = [
    ("verse_embedding",    "Verse",      "embedding",   "vector"),
    ("paragraph_embedding","Paragraph",  "embedding",   "vector"),
    ("verse_ref",          "Verse",      "reference",  "property"),
]
CYPHER_INDEXES = [
    f"CREATE VECTOR INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{prop}) OPTIONS {{indexConfig:{{`vector.dimensions`:768,`vector.similarity_function`:'cosine'}}}}"
    if kind == "vector" else f"CREATE INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"
    for name, label, prop, kind in INDEXES
]

# ────────────────────────── utils ────────────────────────────
class Cleaner:
    _COMB = re.compile(r"[\u0300-\u036f]")
    _WS   = re.compile(r"\s+")
    def __call__(self, obj):  # noqa: ANN401
        if isinstance(obj, dict):   return {k: self(v) for k, v in obj.items()}
        if isinstance(obj, list):   return [self(v) for v in obj]
        if isinstance(obj, str):
            s = unicodedata.normalize("NFKD", obj.replace("\\/", "/"))
            s = self._COMB.sub("", s).replace("\u00a0", " ")
            return self._WS.sub(" ", s).strip()
        return obj

def slugify(txt: str, max_len: int = 110) -> str:
    txt = unicodedata.normalize("NFKD", txt)
    txt = re.sub(r"[\u0300-\u036f]", "", txt).lower()
    txt = re.sub(r"[^\w\s-]", "", txt)
    txt = re.sub(r"[\s_-]+", "-", txt).strip("-")
    return txt[:max_len]

def unique_talk_id(title: str, season: str | None, year: int | str | None) -> str:
    # Ensure we have string values for concatenation
    title = str(title) if title else "untitled"
    season = str(season) if season else "na"
    year = str(year) if year else "na"
    
    # Clean up empty or None values
    if season.lower() in ("", "none", "null", "na", "n/a"):
        season = "na"
    if year.lower() in ("", "none", "null", "na", "n/a", "0"):
        year = "na"
        
    return slugify(f"{title}-{season}-{year}")

def embed(text: str) -> List[float]:
    try:
        return ollama.embeddings(model=OLLAMA_MODEL, prompt=text)["embedding"]
    except Exception:
        return []

def build_ref(book: str, chap: int | str, verse: int | str) -> str:
    return f"{book} {chap}:{verse}"

# ─────────────────────── Neo4j importer ─────────────────────
class Neo4jImporter:
    def __init__(self, uri: str, user: str, pwd: str):
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, pwd))

    # —— minimal wrappers ——
    def _run(self, cypher: str, **params):
        with self.driver.session() as s:
            def run_tx(tx):
                result = tx.run(cypher, **params)
                if "deleted" in cypher.lower():
                    records = list(result)
                    return records[0]["deleted"] if records else 0
                return result
            return s.execute_write(run_tx)

    def _batch(self, stmts: Iterable[tuple[str, dict]]):
        with self.driver.session() as s:
            def fn(tx):
                for c, p in stmts:
                    tx.run(c, **p)
            s.execute_write(fn)

    # —— schema / reset ——
    def init_schema(self):
        for c in CYPHER_CONSTRAINTS + CYPHER_INDEXES:
            self._run(c)

    def reset_database(self):
        for name, *_ in CONSTRAINTS: self._run(f"DROP CONSTRAINT {name} IF EXISTS")
        for name, *_ in INDEXES:     self._run(f"DROP INDEX {name} IF EXISTS")
        # Delete in batches to avoid memory issues
        while True:
            result = self._run("""
                MATCH (n) 
                WITH n LIMIT 10000
                DETACH DELETE n
                RETURN count(n) as deleted
            """)
            if result == 0:
                break
        print("graph wiped; import again when ready")

    # ───────── scriptures  ─────────
    def import_volume(self, vol_dir: Path, meta: dict):
        vid, title = meta["_id"], meta["title"]
        self._run(
            """MERGE (v:Volume {id:$vid}) SET v.title=$t, v.titleShort=$ts, v.titleOfficial=$to
                MERGE (s:Source {id:$sid}) SET s.kind='Volume', s.name=$t
                MERGE (s)-[:SOURCE_OF]->(v)""",
            vid=vid, t=title, ts=meta.get("titleShort"), to=meta.get("titleOfficial"), sid=f"src-{vid}",
        )
        cl = Cleaner()
        for b in meta["books"]:
            st = time.time()
            self._import_book(vol_dir, vid, cl(b))
            print(f"Book {b['_id']} imported in {time.time() - st:.2f} seconds")

    def _import_book(self, vol_dir: Path, vid: str, bmeta: dict):
        bid, btitle = bmeta["_id"], bmeta["title"]
        path = vol_dir / bid
        if not path.is_dir():
            print("⚠ missing book", path); return
        self._run("MERGE (b:Book {id:$bid}) SET b.title=$t WITH b MATCH (v:Volume {id:$vid}) MERGE (v)-[:CONTAINS]->(b)", bid=bid, t=btitle, vid=vid)
        cl = Cleaner()
        for jf in sorted(path.glob(f"{bid}_*.json")):
            st_chapter = time.time()
            data = cl(json.load(jf.open()))
            chap = data["chapter"]; cid = data["_id"]
            cnum = int(chap["number"])
            verses = chap["verses"]
            for i,v in enumerate(verses,1): v.setdefault("verse", i)
            self._run("MERGE (c:Chapter {id:$cid}) SET c.number=$n, c.summary=$s WITH c MATCH (b:Book {id:$bid}) MERGE (b)-[:CONTAINS]->(c)", cid=cid, n=cnum, s=chap.get("summary"), bid=bid)
            stmts=[]
            for v in verses:
                vnum,text=v["verse"],v["text"]
                vid=f"{cid}_{vnum}"; ref=build_ref(btitle,cnum,vnum)
                stmts.append(("MERGE (v:Verse {id:$id}) SET v.text=$tx, v.number=$n, v.reference=$ref, v.embedding=$emb WITH v MATCH (c:Chapter {id:$cid}) MERGE (c)-[:CONTAINS]->(v)",
                              dict(id=vid,tx=text,n=vnum,ref=ref,emb=embed(text),cid=cid)))
            self._batch(stmts)
            print(f"Chapter {cid} imported in {time.time() - st_chapter:.2f} seconds")
    # ───────── talks & paragraphs ─────────
    def import_conference_talks(self, p: Path):
        cl=Cleaner(); talks=cl(json.load(p.open()))
        seen_ids = set()
        for t in talks:
            st = time.time()
            title, season, year = t["title"], t.get("season"), t.get("year")
            tid = unique_talk_id(title, season, year)
            
            if tid in seen_ids:
                print(f"⚠ Duplicate talk ID found: {tid}")
                print(f"  Title: {title}")
                print(f"  Season: {season}")
                print(f"  Year: {year}")
                # Append a unique suffix to make the ID unique
                counter = 1
                while f"{tid}-{counter}" in seen_ids:
                    counter += 1
                tid = f"{tid}-{counter}"
                print(f"  New ID: {tid}")
            
            seen_ids.add(tid)
            
            try:
                self._run("""MERGE (t:Talk {id:$id}) SET t.title=$title, t.year=$y, t.season=$s, t.url=$u
                            MERGE (src:Source {id:$sid}) SET src.kind='Talk', src.name=$title MERGE (src)-[:SOURCE_OF]->(t)""",
                          id=tid,title=title,y=int(year if year else 0),s=season,u=t.get("url"),sid=f"src-{tid}")
                
                if sp:=t.get("speaker"):
                    self._run("MERGE (sp:Speaker {name:$n}) WITH sp MATCH (t:Talk {id:$id}) MERGE (sp)-[:GAVE]->(t)", n=sp, id=tid)
                
                stmts=[]
                for para in t.get("content", []):
                    num,text=para["paragraph_number"], para["paragraph"]
                    pid=f"{tid}_{num}"
                    stmts.append(("MERGE (p:Paragraph {id:$id}) SET p.text=$tx, p.number=$n, p.embedding=$emb WITH p MATCH (t:Talk {id:$tid}) MERGE (t)-[:CONTAINS]->(p)",
                                  dict(id=pid,tx=text,n=num,emb=embed(text),tid=tid)))
                self._batch(stmts)
                print(f"Talk {tid} imported in {time.time() - st:.2f} seconds")
            except Exception as e:
                print(f"Error importing talk {tid}: {str(e)}")
                continue

    # ───────── topics & mappings ─────────
    def _merge_topic(self,name:str,**extra): self._run("MERGE (tp:Topic {name:$n}) SET tp += $e", n=name, e=extra)
    def _link_tv(self,tp,strref): self._run("MATCH (tp:Topic {name:$t}) MATCH (v:Verse {reference:$r}) MERGE (tp)-[:MENTIONS]->(v)", t=tp, r=strref)

    def import_topic_talk_mapping(self,p:Path):
        cl=Cleaner(); maps=cl(json.load(p.open()))
        for m in maps:
            tp=m["topic"]; self._merge_topic(tp, url=m.get("topic_url"))
            for info in m["talks"]:
                tid=unique_talk_id(info["title"], info.get("season"), info.get("year"))
                self._run("MERGE (t:Talk {id:$id}) SET t.title=$title, t.year=$y, t.season=$s, t.url=$u WITH t MERGE (tp:Topic {name:$tp}) MERGE (tp)-[:MENTIONS]->(t)",
                          id=tid,title=info["title"],y=int(info.get("year",0)),s=info.get("season"),u=info.get("url"),tp=tp)

    def import_topical_guide(self,p:Path):
        cl=Cleaner(); entries=cl(json.load(p.open()))
        for e in entries:
            tp=e["entry"]; self._merge_topic(tp, tg_url=e.get("entry_url"))
            refs=[sr for pg in e.get("paragraphs",[]) for sr in pg.get("scripture_references",[])]
            for r in refs: self._link_tv(tp,r)

    def import_bible_dictionary(self,p:Path):
        cl=Cleaner(); entries=cl(json.load(p.open()))
        for e in entries:
            tp=e["entry"]; self._merge_topic(tp, bd_url=e.get("entry_url"))
            sid=f"src-bd-{slugify(tp)}"
            self._run("MERGE (s:Source {id:$sid}) SET s.kind='BDEntry', s.name=$n WITH s MERGE (tp:Topic {name:$n}) MERGE (s)-[:SOURCE_OF]->(tp)", sid=sid, n=tp)
            refs=[sr for pg in e.get("paragraphs",[]) for sr in pg.get("scripture_references",[])]
            for r in refs: self._link_tv(tp,r)

    def close(self):
        self.driver.close()

# ───────────────────────── batch orchestration ─────────────────────────

def import_all(imp: Neo4jImporter):
    cl=Cleaner()
    for k in SCRIPTURE_VOLUMES:
        meta=DATA_ROOT / k / f"{k}_data.json"
        if not meta.exists(): print("⚠",meta,"missing"); continue
        imp.import_volume(DATA_ROOT/k, cl(json.load(meta.open())))
    if CONFERENCE_FILE.exists():         imp.import_conference_talks(CONFERENCE_FILE)
    if TOPIC_TALK_MAPPING_FILE.exists(): imp.import_topic_talk_mapping(TOPIC_TALK_MAPPING_FILE)
    if TOPICAL_GUIDE_FILE.exists():      imp.import_topical_guide(TOPICAL_GUIDE_FILE)
    if BIBLE_DICT_FILE.exists():         imp.import_bible_dictionary(BIBLE_DICT_FILE)

# ───────────────────────── CLI entry ─────────────────────────
if __name__=="__main__":
    imp=Neo4jImporter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    imp.reset_database()
    imp.init_schema()
    import_all(imp)
    imp.close(); print("import done")
