# db.py

import pymysql

def get_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='',
        database='project-swasta',
        charset='utf8mb4'
    )
