from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone

from database import Base


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=False)
    container_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="running")
    cpu_request = Column(String, nullable=False, default="100m")
    memory_request = Column(String, nullable=False, default="128Mi")
    cpu_limit = Column(String, nullable=False, default="500m")
    memory_limit = Column(String, nullable=False, default="512Mi")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True)
