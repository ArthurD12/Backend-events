"""Base común de los modelos ORM de todos los módulos.

Alembic lee `Base.metadata` para comparar los modelos con la base de datos y generar
migraciones. La convención de nombres da nombres estables a índices y restricciones,
así las migraciones autogeneradas no cambian de una computadora a otra.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
