import sqlite3

conn = sqlite3.connect(r'C:\Users\Windows\Downloads\InfobipExt\infobip.db')
cur = conn.cursor()

# Actualizar el infobip_id
cur.execute("""
UPDATE people_ext 
SET infobip_id = ?
WHERE id = 86486
""", ('110036',))

conn.commit()

# Verificar la actualización
cur.execute("""
SELECT id, party_id, party_number, telefono, infobip_id, created_at, updated_at
FROM people_ext 
WHERE id = 86486
""")
resultado = cur.fetchone()

if resultado:
    print("✓ Registro actualizado exitosamente:")
    print(f"  ID: {resultado[0]}")
    print(f"  party_id: {resultado[1]}")
    print(f"  party_number: {resultado[2]}")
    print(f"  telefono: {resultado[3]}")
    print(f"  infobip_id: {resultado[4]}")
    print(f"  created_at: {resultado[5]}")
    print(f"  updated_at: {resultado[6]}")

conn.close()
