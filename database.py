"""
Conexão com o banco MySQL (cuidado_puro_v2) via SQLAlchemy.

Configure a variável de ambiente DATABASE_URL antes de rodar, por exemplo:

    Windows (PowerShell):
        $env:DATABASE_URL = "mysql+pymysql://usuario:senha@localhost:3306/cuidado_puro_v2"

    Linux / Mac:
        export DATABASE_URL="mysql+pymysql://usuario:senha@localhost:3306/cuidado_puro_v2"

Se DATABASE_URL não for definida, cai no padrão abaixo (ajuste usuário/senha
conforme seu MySQL local).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:root@localhost:3306/cuidado_puro_v2",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency do FastAPI: abre e fecha a sessão do banco por requisição."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
