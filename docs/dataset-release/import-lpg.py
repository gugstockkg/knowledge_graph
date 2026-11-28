"""Recreate the released LPG in an empty Neo4j 5.26+ database."""

import argparse
import csv
import gzip
import json
import os
from getpass import getpass
from itertools import islice
from pathlib import Path

from neo4j import GraphDatabase


def load(session, path, statement):
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        while batch := list(islice(reader, 2000)):
            for row in batch:
                for field in ("LABELS_JSON", "PROPERTIES_JSON"):
                    if field in row:
                        row[field] = json.loads(row[field])
            session.run(statement, rows=batch).consume()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD") or getpass("Neo4j password: ")
    with (
        GraphDatabase.driver(uri, auth=(user, password)) as driver,
        driver.session(database=os.environ.get("NEO4J_DATABASE", "neo4j")) as session,
    ):
        if session.run("MATCH (n) RETURN count(n) AS size").single()["size"]:
            raise SystemExit("Use an empty database.")
        session.run(
            "CREATE CONSTRAINT exported_lpg_id IF NOT EXISTS "
            "FOR (n:ExportedLpgNode) REQUIRE n.export_id IS UNIQUE"
        ).consume()
        load(
            session,
            args.directory / "lpg-nodes.csv.gz",
            """
            UNWIND $rows AS row
            CREATE (n:ExportedLpgNode {export_id: row.NODE_ID})
            SET n:$(row.LABELS_JSON), n += row.PROPERTIES_JSON
        """,
        )
        load(
            session,
            args.directory / "lpg-relationships.csv.gz",
            """
            UNWIND $rows AS row
            MATCH (a:ExportedLpgNode {export_id: row.SOURCE_ID})
            MATCH (b:ExportedLpgNode {export_id: row.TARGET_ID})
            CREATE (a)-[r:$(row.TYPE)]->(b)
            SET r += row.PROPERTIES_JSON
        """,
        )


if __name__ == "__main__":
    main()
