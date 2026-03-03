import sqlite3

conn = sqlite3.connect(r'C:\Users\Windows\Downloads\InfobipExt\infobip.db')
cur = conn.cursor()

# Verificar el esquema de la tabla
cur.execute("PRAGMA table_info(people_ext)")
columnas = cur.fetchall()
print("Esquema de people_ext:")
for col in columnas:
    print(f"  {col[1]} ({col[2]})")

print("\nÚltimo registro insertado:")
cur.execute("""
SELECT * FROM people_ext 
WHERE id = 86486
""")
resultado = cur.fetchone()
print(resultado)

conn.close()
