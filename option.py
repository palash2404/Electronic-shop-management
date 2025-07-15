import mysql.connector
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

def main_menu():
    while True:
        print("\n--- Main Menu ---")
        print("1. Customer Management")
        print("2. Product Management")
        print("3. Bill Management")
        print("4. Sales Management")
        print("5. Exit")
        choice = input("Enter your choice: ")

        if choice == '1':
            customer_menu()
        elif choice == '2':
            product_menu()
        elif choice == '3':
            bill_menu()
        elif choice == '4':
            sales_menu()
        elif choice == '5':
            break
        else:
            print("Invalid choice")

def customer_menu():
    while True:
        print("\n--- Customer Management ---")
        print("1. Add Customer")
        print("2. View Customers")
        print("3. Update Customer")
        print("4. Delete Customer")
        print("5. Export Customers to CSV")
        print("6. Back to Main Menu")
        choice = input("Enter choice: ")

        if choice == '1':
            add_customer()
        elif choice == '2':
            view_customers()
        elif choice == '3':
            update_customer()
        elif choice == '4':
            delete_customer()
        elif choice == '5':
            export_customers()
        elif choice == '6':
            break
        else:
            print("Invalid choice.")

def add_customer():
    con = get_connection()
    cur = con.cursor()
    cid = input("Customer ID: ")
    name = input("Customer Name: ")
    phone = input("Phone Number: ")
    try:
        cur.execute("INSERT INTO customer_details (customer_id, name, phone_no) VALUES (%s, %s, %s)",
                    (cid, name, phone))
        con.commit()
        print("Customer added successfully.")
    except Exception as e:
        print("Error:", e)
    finally:
        con.close()

def view_customers():
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM customer_details")
    rows = cur.fetchall()
    print("\nCustomer ID | Name | Phone")
    for row in rows:
        print(row)
    con.close()

def update_customer():
    con = get_connection()
    cur = con.cursor()
    cid = input("Enter customer ID to update: ")
    print("1. Update Name")
    print("2. Update Phone")
    choice = input("Enter your choice: ")
    if choice == '1':
        new_name = input("Enter new name: ")
        cur.execute("UPDATE customer_details SET name=%s WHERE customer_id=%s", (new_name, cid))
    elif choice == '2':
        new_phone = input("Enter new phone: ")
        cur.execute("UPDATE customer_details SET phone_no=%s WHERE customer_id=%s", (new_phone, cid))
    else:
        print("Invalid option.")
        return
    con.commit()
    print("Customer updated successfully.")
    con.close()

def delete_customer():
    con = get_connection()
    cur = con.cursor()
    cid = input("Enter customer ID to delete: ")
    cur.execute("DELETE FROM customer_details WHERE customer_id=%s", (cid,))
    con.commit()
    print("Customer deleted.")
    con.close()

def export_customers():
    con = get_connection()
    df = pd.read_sql("SELECT * FROM customer_details", con)
    df.to_csv("customers.csv", index=False)
    print("Exported to customers.csv")
    con.close()

def product_menu():
    while True:
        print("\n--- Product Management ---")
        print("1. Add Product")
        print("2. View Products")
        print("3. Update Product")
        print("4. Delete Product")
        print("5. Export Products to CSV")
        print("6. Back to Main Menu")
        choice = input("Enter choice: ")

        if choice == '1':
            add_product()
        elif choice == '2':
            view_products()
        elif choice == '3':
            update_product()
        elif choice == '4':
            delete_product()
        elif choice == '5':
            export_products()
        elif choice == '6':
            break
        else:
            print("Invalid choice.")

def add_product():
    con = get_connection()
    cur = con.cursor()
    pid = input("Product ID: ")
    price = input("Price: ")
    qty = input("Quantity: ")
    total = input("Total value: ")
    try:
        cur.execute("INSERT INTO product (product_id, u_price, quantity, total) VALUES (%s, %s, %s, %s)",
                    (pid, price, qty, total))
        con.commit()
        print("Product added.")
    except Exception as e:
        print("Error:", e)
    finally:
        con.close()

def view_products():
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM product")
    rows = cur.fetchall()
    print("\nProduct ID | Price | Quantity | Total")
    for row in rows:
        print(row)
    con.close()

def update_product():
    con = get_connection()
    cur = con.cursor()
    pid = input("Enter product ID to update: ")
    print("1. Update Price")
    print("2. Update Quantity")
    print("3. Update Total")
    choice = input("Enter your choice: ")
    if choice == '1':
        new_price = input("Enter new price: ")
        cur.execute("UPDATE product SET u_price=%s WHERE product_id=%s", (new_price, pid))
    elif choice == '2':
        new_qty = input("Enter new quantity: ")
        cur.execute("UPDATE product SET quantity=%s WHERE product_id=%s", (new_qty, pid))
    elif choice == '3':
        new_total = input("Enter new total: ")
        cur.execute("UPDATE product SET total=%s WHERE product_id=%s", (new_total, pid))
    else:
        print("Invalid choice.")
        return
    con.commit()
    print("Product updated.")
    con.close()

def delete_product():
    con = get_connection()
    cur = con.cursor()
    pid = input("Enter product ID to delete: ")
    cur.execute("DELETE FROM product WHERE product_id=%s", (pid,))
    con.commit()
    print("Product deleted.")
    con.close()

def export_products():
    con = get_connection()
    df = pd.read_sql("SELECT * FROM product", con)
    df.to_csv("products.csv", index=False)
    print("Exported to products.csv")
    con.close()

def bill_menu():
    while True:
        print("\n--- Bill Management ---")
        print("1. Add Bill")
        print("2. View Bills")
        print("3. Update Bill")
        print("4. Delete Bill")
        print("5. Export Bills to CSV")
        print("6. Back to Main Menu")
        choice = input("Enter choice: ")

        if choice == '1':
            add_bill()
        elif choice == '2':
            view_bills()
        elif choice == '3':
            update_bill()
        elif choice == '4':
            delete_bill()
        elif choice == '5':
            export_bills()
        elif choice == '6':
            break
        else:
            print("Invalid choice.")

def add_bill():
    con = get_connection()
    cur = con.cursor()
    sr_no = input("Bill Serial No: ")
    item = input("Item Name: ")
    unit = input("Unit: ")
    qty = input("Quantity: ")
    amt = input("Amount: ")
    try:
        cur.execute(
    "INSERT INTO bill_details (sr_no, item_name, unit, quantity, amount) VALUES (%s, %s, %s, %s, %s)",
    (sr_no, item, unit, qty, amt)
)


        con.commit()
        print("Bill added.")
    except Exception as e:
        print("Error:", e)
    finally:
        con.close()

def view_bills():
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM bill_details")
    rows = cur.fetchall()
    print("\nSr No | Item Name | Unit | Qty | Amount")
    for row in rows:
        print(row)
    con.close()

def update_bill():
    con = get_connection()
    cur = con.cursor()
    sr_no = input("Enter bill serial no to update: ")
    print("1. Update Item Name")
    print("2. Update Unit")
    print("3. Update Quantity")
    print("4. Update Amount")
    choice = input("Enter your choice: ")
    if choice == '1':
        new_item = input("Enter new item name: ")
        cur.execute("UPDATE bill_details SET item_name=%s WHERE sr_no=%s", (new_item, sr_no))
    elif choice == '2':
        new_unit = input("Enter new unit: ")
        cur.execute("UPDATE bill_details SET unit=%s WHERE sr_no=%s", (new_unit, sr_no))
    elif choice == '3':
        new_qty = input("Enter new quantity: ")
        cur.execute("UPDATE bill_details SET quantity=%s WHERE sr_no=%s", (new_qty, sr_no))
    elif choice == '4':
        new_amt = input("Enter new amount: ")
        cur.execute("UPDATE bill_details SET amount=%s WHERE sr_no=%s", (new_amt, sr_no))
    else:
        print("Invalid choice.")
        return
    con.commit()
    print("Bill updated.")
    con.close()

def delete_bill():
    con = get_connection()
    cur = con.cursor()
    sr_no = input("Enter bill serial no to delete: ")
    cur.execute("DELETE FROM bill_details WHERE sr_no=%s", (sr_no,))
    con.commit()
    print("Bill deleted.")
    con.close()

def export_bills():
    con = get_connection()
    df = pd.read_sql("SELECT * FROM bill_details", con)
    df.to_csv("bills.csv", index=False)
    print("Exported to bills.csv")
    con.close()

def sales_menu():
    while True:
        print("\n--- Sales Management ---")
        print("1. Add Sale")
        print("2. View Sales")
        print("3. Update Sale")
        print("4. Delete Sale")
        print("5. Export Sales to CSV")
        print("6. Back to Main Menu")
        choice = input("Enter choice: ")

        if choice == '1':
            add_sale()
        elif choice == '2':
            view_sales()
        elif choice == '3':
            update_sale()
        elif choice == '4':
            delete_sale()
        elif choice == '5':
            export_sales()
        elif choice == '6':
            break
        else:
            print("Invalid choice.")

def add_sale():
    con = get_connection()
    cur = con.cursor()
    pid = input("Product ID: ")
    qty = input("Quantity Sold: ")
    date = input("Date Sold (YYYY-MM-DD): ")
    custid = input("Customer ID: ")
    try:
        cur.execute("INSERT INTO sales (product_id, quantity, datesold, custid) VALUES (%s, %s, %s, %s)",
                    (pid, qty, date, custid))
        con.commit()
        print("Sale recorded.")
    except Exception as e:
        print("Error:", e)
    finally:
        con.close()

def view_sales():
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM sales")
    rows = cur.fetchall()
    print("\nProduct ID | Quantity | Date Sold | Customer ID")
    for row in rows:
        print(row)
    con.close()

def update_sale():
    con = get_connection()
    cur = con.cursor()
    pid = input("Enter product ID to update sale: ")
    print("1. Update Quantity")
    print("2. Update Date Sold")
    print("3. Update Customer ID")
    choice = input("Enter your choice: ")
    if choice == '1':
        new_qty = input("Enter new quantity: ")
        cur.execute("UPDATE sales SET quantity=%s WHERE product_id=%s", (new_qty, pid))
    elif choice == '2':
        new_date = input("Enter new sale date: ")
        cur.execute("UPDATE sales SET datesold=%s WHERE product_id=%s", (new_date, pid))
    elif choice == '3':
        new_custid = input("Enter new customer ID: ")
        cur.execute("UPDATE sales SET custid=%s WHERE product_id=%s", (new_custid, pid))
    else:
        print("Invalid choice.")
        return
    con.commit()
    print("Sale updated.")
    con.close()

def delete_sale():
    con = get_connection()
    cur = con.cursor()
    pid = input("Enter product ID to delete sale: ")
    cur.execute("DELETE FROM sales WHERE product_id=%s", (pid,))
    con.commit()
    print("Sale deleted.")
    con.close()

def export_sales():
    con = get_connection()
    df = pd.read_sql("SELECT * FROM sales", con)
    df.to_csv("sales.csv", index=False)
    print("Exported to sales.csv")
    con.close()
