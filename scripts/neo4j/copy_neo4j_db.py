"""
Copy an entire Neo4j database to another Neo4j instance.

Usage:
    python copy_neo4j_db.py [--src-uri URI] [--dst-uri URI]
                            [--src-user USER] [--dst-user USER]
                            [--src-pass PASS] [--dst-pass PASS]
                            [--batch-size N]

Defaults match the project config (src=7688, dst=7687).
"""

import argparse
from neo4j import GraphDatabase


# ── defaults ────────────────────────────────────────────────────────────────
DEFAULT_SRC_URI  = "bolt://localhost:7688"
DEFAULT_DST_URI  = "bolt://localhost:7687"
DEFAULT_USERNAME = "neo4j"
DEFAULT_PASSWORD = "12345678"
DEFAULT_BATCH    = 500


# ── helpers ──────────────────────────────────────────────────────────────────

def wipe_destination(dst_session):
    """Delete every node and relationship in the destination database."""
    print("Wiping destination database…")
    dst_session.run("MATCH (n) DETACH DELETE n")
    print("  done.")


def fetch_nodes(src_session):
    """Return all nodes as dicts with labels, elementId, and properties."""
    result = src_session.run(
        "MATCH (n) RETURN elementId(n) AS eid, labels(n) AS labels, properties(n) AS props"
    )
    return [dict(r) for r in result]


def fetch_relationships(src_session):
    """Return all relationships with type, endpoints, and properties."""
    result = src_session.run(
        """
        MATCH (a)-[r]->(b)
        RETURN elementId(a) AS src_eid,
               elementId(b) AS dst_eid,
               type(r)       AS rel_type,
               properties(r) AS props
        """
    )
    return [dict(r) for r in result]


def _label_str(labels):
    """Convert a list of labels to a Cypher label string, e.g. ['A','B'] -> ':A:B'."""
    return "".join(f":`{lbl}`" for lbl in sorted(labels))


def copy_nodes(nodes, dst_session, batch_size):
    """Create nodes in the destination grouped by label set (no APOC required)."""
    from collections import defaultdict
    print(f"Copying {len(nodes)} nodes…")

    # Group by frozenset of labels so we can build one query per unique label combo.
    groups = defaultdict(list)
    for node in nodes:
        key = tuple(sorted(node["labels"]))
        groups[key].append({"eid": node["eid"], "props": dict(node["props"])})

    created = 0
    for labels, group in groups.items():
        lbl = _label_str(labels)
        for i in range(0, len(group), batch_size):
            batch = group[i : i + batch_size]
            dst_session.run(
                f"UNWIND $batch AS row CREATE (n{lbl}) SET n = row.props, n._src_eid = row.eid",
                batch=batch,
            )
            created += len(batch)
            print(f"  nodes: {created}/{len(nodes)}")
    print("  nodes done.")


def copy_relationships(rels, dst_session, batch_size):
    """Create relationships grouped by type (no APOC required)."""
    from collections import defaultdict
    print(f"Copying {len(rels)} relationships…")

    groups = defaultdict(list)
    for rel in rels:
        groups[rel["rel_type"]].append(
            {"src": rel["src_eid"], "dst": rel["dst_eid"], "props": dict(rel["props"])}
        )

    created = 0
    for rel_type, group in groups.items():
        for i in range(0, len(group), batch_size):
            batch = group[i : i + batch_size]
            dst_session.run(
                f"""
                UNWIND $batch AS row
                MATCH (a {{_src_eid: row.src}})
                MATCH (b {{_src_eid: row.dst}})
                CREATE (a)-[r:`{rel_type}`]->(b)
                SET r = row.props
                """,
                batch=batch,
            )
            created += len(batch)
            print(f"  rels: {created}/{len(rels)}")
    print("  relationships done.")


def cleanup_temp_property(dst_session):
    """Remove the temporary _src_eid property added during copy."""
    print("Removing temporary _src_eid property…")
    dst_session.run("MATCH (n) WHERE n._src_eid IS NOT NULL REMOVE n._src_eid")
    print("  done.")


# ── main ─────────────────────────────────────────────────────────────────────

def copy_database(
    src_uri=DEFAULT_SRC_URI,
    dst_uri=DEFAULT_DST_URI,
    src_user=DEFAULT_USERNAME,
    dst_user=DEFAULT_USERNAME,
    src_pass=DEFAULT_PASSWORD,
    dst_pass=DEFAULT_PASSWORD,
    batch_size=DEFAULT_BATCH,
):
    src_driver = GraphDatabase.driver(src_uri, auth=(src_user, src_pass))
    dst_driver = GraphDatabase.driver(dst_uri, auth=(dst_user, dst_pass))

    try:
        with src_driver.session() as src_session, dst_driver.session() as dst_session:
            wipe_destination(dst_session)

            nodes = fetch_nodes(src_session)
            copy_nodes(nodes, dst_session, batch_size)

            rels = fetch_relationships(src_session)
            copy_relationships(rels, dst_session, batch_size)

            cleanup_temp_property(dst_session)

        print("\nCopy complete.")
    finally:
        src_driver.close()
        dst_driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy a Neo4j database to another instance.")
    parser.add_argument("--src-uri",  default=DEFAULT_SRC_URI,  help="Source bolt URI")
    parser.add_argument("--dst-uri",  default=DEFAULT_DST_URI,  help="Destination bolt URI")
    parser.add_argument("--src-user", default=DEFAULT_USERNAME,  help="Source username")
    parser.add_argument("--dst-user", default=DEFAULT_USERNAME,  help="Destination username")
    parser.add_argument("--src-pass", default=DEFAULT_PASSWORD,  help="Source password")
    parser.add_argument("--dst-pass", default=DEFAULT_PASSWORD,  help="Destination password")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH, help="Nodes/rels per batch")
    args = parser.parse_args()

    copy_database(
        src_uri=args.src_uri,
        dst_uri=args.dst_uri,
        src_user=args.src_user,
        dst_user=args.dst_user,
        src_pass=args.src_pass,
        dst_pass=args.dst_pass,
        batch_size=args.batch_size,
    )
