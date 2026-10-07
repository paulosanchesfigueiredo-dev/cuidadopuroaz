"""
Módulo de pagamento — geração de QR Code Pix ESTÁTICO (padrão EMV/BR Code
do Banco Central) a partir da própria chave Pix do usuário, sem precisar
de conta em gateway pago (Mercado Pago, Stripe, etc).

Isso é só para DEMONSTRAÇÃO: qualquer banco consegue ler e pagar esse QR
Code normalmente, mas a confirmação de que o Pix caiu é feita manualmente
(endpoint /pagamento/confirmar) — não existe webhook automático de banco
aqui, porque isso exige integração paga com uma instituição financeira.

Veja GUIA_PIX_TESTE.md para o passo a passo de uso na demonstração.
"""

import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime

import models
import schemas
from database import get_db

router = APIRouter(prefix="/pagamento", tags=["pagamento"])


# ---------------------------------------------------------------
# Geração do payload Pix (BR Code / EMV) — implementação própria,
# sem depender de nenhum serviço pago.
# ---------------------------------------------------------------

def _crc16_ccitt(payload: str) -> str:
    """CRC16-CCITT (polinômio 0x1021, valor inicial 0xFFFF) — é o
    checksum exigido pelo padrão Pix no campo 63."""
    poly = 0x1021
    result = 0xFFFF
    data = payload.encode("utf-8")
    for byte in data:
        result ^= byte << 8
        for _ in range(8):
            if result & 0x8000:
                result = ((result << 1) ^ poly) & 0xFFFF
            else:
                result = (result << 1) & 0xFFFF
    return format(result, "04X")


def _campo(id_: str, valor: str) -> str:
    """Formata um campo TLV (Tag-Length-Value) do padrão EMV."""
    tamanho = f"{len(valor):02d}"
    return f"{id_}{tamanho}{valor}"


def gerar_payload_pix(
    chave_pix: str,
    nome_recebedor: str,
    cidade_recebedor: str,
    valor: Optional[float] = None,
    txid: str = "***",
    descricao: Optional[str] = None,
) -> str:
    """
    Monta o payload Pix estático (texto que vira o QR Code).

    - chave_pix: CPF, celular, e-mail ou chave aleatória do usuário.
    - nome_recebedor: até 25 caracteres, sem acento (regra do BACEN).
    - cidade_recebedor: até 15 caracteres, sem acento.
    - valor: se None, o QR Code fica "em aberto" (quem paga digita o
      valor); se definido, o valor já vem preenchido no app do banco.
    - txid: identificador da transação (ex: id da assinatura), até 25
      caracteres alfanuméricos, sem espaço. "***" = sem identificação.
    """
    nome_recebedor = nome_recebedor[:25]
    cidade_recebedor = cidade_recebedor[:15]

    merchant_account = (
        _campo("00", "br.gov.bcb.pix")
        + _campo("01", chave_pix)
        + (_campo("02", descricao[:40]) if descricao else "")
    )

    campos = (
        _campo("00", "01")                              # Payload Format Indicator
        + _campo("26", merchant_account)                  # Merchant Account Info (Pix)
        + _campo("52", "0000")                             # Merchant Category Code
        + _campo("53", "986")                              # Moeda: Real (BRL)
        + (_campo("54", f"{valor:.2f}") if valor else "")  # Valor (opcional)
        + _campo("58", "BR")                               # País
        + _campo("59", nome_recebedor)                     # Nome do recebedor
        + _campo("60", cidade_recebedor)                   # Cidade do recebedor
        + _campo("62", _campo("05", txid))                 # Additional Data (txid)
    )

    payload_sem_crc = campos + "6304"
    crc = _crc16_ccitt(payload_sem_crc)
    return payload_sem_crc + crc


# ---------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------

@router.post("/gerar-qrcode")
def gerar_qrcode_pix(
    id_assinatura: int,
    chave_pix: str,
    nome_recebedor: str,
    cidade_recebedor: str,
    db: Session = Depends(get_db),
):
    """
    Gera o payload Pix (texto do QR Code) para pagar a assinatura
    indicada. O front-end (ou o próprio Postman/navegador, para o
    teste de hoje) transforma esse texto em imagem de QR Code — veja
    GUIA_PIX_TESTE.md para como fazer isso em 1 minuto, sem instalar
    nada no servidor.
    """
    assinatura = db.get(models.Assinatura, id_assinatura)
    if not assinatura:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada.")

    plano = db.get(models.Plano, assinatura.id_plano)

    payload = gerar_payload_pix(
        chave_pix=chave_pix,
        nome_recebedor=nome_recebedor,
        cidade_recebedor=cidade_recebedor,
        valor=float(plano.valor) if plano else None,
        txid=f"ASS{id_assinatura}",
        descricao="Mensalidade Cuidado Puro",
    )

    return {
        "id_assinatura": id_assinatura,
        "valor": float(plano.valor) if plano else None,
        "payload_pix": payload,
        "instrucao": "Cole este texto em um gerador de QR Code (ex: qrcode-monkey.com) "
                      "ou use o endpoint /pagamento/gerar-qrcode-imagem para já receber a imagem pronta.",
    }


@router.get("/gerar-qrcode-imagem")
def gerar_qrcode_pix_imagem(
    id_assinatura: int,
    chave_pix: str,
    nome_recebedor: str,
    cidade_recebedor: str,
    db: Session = Depends(get_db),
):
    """
    Igual a /gerar-qrcode, mas já devolve a imagem PNG do QR Code
    pronta pra escanear com o app do banco — ideal pra mostrar na
    tela durante a apresentação.
    """
    import qrcode

    assinatura = db.get(models.Assinatura, id_assinatura)
    if not assinatura:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada.")

    plano = db.get(models.Plano, assinatura.id_plano)

    payload = gerar_payload_pix(
        chave_pix=chave_pix,
        nome_recebedor=nome_recebedor,
        cidade_recebedor=cidade_recebedor,
        valor=float(plano.valor) if plano else None,
        txid=f"ASS{id_assinatura}",
        descricao="Mensalidade Cuidado Puro",
    )

    img = qrcode.make(payload)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="image/png")


@router.post("/confirmar")
def confirmar_pagamento(
    dados: schemas.ConfirmarPagamentoRequest,
    db: Session = Depends(get_db),
):
    """
    Confirmação MANUAL de que o Pix caiu (sem webhook automático de
    banco, que exige integração paga). Para a demonstração: depois de
    pagar o QR Code de verdade, chame este endpoint pra marcar a
    assinatura como paga em tempo real, na frente da banca.
    """
    assinatura = db.get(models.Assinatura, dados.id_assinatura)
    if not assinatura:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada.")

    assinatura.status_pagamento = "pago"
    assinatura.data_pagamento = datetime.utcnow()
    db.commit()
    db.refresh(assinatura)

    return {
        "mensagem": "Pagamento confirmado com sucesso.",
        "id_assinatura": assinatura.id_assinatura,
        "status_pagamento": assinatura.status_pagamento,
        "data_pagamento": assinatura.data_pagamento,
    }
