from fastapi import FastAPI
from core.database import engine, Base
from core.config import settings

# 1. PRIMERO importamos el modelo para que SQLAlchemy sepa que existe
from models import usuario_model

print(
    "Intentando conectar a:", settings.database_url
)  # Esto imprimirá la URL en tu terminal

# 2. DESPUÉS de importar, le decimos que cree las tablas
Base.metadata.create_all(bind=engine)

print("Las tablas deberían estar creadas.")

# 3. FINALMENTE inicializamos la app
app = FastAPI(title="API Sistema de Eventos")


@app.get("/")
def read_root():
    return {"mensaje": "Servidor funcionando y conectado a la BD"}
