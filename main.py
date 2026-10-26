from datetime import datetime, timedelta, date
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext
from jose import JWTError, jwt

# Configurações de Segurança
SECRET_KEY = "sua_chave_secreta_super_segura_mude_aqui" # Altere para uma string aleatória longa
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # Token válido por 7 dias

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# 1. Banco de Dados SQLite
DATABASE_URL = "sqlite:///./financas.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Modelos no Banco de Dados
class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    transacoes = relationship("TransacaoDB", back_populates="dono")

class TransacaoDB(Base):
    __tablename__ = "transacoes"
    id = Column(Integer, primary_key=True, index=True)
    desc = Column(String, nullable=False)
    valor = Column(Float, nullable=False)
    data = Column(Date, nullable=False)
    tipo = Column(String, nullable=False)
    subcategoria = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    dono = relationship("UserDB", back_populates="transacoes")

Base.metadata.create_all(bind=engine)

# 3. Schemas de Validação
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TransacaoSchema(BaseModel):
    desc: str
    valor: float
    data: date
    tipo: str
    subcategoria: Optional[str] = None

class TransacaoResponse(TransacaoSchema):
    id: int
    user_id: int

    class Config:
        from_attributes = True

# 4. Funções Utilitárias de Segurança
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

app = FastAPI(title="Minhas Finanças API com Autenticação")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "null"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Função para obter o usuário logado a partir do Token
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou token expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(UserDB).filter(UserDB.email == email).first()
    if user is None:
        raise credentials_exception
    return user

# 5. Rotas de Autenticação

@app.post("/register", status_code=201)
def registrar_usuario(user: UserCreate, db: Session = Depends(get_db)):
    user_existente = db.query(UserDB).filter(UserDB.email == user.email).first()
    if user_existente:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    
    hashed_pwd = get_password_hash(user.password)
    novo_usuario = UserDB(email=user.email, hashed_password=hashed_pwd)
    db.add(novo_usuario)
    db.commit()
    return {"message": "Usuário criado com sucesso!"}

@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="E-mail ou senha incorretos")
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# 6. Rotas Protegidas de Transações (Filtram por usuário)

@app.get("/transacoes", response_model=List[TransacaoResponse])
def listar_transacoes(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(TransacaoDB).filter(TransacaoDB.user_id == current_user.id).all()

@app.post("/transacoes", response_model=TransacaoResponse, status_code=201)
def criar_transacao(transacao: TransacaoSchema, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    nova = TransacaoDB(**transacao.model_dump(), user_id=current_user.id)
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

@app.delete("/transacoes/{transacao_id}", status_code=204)
def deletar_transacao(transacao_id: int, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(TransacaoDB).filter(TransacaoDB.id == transacao_id, TransacaoDB.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    db.delete(item)
    db.commit()
    return None