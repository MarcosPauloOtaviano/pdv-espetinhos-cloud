import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createClient } from '@supabase/supabase-js';
import { supabaseUrl, supabasePublishableKey } from './lib/supabase';
import { currency } from './lib/format';

// Do not reuse a staff JWT, even when the attendant previews the customer link.
const customerClient = supabaseUrl && supabasePublishableKey ? createClient(supabaseUrl, supabasePublishableKey, {
  auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false, storageKey: 'pdv-customer' },
}) : null;
const statusLabel = { pendente: 'Na fila', preparando: 'Em preparo', pronto: 'Pronto', entregue: 'Entregue' };

export default function CustomerApp({ token }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [fatal, setFatal] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [cart, setCart] = useState({});
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [refreshing, setRefreshing] = useState(true);
  const sending = useRef(false);
  const pending = useRef(null);
  const requestStorage = `pdv-customer-request:${token}`;

  const refresh = useCallback(async () => {
    if (!customerClient) { setError('Serviço indisponível. Chame o atendente.'); setRefreshing(false); return; }
    const { data: next, error: err } = await customerClient.rpc('customer_command', { p_token: token });
    if (err) {
      if (err.code === 'P0001') { setFatal(true); setData(null); setCart({}); }
      setError(err.code === 'P0001' ? err.message : 'Não foi possível atualizar. Verifique sua conexão e tente novamente.');
    } else { setData(next); setFatal(false); setError(''); }
    setRefreshing(false);
  }, [token]);

  useEffect(() => {
    let stopped = false;
    let timer;
    const poll = async () => {
      await refresh();
      if (!stopped) timer = window.setTimeout(poll, document.hidden ? 30000 : 5000);
    };
    poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [refresh]);

  const products = data?.products || [];
  const categories = [...new Set(products.map((p) => p.category || 'Outros'))];
  const selected = Object.entries(cart).filter(([, item]) => item.quantity > 0);
  const cartTotal = selected.reduce((sum, [id, item]) => sum + Number(products.find((p) => p.id === id)?.price || 0) * item.quantity, 0);
  const editable = data?.command?.status === 'aberto' && !fatal;

  function changeItem(id, quantity) {
    setCart((current) => ({ ...current, [id]: { ...current[id], quantity: Math.min(50, Math.max(0, quantity)) } }));
  }

  async function submit(type) {
    if (sending.current || fatal || !data) return;
    const items = type === 'pedido_digital' ? selected.map(([id, item]) => ({ product_id: id, quantity: item.quantity, notes: item.notes || '' })) : [];
    if (type === 'pedido_digital' && !items.length) return;
    if (type === 'solicitar_fechamento' && !window.confirm('Solicitar o fechamento? Para novos pedidos depois disso, será necessário chamar o atendente.')) return;
    sending.current = true; setBusy(true); setError(''); setMessage('');
    const signature = JSON.stringify({ type, items });
    try {
      if (!pending.current) { try { pending.current = JSON.parse(sessionStorage.getItem(requestStorage)); } catch { /* storage is optional */ } }
      if (pending.current?.signature !== signature) pending.current = { signature, id: crypto.randomUUID() };
      try { sessionStorage.setItem(requestStorage, JSON.stringify(pending.current)); } catch { /* storage is optional */ }
      const { error: err } = await customerClient.rpc('customer_request', {
        p_token: token, p_request_id: pending.current.id, p_type: type, p_items: items,
      });
      if (err) throw err;
      pending.current = null;
      try { sessionStorage.removeItem(requestStorage); } catch { /* storage is optional */ }
      if (type === 'pedido_digital') setCart({});
      setMessage(type === 'pedido_digital' ? 'Pedido enviado! Ele já entrou na fila de atendimento.' : type === 'chamar_garcom' ? 'Atendente chamado. Sua solicitação está na fila.' : 'Fechamento solicitado. Aguarde o atendente.');
      await refresh();
    } catch (err) { setError(err.code === 'P0001' ? err.message : 'Não foi possível confirmar o envio. Tente novamente; o mesmo pedido não será duplicado.'); }
    finally { sending.current = false; setBusy(false); }
  }

  if (!data) return <main className="customer-shell"><section className="panel customer-welcome">
    <span className="eyebrow">Sua comanda</span><h1>{refreshing ? 'Abrindo sua comanda…' : 'Vamos chamar o atendente?'}</h1>
    {error && <p role="alert">{error}</p>}
    {!refreshing && <button className="primary" onClick={refresh}>Tentar novamente</button>}
    <p>Use o QR Code fornecido pela equipe da sua mesa.</p>
  </section></main>;

  const c = data.command;
  const queued = data.requests.filter((r) => ['pendente', 'em_atendimento'].includes(r.status));
  return <main className="customer-shell" style={{ '--orange': data.establishment.primary_color || '#a85a2a', backgroundColor: data.establishment.background_color || '#f6f2ec' }}>
    <header className="customer-header"><span className="eyebrow">Bem-vindo à sua mesa</span>
      <h1>{data.establishment.name}</h1><p>Comanda #{String(c.number).padStart(4, '0')}{c.table_ref ? ` · Mesa ${c.table_ref}` : ''}{c.customer_name ? ` · ${c.customer_name}` : ''}</p>
    </header>
    {error && <div className="warning" role="alert">{error}</div>}
    {message && <div className="customer-notice" role="status">{message}</div>}
    <section className="panel customer-summary">
      <div className="row"><div><span className="eyebrow">Total da comanda</span><strong className="customer-total">{currency(c.total)}</strong></div><span className="pill">{editable ? 'Aberta' : 'Fechamento solicitado'}</span></div>
      {Number(c.discount) > 0 && <p>Subtotal {currency(c.subtotal)} · Desconto {currency(c.discount)}</p>}
      <p>O total inclui os pedidos feitos com o atendente e pelo celular.</p>
      <div className="button-row"><button className="neutral" disabled={busy || queued.some((r) => r.type === 'chamar_garcom')} onClick={() => submit('chamar_garcom')}>Chamar atendente</button>
        <button className="neutral" disabled={busy || !editable} onClick={() => submit('solicitar_fechamento')}>Pedir fechamento</button></div>
      {queued.length > 0 && <small>{queued.length} solicitação(ões) aguardando ou em atendimento.</small>}
    </section>
    <section className="panel"><h2>O que já pedimos</h2>
      {!data.items.length && <p>Ainda não há itens na comanda.</p>}
      {data.items.map((item) => <div className="customer-order-line" key={item.id}>
        <div><strong>{Number(item.quantity)} × {item.name}</strong>{item.notes && <small>{item.notes}</small>}<small>{statusLabel[item.status] || item.status}</small></div><strong>{currency(item.subtotal)}</strong>
      </div>)}
    </section>
    {editable && <section className="panel"><span className="eyebrow">Mais um pedido?</span><h2>Cardápio da casa</h2>
      <div className="form-grid"><input aria-label="Buscar no cardápio" placeholder="O que você gostaria de pedir?" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select aria-label="Categoria do cardápio" value={category} onChange={(e) => setCategory(e.target.value)}><option value="">Todas as categorias</option>{categories.map((name) => <option key={name}>{name}</option>)}</select></div>
      <div className="customer-menu">{products.filter((p) => (!category || (p.category || 'Outros') === category) && p.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map((p) => {
        const count = cart[p.id]?.quantity || 0;
        return <article className="customer-product" key={p.id}><div><small>{p.category || 'Da casa'}</small><h3>{p.name}</h3><strong>{currency(p.price)}</strong></div>
          <div className="qty"><button aria-label={`Diminuir ${p.name}`} disabled={busy || !count} onClick={() => changeItem(p.id, count - 1)}>−</button><span aria-live="polite">{count}</span><button aria-label={`Adicionar ${p.name}`} disabled={busy || !p.available || count >= 50} onClick={() => changeItem(p.id, count + 1)}>+</button></div>
          {!p.available && <small>Indisponível no momento</small>}
          {count > 0 && <input maxLength="300" disabled={busy} aria-label={`Observação para ${p.name}`} placeholder="Observação: sem cebola, por exemplo" value={cart[p.id]?.notes || ''} onChange={(e) => setCart((current) => ({ ...current, [p.id]: { ...current[p.id], notes: e.target.value } }))} />}
        </article>;
      })}</div>
      {!products.length && <p>O cardápio está sendo preparado. Chame o atendente para fazer seu pedido.</p>}
    </section>}
    {editable && selected.length > 0 && <section className="customer-cart" aria-label="Novo pedido"><div><strong>Novo pedido · {currency(cartTotal)}</strong><small>{selected.reduce((sum, [, item]) => sum + item.quantity, 0)} item(ns) selecionado(s)</small></div><button className="primary" disabled={busy} onClick={() => submit('pedido_digital')}>{busy ? 'Enviando…' : 'Enviar pedido'}</button></section>}
    <footer className="customer-footer">Atualização automática · Pagamento com o atendente</footer>
  </main>;
}
