from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class NetworkLink(Base):
    __tablename__ = "network_links"
    __table_args__ = (
        UniqueConstraint(
            "server_id",
            "switch_id",
            "server_interface",
            "server_mac",
            name="uq_network_link_endpoint",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    switch_id = Column(Integer, ForeignKey("switches.id", ondelete="CASCADE"), nullable=False)

    server_interface = Column(String(100), nullable=False)
    server_ip = Column(String(45), nullable=True)
    server_mac = Column(String(32), nullable=False)
    switch_interface = Column(String(120), nullable=True)
    vlan = Column(String(64), nullable=True)
    status = Column(String(32), default="unknown")
    raw_output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)

    server = relationship("Server", lazy="selectin")
    switch = relationship("Switch", lazy="selectin")
