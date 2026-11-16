// Units sold and revenue per product category.
// There is no GROUP BY in Cypher: every non-aggregated column in RETURN is a group key.
MATCH (:Bill)-[i:INCLUDES]->(p:Product)
RETURN p.category AS category, sum(i.quantity) AS units,
       sum(i.quantity * i.unit_price) AS revenue
ORDER BY revenue DESC
