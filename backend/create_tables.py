from sqlalchemy import inspect, text

from database import engine, Base
from models import Deployment

Base.metadata.create_all(bind=engine)

default_columns = {
    "cpu_request": "100m",
    "memory_request": "128Mi",
    "cpu_limit": "500m",
    "memory_limit": "512Mi",
}

inspector = inspect(engine)
existing_columns = {
    column["name"]
    for column in inspector.get_columns(Deployment.__tablename__)
}

with engine.begin() as connection:
    for column_name, default_value in default_columns.items():
        if column_name in existing_columns:
            continue

        escaped_default = default_value.replace("'", "''")
        connection.execute(
            text(
                f"ALTER TABLE {Deployment.__tablename__} "
                f"ADD COLUMN {column_name} VARCHAR "
                f"NOT NULL DEFAULT '{escaped_default}'"
            )
        )

print("Tables created!")
