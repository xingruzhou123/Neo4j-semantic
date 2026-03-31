"""
Ingest dataset reports (PDFs and JSONs) into Neo4j as DocumentChunk nodes.
Run once from scripts/chatbot/: python ingest_reports.py

Creates:
- ProjectReports nodes (one per source_file)
- DocumentChunk nodes with text, embedding, source_file, chunk_index
- (ResearchProject)-[:HAS_REPORTS]->(ProjectReports)-[:CONTAINS_CHUNK]->(DocumentChunk)
- Neo4j vector index 'documentChunkIndex' on DocumentChunk.embedding
"""

import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
from llm import embeddings
from neo4j import GraphDatabase
import config

REPORTS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../reports/reports.json")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../reports")

driver = GraphDatabase.driver(
    config.NEO4J_URI,
    auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD)
)

splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)


def already_ingested(source_file: str) -> bool:
    with driver.session() as session:
        result = session.run(
            "MATCH (pr:ProjectReports {source_file: $source_file})-[:CONTAINS_CHUNK]->(c:DocumentChunk) RETURN count(c) AS n",
            source_file=source_file
        )
        return result.single()["n"] > 0


def create_vector_index(dim: int):
    with driver.session() as session:
        session.run(
            f"""
            CREATE VECTOR INDEX documentChunkIndex IF NOT EXISTS
            FOR (c:DocumentChunk) ON (c.embedding)
            OPTIONS {{indexConfig: {{`vector.dimensions`: {dim}, `vector.similarity_function`: 'cosine'}}}}
            """
        )
    print(f"Vector index 'documentChunkIndex' ensured (dim={dim})")


def ingest_chunks(source_file: str, chunks: list[str], element_ids: list[str]):
    with driver.session() as session:
        for i, chunk_text in enumerate(chunks):
            emb = embeddings.embed_documents([chunk_text])[0]
            # Create ProjectReports node and DocumentChunk under first project
            session.run(
                """
                MATCH (rp:ResearchProject) WHERE elementId(rp) = $elementId
                MERGE (pr:ProjectReports {source_file: $source_file})
                MERGE (rp)-[:HAS_REPORTS]->(pr)
                CREATE (pr)-[:CONTAINS_CHUNK]->(c:DocumentChunk {
                    text: $text,
                    embedding: $embedding,
                    source_file: $source_file,
                    chunk_index: $chunk_index
                })
                """,
                elementId=element_ids[0],
                text=chunk_text,
                embedding=emb,
                source_file=source_file,
                chunk_index=i
            )
            # Link to additional projects (deduplication: same file, multiple projects)
            for eid in element_ids[1:]:
                session.run(
                    """
                    MATCH (rp:ResearchProject) WHERE elementId(rp) = $elementId
                    MATCH (pr:ProjectReports {source_file: $source_file})
                    MERGE (rp)-[:HAS_REPORTS]->(pr)
                    """,
                    elementId=eid,
                    source_file=source_file,
                )


def extract_text_pdf(path: str) -> str:
    doc = fitz.open(path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    return "\n".join(pages)


def extract_text_json(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return json.dumps(data, indent=2)


def main():
    with open(REPORTS_JSON, "r") as f:
        reports_data = json.load(f)

    # Group reports by source_file to handle duplicates
    file_to_eids: dict[str, list] = {}
    file_to_type: dict[str, str] = {}
    for entry in reports_data["reports"]:
        fname = entry["report_name"]
        eid = entry["elementId"]
        rtype = entry["report_type"]
        file_to_eids.setdefault(fname, []).append(eid)
        file_to_type[fname] = rtype

    # Get embedding dimension
    dim = len(embeddings.embed_query("test"))
    create_vector_index(dim)

    total_chunks = 0
    for fname, element_ids in file_to_eids.items():
        if already_ingested(fname):
            print(f"  [skip] {fname} already ingested")
            continue

        fpath = os.path.join(REPORTS_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  [warn] File not found: {fpath}")
            continue

        ftype = file_to_type[fname]
        print(f"  [parse] {fname} ({ftype}) -> projects: {len(element_ids)}")

        if ftype == "pdf":
            text = extract_text_pdf(fpath)
        elif ftype == "json":
            text = extract_text_json(fpath)
        else:
            print(f"  [warn] Unknown type: {ftype}")
            continue

        chunks = splitter.split_text(text)
        print(f"    -> {len(chunks)} chunks, embedding...")
        ingest_chunks(fname, chunks, element_ids)
        print(f"    -> done ({len(chunks)} chunks ingested)")
        total_chunks += len(chunks)

    print(f"\nIngestion complete. Total new chunks: {total_chunks}")
    driver.close()


if __name__ == "__main__":
    main()
