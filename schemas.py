"""
Schemas Pydantic — formatos de entrada (Create) e saída (Out) da API.
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------
# Paciente
# ---------------------------------------------------------------
class PacienteCreate(BaseModel):
    nome: str
    rg: str
    cpf: str
    data_nascimento: date
    telefone: str
    cidade: str
    cep: str
    email: EmailStr
    senha: str
    telefone_responsavel: Optional[str] = None


class PacienteOut(BaseModel):
    id_paciente: int
    nome: str
    cidade: str
    email: EmailStr
    status_cadastro: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------
# Cuidador
# ---------------------------------------------------------------
class CuidadorCreate(BaseModel):
    nome: str
    rg: str
    cpf: str
    idade: int = Field(ge=18)
    cidade: str
    cep: str
    telefone: str
    categoria_profissional: str
    numero_registro_coren: Optional[str] = None
    email: EmailStr
    senha: str


class CuidadorOut(BaseModel):
    id_cuidador: int
    nome: str
    cidade: str
    categoria_profissional: str
    email: EmailStr
    status_cadastro: str

    class Config:
        from_attributes = True


class AprovarRecusarCadastroRequest(BaseModel):
    tipo_usuario: str  # "paciente" ou "cuidador"
    id_usuario: int
    novo_status: str  # "aprovado" ou "recusado"


# ---------------------------------------------------------------
# Login
# ---------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    senha: str
    tipo_usuario: str  # "paciente" ou "cuidador"


class LoginResponse(BaseModel):
    autenticado: bool
    tipo_usuario: str
    id_usuario: Optional[int] = None
    nome: Optional[str] = None


# ---------------------------------------------------------------
# Match (paciente <-> cuidador)
# ---------------------------------------------------------------
class MatchResultado(BaseModel):
    id_cuidador: int
    nome: str
    categoria_profissional: str
    cidade: str
    motivo: str


# ---------------------------------------------------------------
# Cuidado (agendamento)
# ---------------------------------------------------------------
class CuidadoCreate(BaseModel):
    id_cuidador: int
    id_paciente: int
    data_agendamento: datetime


class CuidadoOut(BaseModel):
    id_cuidado: int
    id_cuidador: int
    id_paciente: int
    data_agendamento: datetime
    status: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------
# Mensagem (chat)
# ---------------------------------------------------------------
class MensagemCreate(BaseModel):
    id_cuidado: int
    remetente_tipo: str  # "cuidador" ou "paciente"
    remetente_id: int
    texto: str


class MensagemOut(BaseModel):
    id_mensagem: int
    id_cuidado: int
    remetente_tipo: str
    remetente_id: int
    texto: str
    enviado_em: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------
# Assinatura / plano (financeiro)
# ---------------------------------------------------------------
class AssinaturaOut(BaseModel):
    id_assinatura: int
    tipo_usuario: str
    id_usuario: int
    status_pagamento: str
    data_vencimento: date
    data_pagamento: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConfirmarPagamentoRequest(BaseModel):
    id_assinatura: int


# ---------------------------------------------------------------
# Medicação / consulta (Modo Pós-Alta)
# ---------------------------------------------------------------
class MedicacaoCreate(BaseModel):
    id_paciente: int
    nome_medicamento: str
    dosagem: str
    horario: str
    data_inicio: date
    data_fim: Optional[date] = None
    observacoes: Optional[str] = None


class MedicacaoOut(MedicacaoCreate):
    id_medicacao: int

    class Config:
        from_attributes = True


class ConsultaMedicaCreate(BaseModel):
    id_paciente: int
    data_consulta: datetime
    nome_medico: str
    especialidade: str
    eh_retorno: bool = False
    observacoes: Optional[str] = None


class ConsultaMedicaOut(ConsultaMedicaCreate):
    id_consulta: int

    class Config:
        from_attributes = True
