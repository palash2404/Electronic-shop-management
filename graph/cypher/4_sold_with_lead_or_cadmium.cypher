// Which sales included a product containing lead or cadmium, and to whom?
// One pattern from the customer all the way to the material: five hops.
MATCH (c:Customer)-[:PLACED]->(b:Bill)-[:INCLUDES]->(p:Product)
      -[:HAS_PART]->(:Component)-[:CONTAINS]->(m:Material)
WHERE m.name IN ['Lead', 'Cadmium']
RETURN DISTINCT toString(b.date) AS date, c.name AS customer, p.name AS product, m.name AS material
ORDER BY date, product, material
