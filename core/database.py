from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import settings

# 1. Crear el motor que se comunica con PostgreSQL
engine = create_engine(settings.database_url)

# 2. Configurar la "fábrica" de sesiones de base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. Clase base de la que heredarán todos tus modelos (tablas)
Base = declarative_base()


# 4. Función de dependencia para usar en tus rutas (cierra la conexión al terminar)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
