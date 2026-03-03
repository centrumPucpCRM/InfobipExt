import sqlite3
from datetime import datetime

conn = sqlite3.connect('infobip.db')
cursor = conn.cursor()

cursor.execute("""
    INSERT INTO rdv_ext (party_id, party_number, infobip_external_id, correo, first_name, last_name, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    300000026979342,
    267445,
    '5eb5ea36-5dde-47d6-8332-35e24c6be9a9',
    'rhidalgob@pucp.edu.pe',
    'Rebeca',
    'Hidalgo',
    datetime.now().isoformat(),
    datetime.now().isoformat()
))

conn.commit()
print(f'Inserted RDV with ID: {cursor.lastrowid}')
conn.close()
