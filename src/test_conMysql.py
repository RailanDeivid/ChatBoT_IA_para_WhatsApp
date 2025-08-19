import mysql.connector
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

def fletch_data(query):
    db = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        use_pure=True  
    )

    cursor = db.cursor()
    cursor.execute(query)
    return cursor.fetchall()


data = pd.DataFrame(fletch_data("SELECT * FROM `505 COMPRA` lIMIT 10"))
print(data)

