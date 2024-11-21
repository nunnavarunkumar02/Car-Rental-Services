'''import pymysql as mysql

def connect_db():
    return mysql.connect(
        host="localhost",
        user="root",
        password="sunny",
        database="project"
    )
'''
import mysql.connector as mysql

def connect_db():
    return mysql.connect(
        host="localhost",
        user="root",
        password="sunny",
        database="project"
    )
