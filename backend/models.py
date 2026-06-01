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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True)