// Grams of each EU critical raw material held in current stock.
// The numbers sit on the relationships (h.quantity, c.mass_g),
// so no extra PartUsage or MaterialContent nodes are needed.
MATCH (p:Product)-[h:HAS_PART]->(:Component)-[c:CONTAINS]->(m:CriticalRaw)
RETURN m.name AS material,
       round(sum(p.stock_qty * h.quantity * c.mass_g), 1) AS grams_in_stock
ORDER BY grams_in_stock DESC
