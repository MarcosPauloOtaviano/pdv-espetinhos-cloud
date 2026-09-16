import QRCode from "qrcode";

function emvField(id, value) {
  const text = String(value ?? "");
  return `${id}${String(text.length).padStart(2, "0")}${text}`;
}

function sanitize(text, maxLen) {
  const clean = String(text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Za-z0-9 ]/g, "")
    .trim()
    .toUpperCase();
  return (clean || "NAO INFORMADO").slice(0, maxLen);
}

function crc16(payload) {
  let crc = 0xffff;
  for (let i = 0; i < payload.length; i += 1) {
    crc ^= payload.charCodeAt(i) << 8;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
  }
  return crc.toString(16).toUpperCase().padStart(4, "0");
}

export function buildPixPayload({
  pixKey,
  merchantName,
  merchantCity,
  amount,
  description = "",
  txid = "***",
}) {
  if (!pixKey) throw new Error("Chave Pix nao configurada.");
  const merchantAccount =
    emvField("00", "BR.GOV.BCB.PIX") +
    emvField("01", pixKey) +
    (description ? emvField("02", String(description).slice(0, 40)) : "");
  const cleanTxid = String(txid || "***").replace(/[^A-Za-z0-9]/g, "") || "***";
  const payload =
    emvField("00", "01") +
    emvField("01", "12") +
    emvField("26", merchantAccount) +
    emvField("52", "0000") +
    emvField("53", "986") +
    emvField("54", Number(amount || 0).toFixed(2)) +
    emvField("58", "BR") +
    emvField("59", sanitize(merchantName, 25)) +
    emvField("60", sanitize(merchantCity, 15)) +
    emvField("62", emvField("05", cleanTxid.slice(0, 25)));
  const withCrcMarker = `${payload}6304`;
  return `${withCrcMarker}${crc16(withCrcMarker)}`;
}

export async function pixQrDataUrl(payload) {
  return QRCode.toDataURL(payload, { margin: 2, width: 260 });
}
