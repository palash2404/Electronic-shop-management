"""Electronic shop CLI: products, customers, bills and circular-economy reports."""
import csv
from datetime import date
from pathlib import Path

from db import Error, cursor, execute, query

EXPORT_DIR = Path(__file__).parent / "exports"


# ---------- helpers ----------

def show(rows: list[dict]) -> None:
    if not rows:
        print("(no rows)")
        return
    cols = list(rows[0])
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))


def menu(title: str, options: dict) -> None:
    """options: label -> function. Loops until the user picks Back."""
    items = list(options.items())
    while True:
        print(f"\n--- {title} ---")
        for i, (label, _) in enumerate(items, 1):
            print(f"{i}. {label}")
        print("0. Back")
        choice = input("Choice: ").strip()
        if choice == "0":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(items):
            try:
                items[int(choice) - 1][1]()
            except Error as e:
                print(f"Database error: {e}")
        else:
            print("Invalid choice.")


# ---------- products ----------

def list_products():
    show(query("""
        SELECT p.product_id, p.name, p.category, m.name AS manufacturer,
               p.unit_price, p.stock_qty, p.item_condition
        FROM product p JOIN manufacturer m USING (manufacturer_id)
        ORDER BY p.product_id"""))


def add_product():
    values = (
        input("Product ID (e.g. P21): "), input("Name: "), input("Category: "),
        input("Manufacturer ID (e.g. MF01): "), input("Unit price: "),
        input("Stock quantity: "), input("Release year: "),
        input("Condition (new/refurbished): ") or "new",
    )
    execute("""INSERT INTO product (product_id, name, category, manufacturer_id,
               unit_price, stock_qty, release_year, item_condition)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", values)
    print("Product added.")


def update_product():
    pid = input("Product ID: ")
    field = {"1": "unit_price", "2": "stock_qty"}.get(input("1. Price  2. Stock: "))
    if not field:
        print("Invalid choice.")
        return
    n = execute(f"UPDATE product SET {field} = ? WHERE product_id = ?", (input("New value: "), pid))
    print("Product updated." if n else "No product with that ID.")


def delete_product():
    n = execute("DELETE FROM product WHERE product_id = ?", (input("Product ID: "),))
    print("Product deleted." if n else "No product with that ID.")


def product_parts():
    pid = input("Product ID: ")
    show(query("""
        SELECT c.component_id, c.name AS component, pc.quantity, c.recyclable
        FROM product_component pc JOIN component c USING (component_id)
        WHERE pc.product_id = ?""", (pid,)))


# ---------- customers ----------

def list_customers():
    show(query("SELECT * FROM customer ORDER BY customer_id"))


def add_customer():
    execute("INSERT INTO customer (name, phone_no, city) VALUES (?, ?, ?)",
            (input("Name: "), input("Phone: "), input("City: ")))
    print("Customer added.")


def update_customer():
    cid = input("Customer ID: ")
    field = {"1": "name", "2": "phone_no", "3": "city"}.get(input("1. Name  2. Phone  3. City: "))
    if not field:
        print("Invalid choice.")
        return
    n = execute(f"UPDATE customer SET {field} = ? WHERE customer_id = ?", (input("New value: "), cid))
    print("Customer updated." if n else "No customer with that ID.")


def delete_customer():
    n = execute("DELETE FROM customer WHERE customer_id = ?", (input("Customer ID: "),))
    print("Customer deleted." if n else "No customer with that ID.")


# ---------- bills ----------

def list_bills():
    show(query("""
        SELECT b.bill_id, b.bill_date, c.name AS customer,
               SUM(bi.quantity * bi.unit_price) AS total
        FROM bill b
        JOIN customer c USING (customer_id)
        JOIN bill_item bi USING (bill_id)
        GROUP BY b.bill_id, b.bill_date, c.name
        ORDER BY b.bill_date"""))


def new_bill():
    """Create a bill with several items in one transaction; stock is reduced."""
    cid = input("Customer ID: ")
    items = []
    while (pid := input("Product ID (blank to finish): ").strip()):
        items.append((pid, int(input("  Quantity: "))))
    if not items:
        print("No items, bill not created.")
        return
    with cursor(commit=True) as cur:
        cur.execute("INSERT INTO bill (customer_id, bill_date) VALUES (?, ?)", (cid, date.today().isoformat()))
        bill_id = cur.lastrowid
        for pid, qty in items:
            cur.execute("SELECT unit_price, stock_qty FROM product WHERE product_id = ?", (pid,))
            row = cur.fetchone()
            if row is None or row["stock_qty"] < qty:
                raise Error(f"{pid}: unknown product or not enough stock")
            cur.execute("INSERT INTO bill_item VALUES (?, ?, ?, ?)", (bill_id, pid, qty, row["unit_price"]))
            cur.execute("UPDATE product SET stock_qty = stock_qty - ? WHERE product_id = ?", (qty, pid))
    print(f"Bill {bill_id} created.")


# ---------- reports ----------

def hazardous_products():
    """Needs a four-table join in SQL. In the graph this is one path query."""
    show(query("""
        SELECT p.product_id, p.name, p.item_condition,
               GROUP_CONCAT(DISTINCT m.name) AS hazardous_materials
        FROM product p
        JOIN product_component pc  USING (product_id)
        JOIN component_material cm USING (component_id)
        JOIN material m            USING (material_id)
        WHERE m.is_hazardous
        GROUP BY p.product_id, p.name, p.item_condition
        ORDER BY p.product_id"""))


def sales_by_category():
    show(query("""
        SELECT p.category, SUM(bi.quantity) AS units, SUM(bi.quantity * bi.unit_price) AS revenue
        FROM bill_item bi JOIN product p USING (product_id)
        GROUP BY p.category ORDER BY revenue DESC"""))


def critical_material_mass():
    """Grams of each EU critical raw material held in current stock."""
    show(query("""
        SELECT m.name, ROUND(SUM(p.stock_qty * pc.quantity * cm.mass_g), 1) AS grams_in_stock
        FROM product p
        JOIN product_component pc  USING (product_id)
        JOIN component_material cm USING (component_id)
        JOIN material m            USING (material_id)
        WHERE m.is_critical_raw
        GROUP BY m.name ORDER BY grams_in_stock DESC"""))


def export_table():
    tables = ["product", "component", "material", "product_component",
              "component_material", "customer", "bill", "bill_item", "manufacturer"]
    name = input(f"Table ({', '.join(tables)}): ").strip()
    if name not in tables:
        print("Unknown table.")
        return
    rows = query(f"SELECT * FROM {name}")
    EXPORT_DIR.mkdir(exist_ok=True)
    path = EXPORT_DIR / f"{name}.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Exported {len(rows)} rows to {path}")


def main():
    menu("Electronic Shop", {
        "Products": lambda: menu("Products", {
            "List products": list_products, "Add product": add_product,
            "Update price or stock": update_product, "Delete product": delete_product,
            "Show product components": product_parts}),
        "Customers": lambda: menu("Customers", {
            "List customers": list_customers, "Add customer": add_customer,
            "Update customer": update_customer, "Delete customer": delete_customer}),
        "Bills": lambda: menu("Bills", {"List bills": list_bills, "New bill": new_bill}),
        "Reports": lambda: menu("Reports", {
            "Products with hazardous materials": hazardous_products,
            "Sales by category": sales_by_category,
            "Critical raw materials in stock": critical_material_mass,
            "Export a table to CSV": export_table}),
    })
    print("Goodbye.")


if __name__ == "__main__":
    main()
