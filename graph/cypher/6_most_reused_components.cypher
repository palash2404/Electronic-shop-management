// The components used in the most products: where a shortage would hurt most.
MATCH (c:Component)<-[:HAS_PART]-(p:Product)
RETURN c.id AS component, c.name AS name, count(p) AS used_in_products
ORDER BY used_in_products DESC, component
LIMIT 5
