// A recall: the 3000 mAh battery cell (C02) turns out to be faulty.
// Which products use it, how many are still in stock, and who already bought one?
// OPTIONAL MATCH keeps products nobody has bought yet (like a LEFT JOIN).
MATCH (part:Component {id: 'C02'})<-[:HAS_PART]-(p:Product)
OPTIONAL MATCH (c:Customer)-[:PLACED]->(:Bill)-[:INCLUDES]->(p)
RETURN p.id AS product, p.name AS name, p.stock_qty AS in_stock,
       collect(DISTINCT c.name) AS customers_to_notify
ORDER BY product
