from sqlalchemy import inspect, text

from database import engine, Base
from models import Deployment

Base.metadata.create_all(bind=engine)

default_columns = {
    "container_port": ("INTEGER", None),
    "cpu_request": ("VARCHAR", "100m"),
    "memory_request": ("VARCHAR", "128Mi"),
    "cpu_limit": ("VARCHAR", "500m"),
    "memory_limit": ("VARCHAR", "512Mi"),
}

inspector = inspect(engine)
existing_columns = {
    column["name"]
    for column in inspector.get_columns(Deployment.__tablename__)
}

with engine.begin() as connection:
    for column_name, (column_type, default_value) in default_columns.items():
        if column_name in existing_columns:
            continue

        default_sql = ""
        if default_value is not None:
            escaped_default = default_value.replace("'", "''")
            default_sql = f" NOT NULL DEFAULT '{escaped_default}'"

        connection.execute(
            text(
                f"ALTER TABLE {Deployment.__tablename__} "
                f"ADD COLUMN {column_name} {column_type}{default_sql}"
            )
        )

print("Tables created!")
