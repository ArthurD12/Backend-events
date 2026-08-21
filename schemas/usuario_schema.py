from pydantic import BaseModel, EmailStr

# Datos requeridos para CREAR un usuario desde el Frontend
class UsuarioCreate(BaseModel):
    nombre: str
    email: EmailStr  # EmailStr valida automáticamente que tenga un formato de correo válido (@)
    password: str
    rol: str = "admin"

# Datos que la API va a DEVOLVER (Ocultamos el password por seguridad)
class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    email: EmailStr
    is_active: bool
    rol: str

    class Config:
        from_attributes = True  # Esto le permite a Pydantic leer los datos del modelo de SQLAlchemy