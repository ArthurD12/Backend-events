from sqlalchemy import Column, Integer, String, Boolean
from core.database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)  # Aquí guardaremos el hash, nunca la clave en texto plano
    is_active = Column(Boolean, default=True)
    rol = Column(String(20), default="admin")  # Puede ser "admin" (tu amigo) o "staff" (almacén)