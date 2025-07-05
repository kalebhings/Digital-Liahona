# Digital-Liahona

A **mobile scripture study companion** that surfaces spiritually relevant passages using a Neo4j knowledge graph, semantic embeddings, and a lightweight LLM backend.

---

## Table of contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Acknowledgements](#acknowledgments)

---

## Features

|  Category                |  Highlights                                                                                       |
| ------------------------ | ------------------------------------------------------------------------------------------------- |
| **Natural‑language Q&A** | Ask "*How do I find peace?*" and receive scripture verses *and* General Conference insights.      |
| **Hybrid retrieval**     | Vector similarity + topic + keyword search for high recall, then LLM re‑ranking for precision.    |
| **Knowledge graph**      | Verses, talks, topics, speakers, cross‑references stored as first‑class nodes in **Neo4j**.       |
| **Local‑first ML**       | Embeddings via `nomic‑embed‑text`; answer ranking with `llama3.2` (runs in **Ollama**).           |
| **React Native app**     | Cross‑platform chat UI; tap a verse to open the full chapter; dark‑mode & bookmarking on roadmap. |


---

## Architecture

```
┌────────────┐   POST /chat        ┌───────────────┐
│ React Native│ ───────────────▶ │  Flask API    │
│   (iOS/Android) │◀───────────────│  (Python 3.12.3) │
└────────────┘   JSON reply       │  ├─ Vector search in Neo4j
                                   │  ├─ Topic/keyword match
                                   │  └─ LLM re‑rank (Ollama)
                                   └───────────────┘
                                            │
                                  ┌─────────────────┐
                                  │  Neo4j 5 graph  │
                                  │ Verse ↔ Topic ↔ Talk │
                                  └─────────────────┘
```

Backend endpoints (excerpt):

- **POST** – main Q&A route
- **GET** – read‑only chapter view
- **GET** – verses & talks for a gospel topic
- **GET** – full talk transcript

Data is populated via `process_import_data_neo4j.py`, which:

1. Cleans scripture & talk JSON
2. Creates graph schema + vector indexes
3. Embeds verses & paragraphs

---


## API Reference

### POST `/chat`

```jsonc
// Request
{ "message": "How does Christ teach forgiveness?" }
// Response (truncated)
{
  "reply": "Here are some things that might help:\n...",
  "verses_with_links": [
    {
      "text": "...",
      "source": "Matthew 18:21",
      "chapter_info": {
        "chapter_url": "/chapter/matthew/18"
      }
    }
  ],
  "related_content": { ... }
}
```

Refer to `flask_server.py` for additional endpoints.

---

## Acknowledgments

- [Open Scriptures API](https://openscriptureapi.org/) for scripture data
- The Church of Jesus Christ of Latter‑day Saints (General Conference transcripts)
- Neo4j & Ollama communities for open tooling
