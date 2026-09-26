import React, { useEffect, useState } from 'react';
import { supabase } from './lib/supabase';
import { dateTime } from './lib/format';

export default function CustomerAccess({ commandId }) {
  const [access, setAccess] = useState(null);
  const [qr, setQr] = useState('');
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const url = access?.active ? `${window.location.origin}/#/comanda/${access.token}` : '';

  useEffect(() => {
    let current = true;
    setAccess(null); setVisible(false); setError('');
    supabase.rpc('manage_command_access', { p_command_id: commandId, p_action: 'get' }).then(({ data, error: err }) => {
      if (!current) return;
      if (err) setError('Não foi possível consultar o acesso. Tente novamente.');
      else setAccess(data);
    });
    return () => { current = false; };
  }, [commandId]);

  useEffect(() => {
    let current = true;
    setQr('');
    if (url) import('qrcode').then(({ default: QRCode }) => QRCode.toDataURL(url, { width: 320, margin: 3 })).then((image) => { if (current) setQr(image); })
      .catch(() => { if (current) setError('Não foi possível desenhar o QR Code. Use o link abaixo.'); });
    return () => { current = false; };
  }, [url]);

  async function manage(action) {
    if (busy) return;
    if (action === 'generate' && access?.active && !window.confirm('Gerar um novo QR Code? O acesso anterior deixará de funcionar. Os pedidos serão mantidos.')) return;
    if (action === 'revoke' && !window.confirm('Revogar o acesso do cliente? A comanda e os pedidos serão mantidos.')) return;
    setBusy(true); setError(''); setCopied(false);
    try {
      const { data, error: err } = await supabase.rpc('manage_command_access', { p_command_id: commandId, p_action: action });
      if (err) throw err;
      setAccess(data);
      setVisible(action !== 'revoke');
    } catch (err) { setError(err.message || 'Não foi possível atualizar o acesso.'); }
    finally { setBusy(false); }
  }

  return <section className="panel customer-access" aria-label="Acesso do cliente">
    <div className="row"><h2>Acesso do cliente</h2><span className={`pill ${access?.active ? 'good' : ''}`}>{access?.status || 'Consultando…'}</span></div>
    <p>Mostre o QR Code na mesa. O cliente acompanha esta comanda e faz novos pedidos pelo celular, sem cadastro.</p>
    <div className="button-row">
      {access?.active && <button className="primary" disabled={busy} onClick={() => manage('get')}>Mostrar QR Code</button>}
      <button className={access?.active ? 'neutral' : 'primary'} disabled={busy} onClick={() => manage('generate')}>{busy ? 'Aguarde…' : access?.active ? 'Gerar novo QR Code' : 'Gerar acesso do cliente'}</button>
      {access?.active && <button className="danger" disabled={busy} onClick={() => manage('revoke')}>Revogar acesso</button>}
    </div>
    {error && <p className="warning" role="alert">{error}</p>}
    {visible && access?.active && <div className="access-preview">
      {qr && <img src={qr} width="320" height="320" alt="QR Code para o cliente acessar esta comanda" />}
      <strong>Escaneie para acessar sua comanda</strong>
      <p>Válido até {dateTime(access.expires_at)} ou até a comanda ser encerrada.</p>
      <div className="button-row"><a className="access-link" href={url} target="_blank" rel="noopener noreferrer">Abrir comanda do cliente</a>
        <button className="neutral" onClick={async () => { try { await navigator.clipboard.writeText(url); setCopied(true); } catch { setError('Copie o link no campo abaixo.'); } }}>{copied ? 'Link copiado' : 'Copiar link'}</button></div>
      <input aria-label="Link da comanda do cliente" value={url} readOnly onFocus={(event) => event.target.select()} />
      <small>Quem possui este link pode acessar a comanda. Compartilhe somente com os clientes desta mesa.</small>
    </div>}
  </section>;
}
