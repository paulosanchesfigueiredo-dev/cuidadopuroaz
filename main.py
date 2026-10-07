"""
Cuidado Puro — API principal (FastAPI).

Endpoints:
  POST /cadastro/paciente
  POST /cadastro/cuidador
  POST /login
  GET  /match/{id_paciente}
  POST /cuidado                 (criar agendamento)
  GET  /cuidado/{id_cuidador}   (agendamentos de um cuidador)
  POST /mensagens
  GET  /mensagens/{id_cuidado}
  GET  /assinaturas/{tipo_usuario}/{id_usuario}

  + tudo em /pagamento/... (ver pagamento.py)

Rodar localmente (ver SETUP_LOCAL.md para o passo a passo completo):
    uvicorn main:app --reload
"""

from datetime import date, datetime
from typing import List

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func

import models
import schemas
from database import engine, get_db, Base
from pagamento import router as pagamento_router

# Cria as tabelas automaticamente se ainda não existirem
# (o ideal é rodar sql/cuidado_puro_v2.sql direto no MySQL antes,
# isso aqui é só uma rede de segurança)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cuidado Puro API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pagamento_router)


@app.get("/")
def raiz():
    return {"status": "online", "projeto": "Cuidado Puro API v2"}


# ---------------------------------------------------------------
# Tráfego (sem número fantasma: cada acesso real grava uma linha)
# ---------------------------------------------------------------
@app.post("/tracking/visita")
def registrar_visita(pagina: str, db: Session = Depends(get_db)):
    db.add(models.Visita(pagina=pagina))
    db.commit()
    return {"ok": True}


@app.get("/adm/trafego")
def trafego_adm(db: Session = Depends(get_db)):
    from datetime import timedelta
    agora = datetime.utcnow()

    hoje = db.scalar(
        select(func.count()).select_from(models.Visita)
        .where(func.date(models.Visita.criado_em) == agora.date())
    ) or 0
    semana = db.scalar(
        select(func.count()).select_from(models.Visita)
        .where(models.Visita.criado_em >= agora - timedelta(days=7))
    ) or 0
    mes = db.scalar(
        select(func.count()).select_from(models.Visita)
        .where(models.Visita.criado_em >= agora - timedelta(days=30))
    ) or 0

    por_dia = dict(
        db.execute(
            select(func.date(models.Visita.criado_em), func.count())
            .where(models.Visita.criado_em >= agora - timedelta(days=14))
            .group_by(func.date(models.Visita.criado_em))
        ).all()
    )
    por_pagina = dict(
        db.execute(
            select(models.Visita.pagina, func.count())
            .group_by(models.Visita.pagina)
            .order_by(func.count().desc())
            .limit(10)
        ).all()
    )

    return {
        "hoje": hoje,
        "ultimos_7_dias": semana,
        "ultimos_30_dias": mes,
        "por_dia_ultimos_14": {str(k): v for k, v in por_dia.items()},
        "por_pagina": por_pagina,
    }


# ---------------------------------------------------------------
# Cadastro
# ---------------------------------------------------------------
@app.post("/cadastro/paciente", response_model=schemas.PacienteOut)
def cadastrar_paciente(dados: schemas.PacienteCreate, db: Session = Depends(get_db)):
    existente = db.scalar(select(models.Paciente).where(models.Paciente.email == dados.email))
    if existente:
        raise HTTPException(status_code=400, detail="Já existe paciente cadastrado com esse e-mail.")

    paciente = models.Paciente(**dados.model_dump())
    db.add(paciente)
    db.commit()
    db.refresh(paciente)

    # já cria a assinatura "única" do paciente como pendente
    plano_unico = db.scalar(select(models.Plano).where(models.Plano.nome == "único"))
    if plano_unico:
        db.add(models.Assinatura(
            tipo_usuario="paciente",
            id_usuario=paciente.id_paciente,
            id_plano=plano_unico.id_plano,
            status_pagamento="pendente",
            data_vencimento=date.today(),
        ))
        db.commit()

    return paciente


@app.post("/cadastro/cuidador", response_model=schemas.CuidadorOut)
def cadastrar_cuidador(dados: schemas.CuidadorCreate, db: Session = Depends(get_db)):
    existente = db.scalar(select(models.Cuidador).where(models.Cuidador.email == dados.email))
    if existente:
        raise HTTPException(status_code=400, detail="Já existe cuidador cadastrado com esse e-mail.")

    if dados.categoria_profissional == "sem registro" and dados.numero_registro_coren:
        raise HTTPException(
            status_code=400,
            detail="Categoria 'sem registro' não pode ter número de COREN preenchido.",
        )

    cuidador = models.Cuidador(**dados.model_dump())
    db.add(cuidador)
    db.commit()
    db.refresh(cuidador)
    return cuidador


# ---------------------------------------------------------------
# Login (simples — compara e-mail/senha direto; trocar por hash +
# JWT antes de qualquer uso fora de demonstração)
# ---------------------------------------------------------------
@app.post("/login", response_model=schemas.LoginResponse)
def login(dados: schemas.LoginRequest, db: Session = Depends(get_db)):
    if dados.tipo_usuario == "paciente":
        usuario = db.scalar(select(models.Paciente).where(models.Paciente.email == dados.email))
    elif dados.tipo_usuario == "cuidador":
        usuario = db.scalar(select(models.Cuidador).where(models.Cuidador.email == dados.email))
    else:
        raise HTTPException(status_code=400, detail="tipo_usuario deve ser 'paciente' ou 'cuidador'.")

    if not usuario or usuario.senha != dados.senha:
        return schemas.LoginResponse(autenticado=False, tipo_usuario=dados.tipo_usuario)

    id_usuario = usuario.id_paciente if dados.tipo_usuario == "paciente" else usuario.id_cuidador
    return schemas.LoginResponse(
        autenticado=True,
        tipo_usuario=dados.tipo_usuario,
        id_usuario=id_usuario,
        nome=usuario.nome,
    )


# ---------------------------------------------------------------
# Match — cruza a necessidade do paciente com a categoria do cuidador
# ---------------------------------------------------------------
CATEGORIAS_POR_ORDEM = ["sem registro", "auxiliar de enfermagem", "técnico de enfermagem", "enfermeiro"]
CATEGORIA_MINIMA_POR_GRAU = {
    "leve": "sem registro",
    "moderado": "auxiliar de enfermagem",
    "alto": "técnico de enfermagem",
}


def _categoria_atende(categoria_cuidador: str, grau_necessidade: str) -> bool:
    minima = CATEGORIA_MINIMA_POR_GRAU[grau_necessidade]
    return CATEGORIAS_POR_ORDEM.index(categoria_cuidador) >= CATEGORIAS_POR_ORDEM.index(minima)


class LoginAutoRequest(schemas.BaseModel):
    email: str
    senha: str


@app.post("/Login")
def login_automatico(dados: LoginAutoRequest, db: Session = Depends(get_db)):
    """
    Compatível com o front-end existente (js/login.js): recebe só
    e-mail e senha, sem o usuário dizer se é paciente ou cuidador —
    a API tenta nas duas tabelas e descobre sozinha.
    """
    paciente = db.scalar(select(models.Paciente).where(models.Paciente.email == dados.email))
    if paciente and paciente.senha == dados.senha:
        return {"autenticado": True, "tipo_usuario": "paciente", "id_usuario": paciente.id_paciente, "nome": paciente.nome}

    cuidador = db.scalar(select(models.Cuidador).where(models.Cuidador.email == dados.email))
    if cuidador and cuidador.senha == dados.senha:
        return {"autenticado": True, "tipo_usuario": "cuidador", "id_usuario": cuidador.id_cuidador, "nome": cuidador.nome}

    raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")


@app.get("/match/{id_paciente}", response_model=List[schemas.MatchResultado])
def buscar_match(id_paciente: int, db: Session = Depends(get_db)):
    paciente = db.get(models.Paciente, id_paciente)
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    necessidades = db.scalars(
        select(models.Necessidade)
        .join(models.PacienteNecessidade)
        .where(models.PacienteNecessidade.id_paciente == id_paciente)
    ).all()

    grau_mais_alto = "leve"
    for n in necessidades:
        if n.grau_dependencia == "alto":
            grau_mais_alto = "alto"
            break
        if n.grau_dependencia == "moderado" and grau_mais_alto != "alto":
            grau_mais_alto = "moderado"

    cuidadores = db.scalars(select(models.Cuidador).where(models.Cuidador.cidade == paciente.cidade)).all()

    resultados = []
    for c in cuidadores:
        if _categoria_atende(c.categoria_profissional, grau_mais_alto):
            resultados.append(schemas.MatchResultado(
                id_cuidador=c.id_cuidador,
                nome=c.nome,
                categoria_profissional=c.categoria_profissional,
                cidade=c.cidade,
                motivo=f"Atende necessidade de grau '{grau_mais_alto}' na mesma cidade ({c.cidade}).",
            ))

    return resultados


# ---------------------------------------------------------------
# Cuidado (agendamento) — ao criar, já libera o chat entre as partes
# ---------------------------------------------------------------
@app.post("/cuidado", response_model=schemas.CuidadoOut)
def criar_cuidado(dados: schemas.CuidadoCreate, db: Session = Depends(get_db)):
    if not db.get(models.Cuidador, dados.id_cuidador):
        raise HTTPException(status_code=404, detail="Cuidador não encontrado.")
    if not db.get(models.Paciente, dados.id_paciente):
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    cuidado = models.Cuidado(**dados.model_dump())
    db.add(cuidado)
    db.commit()
    db.refresh(cuidado)
    return cuidado


@app.get("/cuidado/{id_cuidador}", response_model=List[schemas.CuidadoOut])
def listar_cuidados_do_cuidador(id_cuidador: int, db: Session = Depends(get_db)):
    return db.scalars(select(models.Cuidado).where(models.Cuidado.id_cuidador == id_cuidador)).all()


@app.get("/cuidado/paciente/{id_paciente}", response_model=List[schemas.CuidadoOut])
def listar_cuidados_do_paciente(id_paciente: int, db: Session = Depends(get_db)):
    return db.scalars(select(models.Cuidado).where(models.Cuidado.id_paciente == id_paciente)).all()


class AtualizarStatusCuidadoRequest(schemas.BaseModel):
    status: str  # "agendado" | "em andamento" | "concluído" | "cancelado"


@app.patch("/cuidado/{id_cuidado}/status")
def atualizar_status_cuidado(id_cuidado: int, dados: AtualizarStatusCuidadoRequest, db: Session = Depends(get_db)):
    """Usado pelo cuidador para aceitar (em andamento), recusar (cancelado) ou concluir um agendamento."""
    cuidado = db.get(models.Cuidado, id_cuidado)
    if not cuidado:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")
    validos = {"agendado", "em andamento", "concluído", "cancelado"}
    if dados.status not in validos:
        raise HTTPException(status_code=400, detail=f"status deve ser um de: {', '.join(validos)}")
    cuidado.status = dados.status
    db.commit()
    return {"mensagem": "Status atualizado.", "id_cuidado": id_cuidado, "status": dados.status}


@app.get("/cuidador/{id_cuidador}/agenda")
def agenda_do_cuidador(id_cuidador: int, db: Session = Depends(get_db)):
    """Agenda do cuidador já com nome/telefone/cidade do paciente — evita N chamadas no front-end."""
    linhas = db.execute(
        select(models.Cuidado, models.Paciente)
        .join(models.Paciente, models.Paciente.id_paciente == models.Cuidado.id_paciente)
        .where(models.Cuidado.id_cuidador == id_cuidador)
        .order_by(models.Cuidado.data_agendamento)
    ).all()
    return [
        {
            "id_cuidado": c.id_cuidado,
            "id_paciente": p.id_paciente,
            "nome_paciente": p.nome,
            "telefone_paciente": p.telefone,
            "cidade_paciente": p.cidade,
            "data_agendamento": c.data_agendamento,
            "status": c.status,
        }
        for c, p in linhas
    ]


@app.get("/paciente/{id_paciente}/agenda")
def agenda_do_paciente(id_paciente: int, db: Session = Depends(get_db)):
    """Agenda do paciente já com nome/categoria do cuidador — evita N chamadas no front-end."""
    linhas = db.execute(
        select(models.Cuidado, models.Cuidador)
        .join(models.Cuidador, models.Cuidador.id_cuidador == models.Cuidado.id_cuidador)
        .where(models.Cuidado.id_paciente == id_paciente)
        .order_by(models.Cuidado.data_agendamento)
    ).all()
    return [
        {
            "id_cuidado": c.id_cuidado,
            "id_cuidador": cu.id_cuidador,
            "nome_cuidador": cu.nome,
            "categoria_cuidador": cu.categoria_profissional,
            "data_agendamento": c.data_agendamento,
            "status": c.status,
        }
        for c, cu in linhas
    ]


# ---------------------------------------------------------------
# Mensagens (chat básico, dentro de um agendamento já existente)
# ---------------------------------------------------------------
@app.post("/mensagens", response_model=schemas.MensagemOut)
def enviar_mensagem(dados: schemas.MensagemCreate, db: Session = Depends(get_db)):
    if not db.get(models.Cuidado, dados.id_cuidado):
        raise HTTPException(status_code=404, detail="Agendamento (cuidado) não encontrado — chat só é liberado após o match/agendamento.")

    mensagem = models.Mensagem(**dados.model_dump())
    db.add(mensagem)
    db.commit()
    db.refresh(mensagem)
    return mensagem


@app.get("/mensagens/{id_cuidado}", response_model=List[schemas.MensagemOut])
def listar_mensagens(id_cuidado: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(models.Mensagem)
        .where(models.Mensagem.id_cuidado == id_cuidado)
        .order_by(models.Mensagem.enviado_em)
    ).all()


# ---------------------------------------------------------------
# Assinaturas (financeiro / dashboard ADM)
# ---------------------------------------------------------------
@app.get("/adm/resumo")
def resumo_adm(db: Session = Depends(get_db)):
    """
    Alimenta o dashboard do ADM inteiro em uma única chamada: totais,
    status de cadastro, assinaturas por status/plano, cadastros
    recentes pendentes e receita do mês — tudo puxado do banco real.
    """
    total_pacientes = db.scalar(select(func.count()).select_from(models.Paciente)) or 0
    total_cuidadores = db.scalar(select(func.count()).select_from(models.Cuidador)) or 0

    status_pacientes = dict(
        db.execute(
            select(models.Paciente.status_cadastro, func.count())
            .group_by(models.Paciente.status_cadastro)
        ).all()
    )
    status_cuidadores = dict(
        db.execute(
            select(models.Cuidador.status_cadastro, func.count())
            .group_by(models.Cuidador.status_cadastro)
        ).all()
    )

    assinaturas_status = dict(
        db.execute(
            select(models.Assinatura.status_pagamento, func.count())
            .group_by(models.Assinatura.status_pagamento)
        ).all()
    )

    receita_paga = db.scalar(
        select(func.coalesce(func.sum(models.Plano.valor), 0))
        .select_from(models.Assinatura)
        .join(models.Plano, models.Plano.id_plano == models.Assinatura.id_plano)
        .where(models.Assinatura.status_pagamento == "pago")
    ) or 0

    pendentes = []
    for p in db.scalars(select(models.Paciente).where(models.Paciente.status_cadastro == "pendente")).all():
        pendentes.append({"tipo_usuario": "paciente", "id_usuario": p.id_paciente, "nome": p.nome, "email": p.email, "data_criacao": p.data_criacao})
    for c in db.scalars(select(models.Cuidador).where(models.Cuidador.status_cadastro == "pendente")).all():
        pendentes.append({"tipo_usuario": "cuidador", "id_usuario": c.id_cuidador, "nome": c.nome, "email": c.email, "data_criacao": c.data_criacao})

    return {
        "usuarios": {
            "total": total_pacientes + total_cuidadores,
            "pacientes": total_pacientes,
            "cuidadores": total_cuidadores,
            "status_pacientes": status_pacientes,
            "status_cuidadores": status_cuidadores,
        },
        "assinaturas": {
            "por_status": assinaturas_status,
            "receita_paga": float(receita_paga),
        },
        "cadastros_pendentes": pendentes,
    }


@app.get("/adm/usuarios")
def listar_usuarios_adm(db: Session = Depends(get_db)):
    """Lista completa de pacientes + cuidadores reais — alimenta o painel 'Usuários' do ADM (somente leitura)."""
    resultado = []
    for p in db.scalars(select(models.Paciente)).all():
        resultado.append({
            "tipo_usuario": "paciente",
            "id_usuario": p.id_paciente,
            "nome": p.nome,
            "email": p.email,
            "status_cadastro": p.status_cadastro,
            "data_criacao": p.data_criacao,
        })
    for c in db.scalars(select(models.Cuidador)).all():
        resultado.append({
            "tipo_usuario": "cuidador",
            "id_usuario": c.id_cuidador,
            "nome": c.nome,
            "email": c.email,
            "status_cadastro": c.status_cadastro,
            "data_criacao": c.data_criacao,
        })
    resultado.sort(key=lambda u: u["data_criacao"] or "", reverse=True)
    return resultado


@app.get("/adm/assinaturas")
def listar_assinaturas_adm(db: Session = Depends(get_db)):
    """Lista completa de mensalidades com nome do usuário e plano — alimenta o painel de Pagamentos do ADM."""
    linhas = db.execute(
        select(models.Assinatura, models.Plano)
        .join(models.Plano, models.Plano.id_plano == models.Assinatura.id_plano)
        .order_by(models.Assinatura.data_vencimento.desc())
    ).all()

    resultado = []
    for assinatura, plano in linhas:
        if assinatura.tipo_usuario == "paciente":
            usuario = db.get(models.Paciente, assinatura.id_usuario)
        else:
            usuario = db.get(models.Cuidador, assinatura.id_usuario)
        resultado.append({
            "id_assinatura": assinatura.id_assinatura,
            "tipo_usuario": assinatura.tipo_usuario,
            "id_usuario": assinatura.id_usuario,
            "nome_usuario": usuario.nome if usuario else "(removido)",
            "plano": plano.nome,
            "valor": float(plano.valor),
            "data_vencimento": assinatura.data_vencimento,
            "status_pagamento": assinatura.status_pagamento,
        })
    return resultado


@app.post("/adm/aprovar-recusar-cadastro")
def aprovar_recusar_cadastro(dados: schemas.AprovarRecusarCadastroRequest, db: Session = Depends(get_db)):
    """Usado pelo dashboard do ADM para aprovar ou recusar um cadastro pendente."""
    if dados.novo_status not in ("aprovado", "recusado"):
        raise HTTPException(status_code=400, detail="novo_status deve ser 'aprovado' ou 'recusado'.")

    if dados.tipo_usuario == "paciente":
        usuario = db.get(models.Paciente, dados.id_usuario)
    elif dados.tipo_usuario == "cuidador":
        usuario = db.get(models.Cuidador, dados.id_usuario)
    else:
        raise HTTPException(status_code=400, detail="tipo_usuario deve ser 'paciente' ou 'cuidador'.")

    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    usuario.status_cadastro = dados.novo_status
    db.commit()
    return {"mensagem": f"Cadastro {dados.novo_status} com sucesso.", "id_usuario": dados.id_usuario}


@app.get("/assinaturas/{tipo_usuario}/{id_usuario}", response_model=List[schemas.AssinaturaOut])
def listar_assinaturas(tipo_usuario: str, id_usuario: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(models.Assinatura).where(
            models.Assinatura.tipo_usuario == tipo_usuario,
            models.Assinatura.id_usuario == id_usuario,
        )
    ).all()


# ---------------------------------------------------------------
# Medicação / Consulta médica (Modo Pós-Alta)
# ---------------------------------------------------------------
@app.post("/medicacao", response_model=schemas.MedicacaoOut)
def cadastrar_medicacao(dados: schemas.MedicacaoCreate, db: Session = Depends(get_db)):
    medicacao = models.Medicacao(**dados.model_dump())
    db.add(medicacao)
    db.commit()
    db.refresh(medicacao)
    return medicacao


@app.get("/medicacao/{id_paciente}", response_model=List[schemas.MedicacaoOut])
def listar_medicacoes(id_paciente: int, db: Session = Depends(get_db)):
    return db.scalars(select(models.Medicacao).where(models.Medicacao.id_paciente == id_paciente)).all()


@app.post("/consulta-medica", response_model=schemas.ConsultaMedicaOut)
def cadastrar_consulta(dados: schemas.ConsultaMedicaCreate, db: Session = Depends(get_db)):
    consulta = models.ConsultaMedica(**dados.model_dump())
    db.add(consulta)
    db.commit()
    db.refresh(consulta)
    return consulta


@app.get("/consulta-medica/{id_paciente}", response_model=List[schemas.ConsultaMedicaOut])
def listar_consultas(id_paciente: int, db: Session = Depends(get_db)):
    return db.scalars(select(models.ConsultaMedica).where(models.ConsultaMedica.id_paciente == id_paciente)).all()
