"""
Geracao de Pix estatico no padrao EMV (BR Code), com CRC16-CCITT.
Preparado para no futuro ser substituido por integracao com API
(Mercado Pago, Asaas, Gerencianet, PagSeguro) sem mudar a interface
publica: build_pix_payload() / generate_qr_image().
"""
import re
import unicodedata
import io

import qrcode


def _emv_field(field_id: str, value: str) -> str:
    length = f"{len(value):02d}"
    return f"{field_id}{length}{value}"


def _sanitize(text: str, max_len: int) -> str:
    if not text:
        text = ""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9 ]", "", normalized).strip().upper()
    return normalized[:max_len] if normalized else "NAO INFORMADO"


def _crc16_ccitt(payload: str) -> str:
    """CRC16-CCITT (falso), poly 0x1021, init 0xFFFF - padrao usado pelo Bacen no Pix."""
    poly = 0x1021
    crc = 0xFFFF
    data = payload.encode("utf-8")
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def build_pix_payload(pix_key: str, merchant_name: str, merchant_city: str,
                       amount: float, description: str = "", txid: str = "***") -> str:
    """Monta o BR Code (copia-e-cola) do Pix estatico, com valor fixo e CRC16 no final."""
    if not pix_key:
        raise ValueError("Chave Pix nao configurada. Configure em Configuracoes > Pix.")

    merchant_account_info = (
        _emv_field("00", "BR.GOV.BCB.PIX")
        + _emv_field("01", pix_key)
        + (_emv_field("02", description[:40]) if description else "")
    )

    txid_clean = re.sub(r"[^A-Za-z0-9]", "", txid or "***") or "***"

    payload = (
        _emv_field("00", "01")
        + _emv_field("01", "12")
        + _emv_field("26", merchant_account_info)
        + _emv_field("52", "0000")
        + _emv_field("53", "986")
        + _emv_field("54", f"{amount:.2f}")
        + _emv_field("58", "BR")
        + _emv_field("59", _sanitize(merchant_name, 25))
        + _emv_field("60", _sanitize(merchant_city, 15))
        + _emv_field("62", _emv_field("05", txid_clean[:25]))
    )

    payload_for_crc = payload + "6304"
    crc = _crc16_ccitt(payload_for_crc)
    return payload_for_crc + crc


def generate_qr_image(payload: str):
    """Retorna um objeto PIL.Image com o QR Code do payload Pix."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def generate_qr_bytes(payload: str) -> bytes:
    img = generate_qr_image(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
