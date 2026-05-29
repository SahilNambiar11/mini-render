from database import engine

try:
    connection = engine.connect()
    print("Database Connected!")
    connection.close()

except Exception as e:
    print("Error:", e)