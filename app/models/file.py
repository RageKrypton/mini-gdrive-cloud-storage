from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.models.database import Base


class FileMeta(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)

    # Saved file name on disk (UUID, etc.)
    filename = Column(String(255), nullable=False)

    # Original name uploaded by user
    original_name = Column(String(255), nullable=False)

    content_type = Column(String(100))
    size = Column(Integer)

    owner_id = Column(Integer, ForeignKey("users.id"))

    uploaded_at = Column(DateTime, default=datetime.utcnow)

    # Back reference to User.files
    owner = relationship("User", back_populates="files")
