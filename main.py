from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from sqlalchemy import Column, Integer, String, Float, Date, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. Configuração do Banco de Dados SQLite
DATABASE_URL = "sqlite:///./financas.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Modelo de Tabela no Banco de Dados
class TransacaoDB(Base):
    __tablename__ = "transacoes"

    id = Column(Integer, primary_key=True, index=True)
    desc = Column(String, nullable=False)
    valor = Column(Float, nullable=False)
    data = Column(Date, nullable=False)
    tipo = Column(String, nullable=False)
    subcategoria = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

# 3. Schemas de Validação (Pydantic)
class TransacaoSchema(BaseModel):
    desc: str
    valor: float
    data: date
    tipo: str
    subcategoria: Optional[str] = None

class TransacaoResponse(TransacaoSchema):
    id: int

    class Config:
        from_attributes = True

# 4. Inicialização da Aplicação FastAPI
app = FastAPI(title="Minhas Finanças API")

# Habilitar CORS para permitir requisições de origens externas (como o GitHub Pages)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependência para gerenciamento de sessões do banco
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 5. Rotas da API

@app.get("/transacoes", response_model=List[TransacaoResponse])
def listar_transacoes(db: Session = Depends(get_db)):
    """Retorna todas as transações cadastradas."""
    return db.query(TransacaoDB).all()

@app.post("/transacoes", response_model=TransacaoResponse, status_code=201)
def criar_transacao(transacao: TransacaoSchema, db: Session = Depends(get_db)):
    """Cadastra uma nova transação."""
    nova_transacao = TransacaoDB(**transacao.model_dump())
    db.add(nova_transacao)
    db.commit()
    db.refresh(nova_transacao)
    return nova_transacao

@app.delete("/transacoes/{transacao_id}", status_code=204)
def deletar_transacao(transacao_id: int, db: Session = Depends(get_db)):
    """Remove uma transação pelo ID."""
    item = db.query(TransacaoDB).filter(TransacaoDB.id == transacao_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    db.delete(item)
    db.commit()
    return None