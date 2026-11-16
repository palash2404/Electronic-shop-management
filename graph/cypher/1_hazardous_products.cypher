// Products that contain a hazardous material.
// The pattern is drawn the way you would sketch it: (node)-[:LINK]->(node).
// Compare with graph/queries/1_hazardous_products.rq and hazardous_products in esms.py.
MATCH (p:Product)-[:HAS_PART]->(:Component)-[:CONTAINS]->(m:Hazardous)
RETURN p.id AS product, p.name AS name, p.condition AS condition,
       collect(DISTINCT m.name) AS hazardous_materials
ORDER BY product
