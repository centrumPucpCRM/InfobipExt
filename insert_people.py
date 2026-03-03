import sqlite3
from datetime import datetime

# Conectar a la base de datos
conn = sqlite3.connect(r'C:\Users\Windows\Downloads\InfobipExt\infobip.db')
cur = conn.cursor()

# Insertar el nuevo registro
cur.execute("""
INSERT INTO people_ext (party_id, party_number, telefono, infobip_id, created_at, updated_at)
VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
""", (300000122627833, 1336891, '51949748676', '110036'))

conn.commit()

# Verificar la inserción
cur.execute("""
SELECT id, party_id, party_number, telefono, infobip_id, created_at, updated_at
FROM people_ext
WHERE party_id = 300000122627833
""")

resultado = cur.fetchone()

if resultado:
    print("✓ Registro insertado exitosamente:")
    print(f"  ID: {resultado[0]}")
    print(f"  party_id: {resultado[1]}")
    print(f"  party_number: {resultado[2]}")
    print(f"  telefono: {resultado[3]}")
    print(f"  infobip_id: {resultado[4]}")
    print(f"  created_at: {resultado[5]}")
    print(f"  updated_at: {resultado[6]}")
else:
    print("✗ Error: No se insertó el registro")

conn.close()
