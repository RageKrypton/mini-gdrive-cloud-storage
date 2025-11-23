# app/models/file.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.database import Base

class FileMeta(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String, nullable=False)   # Name user uploaded
    stored_name = Column(String, nullable=False)     # Name we store on disk
    path = Column(String, nullable=False)            # Full path on disk
    size = Column(Integer, nullable=False)           # Size in bytes
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Many files → one owner (User)
    owner = relationship("User", back_populates="files")
