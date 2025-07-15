import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
from option import main_menu

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

def get_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        print(f"Database connection failed: {e}")
        return None

def register_user():
    print("\n--- Register New User ---")
    loginid = input("Enter user ID: ")
    password = input("Enter password: ")
    name = input("Enter your name: ")

    con = get_connection()
    if con:
        try:
            cur = con.cursor()
            cur.execute("INSERT INTO registration (loginid, password, name) VALUES (%s, %s, %s)",
                        (loginid, password, name))
            con.commit()
            print("User registered successfully.")
        except Error as e:
            print(f"Error: {e}")
        finally:
            con.close()

def login_user():
    print("\n--- User Login ---")
    loginid = input("Enter user ID: ")
    password = input("Enter password: ")

    con = get_connection()
    if con:
        try:
            cur = con.cursor()
            cur.execute("SELECT * FROM registration WHERE loginid = %s AND password = %s",
                        (loginid, password))
            result = cur.fetchone()
            if result:
                print("Login successful.\n")
                main_menu()
            else:
                print("Login failed. Check credentials or register first.")
        except Error as e:
            print(f"Error: {e}")
        finally:
            con.close()