#!/usr/bin/env python3
import os
import sqlite3
import argparse
import sys

# Pad naar je settings.db (pas aan als database elders staat)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'settings.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    return conn

def init_db():
    """Maakt de settings-tabel aan als die nog niet bestaat."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value REAL
        )
    ''')
    conn.commit()
    conn.close()

def load_setting(key, default=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row else default

def save_setting(key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    ''', (key, value))
    conn.commit()
    conn.close()

def show_all():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT key, value FROM settings')
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("Geen settings gevonden.")
    else:
        for key, val in rows:
            print(f"{key}: {int(val)}")

def main():
    init_db()

    parser = argparse.ArgumentParser(
        description="CLI voor pulse/pause settings in SQLite"
    )
    sub = parser.add_subparsers(dest='cmd', required=True)

    # get
    p_get = sub.add_parser('get', help='Toon een setting')
    p_get.add_argument('key', choices=['pulse','pause'], help='Welke setting')

    # set
    p_set = sub.add_parser('set', help='Wijzig een setting')
    p_set.add_argument('key', choices=['pulse','pause'], help='Welke setting')
    p_set.add_argument('value', type=int, help='Nieuwe waarde in seconden')

    # show
    sub.add_parser('show', help='Toon alle settings')

    args = parser.parse_args()

    if args.cmd == 'get':
        val = load_setting(args.key)
        if val is None:
            print(f"{args.key} niet gevonden.")
            sys.exit(1)
        print(f"{args.key}: {int(val)}")
    elif args.cmd == 'set':
        save_setting(args.key, args.value)
        print(f"{args.key} is ingesteld op {args.value} s")
    elif args.cmd == 'show':
        show_all()

if __name__ == '__main__':
    main()
