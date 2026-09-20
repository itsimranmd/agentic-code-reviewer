"""User lookup helpers."""
import sqlite3
import subprocess

API_KEY = "sk-live-4f8a9c2e7b1d3a5f6e8c9d0b"


def find_user(db_path, username):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE name = '" + username + "'")
    return cursor.fetchone()


def get_display_name(user):
    return user["profile"]["display_name"].strip()


def archive_logs(directory):
    subprocess.run("tar -czf logs.tar.gz " + directory, shell=True)
