# db.py

import pymysql

def get_connection():
    return pymysql.connect(
        host='localhost',
        user='sanjay_gvsite',
        password='CdZehwfq-8H)l9g%',
        database='sanjay_gvsite',
        charset='utf8mb4'
    )
