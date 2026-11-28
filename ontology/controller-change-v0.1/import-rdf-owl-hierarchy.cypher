// Copy rdf-owl-ontology.csv to the import directory of the target Neo4j server.
// Run these statements in the benchmark or a designated test database.
LOAD CSV WITH HEADERS FROM 'file:///rdf-owl-ontology.csv' AS row
WITH row WHERE row.kind = 'class' AND row.neo4j_mapping = 'BenchmarkType.id'
MERGE (t:BenchmarkType {id: row.id})
SET t.iri = row.iri, t.label_ko = row.label_ko;

LOAD CSV WITH HEADERS FROM 'file:///rdf-owl-ontology.csv' AS row
WITH row WHERE row.kind = 'subclass'
MATCH (child:BenchmarkType {id: row.subject})
MATCH (parent:BenchmarkType {id: row.object_or_datatype})
MERGE (child)-[:SUBCLASS_OF]->(parent);

MATCH (child:BenchmarkType)-[:SUBCLASS_OF]->(parent:BenchmarkType)
WHERE child.iri STARTS WITH 'urn:fintos:benchmark:'
  AND parent.iri STARTS WITH 'urn:fintos:benchmark:'
RETURN child.id AS child, parent.id AS parent
ORDER BY child;
