"""
Modelos SQLAlchemy — espelham exatamente as 15 tabelas de
sql/cuidado_puro_v2.sql. Os nomes de coluna em português batem com o
banco para facilitar o debug (dá pra olhar o MySQL Workbench e o
código lado a lado sem traduzir nada).
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Text,
    DECIMAL, Enum, TIMESTAMP, ForeignKey, UniqueConstraint, func
)
from sqlalchemy.orm import relationship
from database import Base


class EquipeInterna(Base):
    __tablename__ = "equipe_interna"

    id_equipe = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    cpf = Column(String(14), nullable=False, unique=True)
    idade = Column(Integer, nullable=False)
    cidade = Column(String(100), nullable=False)
    cep = Column(String(9), nullable=False)
    telefone = Column(String(20), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    senha = Column(String(255), nullable=False)
    nivel_acesso = Column(
        Enum("ADM", "suporte", "SAC", "financeiro", "marketing",
             "comercial", "frontend", "backend", name="nivel_acesso_enum"),
        nullable=False,
    )
    status = Column(Enum("ativo", "inativo", name="status_equipe_enum"),
                     nullable=False, default="ativo")
    data_criacao = Column(TIMESTAMP, server_default=func.now())


class Cuidador(Base):
    __tablename__ = "cuidador"

    id_cuidador = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    rg = Column(String(20), nullable=False)
    cpf = Column(String(14), nullable=False, unique=True)
    idade = Column(Integer, nullable=False)
    cidade = Column(String(100), nullable=False)
    cep = Column(String(9), nullable=False)
    telefone = Column(String(20), nullable=False)
    categoria_profissional = Column(
        Enum("sem registro", "auxiliar de enfermagem",
             "técnico de enfermagem", "enfermeiro", name="categoria_profissional_enum"),
        nullable=False,
    )
    numero_registro_coren = Column(String(50), nullable=True)
    email = Column(String(150), nullable=False, unique=True)
    senha = Column(String(255), nullable=False)
    status_cadastro = Column(
        Enum("pendente", "aprovado", "recusado", name="status_cadastro_cuidador_enum"),
        nullable=False, default="pendente",
    )
    data_criacao = Column(TIMESTAMP, server_default=func.now())

    cuidados = relationship("Cuidado", back_populates="cuidador")


class Paciente(Base):
    __tablename__ = "paciente"

    id_paciente = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    rg = Column(String(20), nullable=False)
    cpf = Column(String(14), nullable=False, unique=True)
    data_nascimento = Column(Date, nullable=False)
    telefone = Column(String(20), nullable=False)
    cidade = Column(String(100), nullable=False)
    cep = Column(String(9), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    senha = Column(String(255), nullable=False)
    telefone_responsavel = Column(String(20), nullable=True)
    status_cadastro = Column(
        Enum("pendente", "aprovado", "recusado", name="status_cadastro_paciente_enum"),
        nullable=False, default="pendente",
    )
    data_criacao = Column(TIMESTAMP, server_default=func.now())

    cuidados = relationship("Cuidado", back_populates="paciente")
    necessidades = relationship("PacienteNecessidade", back_populates="paciente")
    medicacoes = relationship("Medicacao", back_populates="paciente")
    consultas = relationship("ConsultaMedica", back_populates="paciente")


class Familiar(Base):
    __tablename__ = "familiar"

    id_familiar = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    cpf = Column(String(14), nullable=False, unique=True)
    email = Column(String(150), nullable=False, unique=True)
    senha = Column(String(255), nullable=False)
    telefone = Column(String(20), nullable=False)
    data_criacao = Column(TIMESTAMP, server_default=func.now())


class PacienteFamiliar(Base):
    __tablename__ = "paciente_familiar"
    __table_args__ = (UniqueConstraint("id_paciente", "id_familiar", name="uq_pac_fam"),)

    id_paciente_familiar = Column(Integer, primary_key=True, index=True)
    id_paciente = Column(Integer, ForeignKey("paciente.id_paciente", ondelete="CASCADE"), nullable=False)
    id_familiar = Column(Integer, ForeignKey("familiar.id_familiar", ondelete="CASCADE"), nullable=False)


class Necessidade(Base):
    __tablename__ = "necessidade"

    id_necessidade = Column(Integer, primary_key=True, index=True)
    nome_necessidade = Column(String(100), nullable=False)
    grau_dependencia = Column(Enum("leve", "moderado", "alto", name="grau_dependencia_enum"), nullable=False)


class Habilidade(Base):
    __tablename__ = "habilidade"

    id_habilidade = Column(Integer, primary_key=True, index=True)
    nome_habilidade = Column(String(100), nullable=False)
    restrita_tecnico = Column(Enum("sim", "não", name="restrita_tecnico_enum"), nullable=False)


class PacienteNecessidade(Base):
    __tablename__ = "paciente_necessidade"
    __table_args__ = (UniqueConstraint("id_paciente", "id_necessidade", name="uq_pac_nec"),)

    id_paciente_necessidade = Column(Integer, primary_key=True, index=True)
    id_paciente = Column(Integer, ForeignKey("paciente.id_paciente", ondelete="CASCADE"), nullable=False)
    id_necessidade = Column(Integer, ForeignKey("necessidade.id_necessidade", ondelete="CASCADE"), nullable=False)

    paciente = relationship("Paciente", back_populates="necessidades")
    necessidade = relationship("Necessidade")


class Cuidado(Base):
    __tablename__ = "cuidado"

    id_cuidado = Column(Integer, primary_key=True, index=True)
    id_cuidador = Column(Integer, ForeignKey("cuidador.id_cuidador", ondelete="RESTRICT"), nullable=False)
    id_paciente = Column(Integer, ForeignKey("paciente.id_paciente", ondelete="RESTRICT"), nullable=False)
    data_agendamento = Column(DateTime, nullable=False)
    status = Column(
        Enum("agendado", "em andamento", "concluído", "cancelado", name="status_cuidado_enum"),
        nullable=False, default="agendado",
    )

    cuidador = relationship("Cuidador", back_populates="cuidados")
    paciente = relationship("Paciente", back_populates="cuidados")
    tarefas = relationship("CuidadoTarefa", back_populates="cuidado")
    mensagens = relationship("Mensagem", back_populates="cuidado")


class CuidadoTarefa(Base):
    __tablename__ = "cuidado_tarefa"

    id_cuidado_tarefa = Column(Integer, primary_key=True, index=True)
    id_cuidado = Column(Integer, ForeignKey("cuidado.id_cuidado", ondelete="CASCADE"), nullable=False)
    id_habilidade = Column(Integer, ForeignKey("habilidade.id_habilidade", ondelete="RESTRICT"), nullable=False)
    realizado = Column(Enum("sim", "não", name="realizado_enum"), nullable=False, default="não")

    cuidado = relationship("Cuidado", back_populates="tarefas")
    habilidade = relationship("Habilidade")


class Plano(Base):
    __tablename__ = "plano"

    id_plano = Column(Integer, primary_key=True, index=True)
    nome = Column(Enum("básico", "padrão", "premium", "único", name="plano_nome_enum"), nullable=False, unique=True)
    valor = Column(DECIMAL(10, 2), nullable=False)
    inclui_destaque = Column(Boolean, nullable=False, default=False)


class Assinatura(Base):
    __tablename__ = "assinatura"

    id_assinatura = Column(Integer, primary_key=True, index=True)
    tipo_usuario = Column(Enum("cuidador", "paciente", name="tipo_usuario_assinatura_enum"), nullable=False)
    id_usuario = Column(Integer, nullable=False)
    id_plano = Column(Integer, ForeignKey("plano.id_plano", ondelete="RESTRICT"), nullable=False)
    status_pagamento = Column(
        Enum("pago", "pendente", "atrasado", name="status_pagamento_enum"),
        nullable=False, default="pendente",
    )
    data_vencimento = Column(Date, nullable=False)
    data_pagamento = Column(DateTime, nullable=True)

    plano = relationship("Plano")


class Medicacao(Base):
    __tablename__ = "medicacao"

    id_medicacao = Column(Integer, primary_key=True, index=True)
    id_paciente = Column(Integer, ForeignKey("paciente.id_paciente", ondelete="CASCADE"), nullable=False)
    nome_medicamento = Column(String(150), nullable=False)
    dosagem = Column(String(100), nullable=False)
    horario = Column(String(100), nullable=False)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=True)
    observacoes = Column(Text, nullable=True)

    paciente = relationship("Paciente", back_populates="medicacoes")


class ConsultaMedica(Base):
    __tablename__ = "consulta_medica"

    id_consulta = Column(Integer, primary_key=True, index=True)
    id_paciente = Column(Integer, ForeignKey("paciente.id_paciente", ondelete="CASCADE"), nullable=False)
    data_consulta = Column(DateTime, nullable=False)
    nome_medico = Column(String(150), nullable=False)
    especialidade = Column(String(100), nullable=False)
    eh_retorno = Column(Boolean, nullable=False, default=False)
    observacoes = Column(Text, nullable=True)

    paciente = relationship("Paciente", back_populates="consultas")


class Visita(Base):
    __tablename__ = "visita"

    id_visita = Column(Integer, primary_key=True, index=True)
    pagina = Column(String(150), nullable=False)
    criado_em = Column(TIMESTAMP, server_default=func.now())


class Mensagem(Base):
    __tablename__ = "mensagem"

    id_mensagem = Column(Integer, primary_key=True, index=True)
    id_cuidado = Column(Integer, ForeignKey("cuidado.id_cuidado", ondelete="CASCADE"), nullable=False)
    remetente_tipo = Column(Enum("cuidador", "paciente", name="remetente_tipo_enum"), nullable=False)
    remetente_id = Column(Integer, nullable=False)
    texto = Column(Text, nullable=False)
    enviado_em = Column(TIMESTAMP, server_default=func.now())

    cuidado = relationship("Cuidado", back_populates="mensagens")
