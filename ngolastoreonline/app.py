from flask import Flask, render_template_string, request, redirect, session
import sqlite3, os, random
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "ngola-store-2026"
DB = "ngola.db"
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED = {"png","jpg","jpeg","webp","pdf"}

def limpar_tel(t):
    if not t: return ""
    return "".join([c for c in str(t) if c.isdigit()])
def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c
def init():
    c = db()
    c.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, foto TEXT DEFAULT '', telefone_ligacao TEXT, telefone_whatsapp TEXT, provincia TEXT, municipio TEXT, bairro TEXT, nome_loja TEXT, gps_lat TEXT, gps_lng TEXT, role TEXT, senha TEXT, bloqueado INTEGER DEFAULT 0, pago INTEGER DEFAULT 0, aviso INTEGER DEFAULT 0, rotulo TEXT DEFAULT '', data_pago TEXT DEFAULT '', meses_pagos INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS produtos(id INTEGER PRIMARY KEY AUTOINCREMENT, parceiro_id INTEGER, nome_loja TEXT, nome_produto TEXT, tipo TEXT, preco REAL, stock INTEGER, provincia TEXT, municipio TEXT, bairro TEXT, gps_lat TEXT, gps_lng TEXT, foto TEXT, status TEXT DEFAULT 'pendente', motivo TEXT DEFAULT '', criado_em TEXT, reabastecido INTEGER DEFAULT 0, esgotado_manual INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS encomendas(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, cliente_nome TEXT, cliente_telefone TEXT, produto_id INTEGER, produto_nome TEXT, parceiro_id INTEGER, nome_loja TEXT, preco REAL, qtd INTEGER DEFAULT 1, pagamento TEXT, metodo_pagamento TEXT, provincia TEXT, bairro TEXT, data TEXT, data_finalizada TEXT DEFAULT '', status_encomenda TEXT DEFAULT 'Solicitada', cancelado_por TEXT DEFAULT '', vista_parceiro INTEGER DEFAULT 0, reclamacao TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS avisos(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, produto_id INTEGER, provincia TEXT, ordem INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS comentarios(id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INTEGER, parceiro_id INTEGER, cliente_id INTEGER, cliente_nome TEXT, estrelas INTEGER DEFAULT 5, texto TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mensagens(id INTEGER PRIMARY KEY AUTOINCREMENT, de_id INTEGER, para_id INTEGER, texto TEXT, data TEXT, ficheiro TEXT DEFAULT '', lida INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS anuncios(id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, descricao TEXT, foto TEXT, link_site TEXT, whatsapp TEXT, tem_site INTEGER DEFAULT 0, bloqueado INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notificacoes(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, texto TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS telefones_bloqueados(telefone TEXT PRIMARY KEY, motivo TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS denuncias(id INTEGER PRIMARY KEY AUTOINCREMENT, parceiro_id INTEGER, parceiro_nome TEXT, cliente_id INTEGER, cliente_nome TEXT, motivo TEXT, data TEXT, vista INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS avisos_cliente(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, texto TEXT, de_nome TEXT, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pedidos_senha(id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, telefone TEXT, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico_qtd(id INTEGER PRIMARY KEY AUTOINCREMENT, encomenda_id INTEGER, texto TEXT, data TEXT)''')
    for sql in ["ALTER TABLE users ADD COLUMN foto TEXT DEFAULT ''","ALTER TABLE users ADD COLUMN data_pago TEXT DEFAULT ''","ALTER TABLE users ADD COLUMN meses_pagos INTEGER DEFAULT 0","ALTER TABLE encomendas ADD COLUMN vista_parceiro INTEGER DEFAULT 0","ALTER TABLE encomendas ADD COLUMN reclamacao TEXT DEFAULT ''","ALTER TABLE encomendas ADD COLUMN data_finalizada TEXT DEFAULT ''","ALTER TABLE denuncias ADD COLUMN vista INTEGER DEFAULT 0"]:
        try: c.execute(sql)
        except: pass
    if not c.execute("SELECT * FROM users WHERE telefone_ligacao='900000000'").fetchone():
        c.execute("INSERT INTO users (nome, telefone_ligacao, telefone_whatsapp, role, senha, provincia) VALUES (?,?,?,?,?,?)",("Admin Ngola","900000000","900000000","admin","admin123","Luanda"))
    c.commit(); c.close()
init()

def notificar(uid, txt):
    try:
        c=db(); c.execute("INSERT INTO notificacoes(user_id,texto) VALUES(?,?)",(uid,txt)); c.commit(); c.close()
    except: pass
def media_estrelas(pid):
    try:
        c=db(); r=c.execute("SELECT AVG(estrelas) m, COUNT(*) co FROM comentarios WHERE parceiro_id=?",(pid,)).fetchone(); c.close(); return (round(r["m"] or 0,1), r["co"] or 0)
    except: return (0,0)
def stars(n):
    n=int(round(n or 0)); return "⭐"*n + "☆"*(5-n)
def ponto_status(u):
    if u["bloqueado"]: return "🔴"
    if u["aviso"]: return "🟡"
    if u["pago"]: return "🟢"
    return "🟡"

def info_mensalidade(u):
    meses = int(u.get("meses_pagos") or 0) if isinstance(u, dict) else int(u["meses_pagos"] or 0)
    pago = u.get("pago") if isinstance(u, dict) else u["pago"]
    data_pago = u.get("data_pago") if isinstance(u, dict) else u["data_pago"]
    if not pago or not data_pago or meses == 0:
        return {"dias_restantes": None, "atraso": 0, "texto": "Não pagou", "categoria": "nao_pago"}
    try:
        dt = datetime.strptime(data_pago, "%Y-%m-%d")
    except:
        return {"dias_restantes": None, "atraso": 0, "texto": "Não pagou", "categoria": "nao_pago"}
    restantes = meses * 30 - (datetime.now() - dt).days
    if restantes >= 0:
        texto = f"Faltam {restantes} dias" if restantes <= 10 else f"Pago - Faltam {restantes} dias"
        return {"dias_restantes": restantes, "atraso": 0, "texto": texto, "categoria": "pago"}
    atraso = abs(restantes)
    return {"dias_restantes": restantes, "atraso": atraso, "texto": f"Estás com {atraso} de atraso", "categoria": "atraso"}

def voltar_para(user):
    if not user: return "/loja"
    if user["role"]=="admin": return "/admin"
    if user["role"]=="parceiro": return "/painel-parceiro"
    return "/loja"
def num_msgs_novas(uid):
    c=db(); n=c.execute("SELECT COUNT(*) FROM mensagens WHERE para_id=? AND lida=0",(uid,)).fetchone()[0]; c.close(); return n
def num_pedidos_senha():
    c=db(); n=c.execute("SELECT COUNT(*) FROM pedidos_senha").fetchone()[0]; c.close(); return n
def num_pendentes():
    c=db(); n=c.execute("SELECT COUNT(*) FROM produtos WHERE status IN ('pendente','reavaliacao','rejeitado')").fetchone()[0]; c.close(); return n
def num_denuncias_novas():
    c=db(); n=c.execute("SELECT COUNT(*) FROM denuncias WHERE vista=0").fetchone()[0]; c.close(); return n
def faturacao(user_id, tipo):
    c=db(); hoje=datetime.now(); col="parceiro_id" if tipo=="parceiro" else "cliente_id"
    def soma(filtro, params): return c.execute(f"SELECT COALESCE(SUM(preco*qtd),0) FROM encomendas WHERE {col}=? AND status_encomenda='Vendida' {filtro}", (user_id,*params)).fetchone()[0]
    dia=soma("AND date(data)=?", (hoje.strftime("%Y-%m-%d"),)); semana=soma("AND date(data)>=?", ((hoje-timedelta(days=hoje.weekday())).strftime("%Y-%m-%d"),)); mes=soma("AND substr(data,1,7)=?", (hoje.strftime("%Y-%m"),)); ano=soma("AND substr(data,1,4)=?", (hoje.strftime("%Y"),)); c.close(); return dia,semana,mes,ano
def pagina_msg(titulo, texto, botao_texto="/loja", botao_label="Voltar à Loja"):
    return render_template_string(CSS + f"<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><div class='container'><div class='card' style='text-align:center'><div class='check'>✅</div><h2>{titulo}</h2><p>{texto}</p><br><a href='{botao_texto}'><button class='btn'>{botao_label}</button></a></div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick=\"sair()\">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p><script>function sair(){{if(confirm('Queres mesmo sair?')){{alert('Volte sempre');window.close();window.location.href='/logout';}}}}function voltar(){{if(window.history.length>1){{window.history.back();}}else{{window.location.href='/loja';}}}}</script>")

CSS = """
<meta name= "viewport" content="width=device-width, initial-scale=1">
<style>
*{box-sizing:border-box;font-family:Arial,sans-serif}body{margin:0;background:#f2f2f2}
a{text-decoration:none!important;color:#111;font-weight:bold}a:hover{opacity:.85}
.topo{background:#111;color:white;padding:14px 16px;position:sticky;top:0;z-index:10;display:flex;justify-content:space-between;align-items:center}
.topo b{font-size:22px}.topo b span{color:#FFCC00}.topo a{color:white!important;font-size:13px}
.btn{background:#CC092F;color:white;border:none;padding:12px 18px;border-radius:10px;font-weight:bold;cursor:pointer;font-size:15px;width:100%}
.btn-amarelo{background:#FFCC00;color:#111;border:none;padding:12px 18px;border-radius:10px;font-weight:bold;cursor:pointer;font-size:15px;width:100%}
.btn-outline{background:white;border:2px solid #111;padding:10px;border-radius:10px;font-weight:bold;width:100%;cursor:pointer}
.btn-peq{padding:6px 10px;border-radius:8px;border:none;font-weight:bold;cursor:pointer;font-size:12px;width:auto}
.link-btn{display:inline-block;background:#111;color:white!important;padding:6px 12px;border-radius:20px;font-size:12px;margin:2px}
.link-btn-amarelo{display:inline-block;background:#FFCC00;color:#111!important;padding:6px 12px;border-radius:20px;font-size:12px;margin:2px}
.link-btn-vermelho{display:inline-block;background:#CC092F;color:white!important;padding:6px 12px;border-radius:20px;font-size:12px;margin:2px}
.container{padding:14px;max-width:950px;margin:auto}.card{background:white;padding:18px;border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,.08);margin-bottom:14px}
input,select{width:100%;padding:12px;border:1px solid #ddd;border-radius:10px;margin:6px 0 12px 0;font-size:15px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.produto{background:white;border-radius:16px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);position:relative}
.produto img{width:100%;height:160px;object-fit:cover;background:#eee}.produto-info{padding:10px}.preco{color:#CC092F;font-weight:bold;font-size:18px;margin:6px 0}
.loja{font-size:12px;color:#666}
.kpi{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}.kpi div{background:#111;color:white;padding:14px;border-radius:12px;text-align:center}.kpi div b{font-size:22px;display:block}.kpi div span{font-size:12px;color:#FFCC00}
.tabs{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}.tabs a{background:white;padding:10px 14px;border-radius:20px;color:#111;font-weight:bold;font-size:13px;border:1px solid #ddd}
.foto-preview{width:100%;height:180px;object-fit:cover;border-radius:12px;background:#eee;display:none}.check{font-size:70px}
.capa-fixa{width:100%;height:180px;object-fit:cover;display:block;position:sticky;top:52px;z-index:9}
.balao-flutuante{position:fixed;bottom:20px;right:20px;background:#111;color:white!important;padding:12px 16px;border-radius:30px;z-index:99}
.badge-msg{background:#CC092F;color:white;border-radius:50%;padding:2px 7px;font-size:11px;margin-left:4px}
.aviso-chat-topo{background:#FFCC00;padding:12px;border-radius:10px;text-align:center;font-weight:bold;position:sticky;top:52px;z-index:10}
.total-grande{font-size:42px;font-weight:bold;text-align:center}.total-peq{display:flex;justify-content:space-between;text-align:center;font-size:12px}
.perfil-foto{width:90px;height:90px;border-radius:50%;object-fit:cover}
.pequeno{font-size:11px;color:#666}.comentario{cursor:pointer}
.chat-input{display:flex;gap:6px;align-items:center}.chat-input input{flex:1}.grampo{font-size:22px;cursor:pointer;background:none;border:none}
@media(max-width:600px){.grid{grid-template-columns:1fr}.topo{flex-wrap:wrap}.topo b{font-size:18px}}
img{max-width:100%;heigh:auto}
.container{padding:10px !important}
.topo{flex-wrap:wrap}
.total-grande{font-size:28px !important}
</style>
<script>
function toggle(id){var e=document.getElementById(id);e.style.display=e.style.display=='none'?'block':'none';}
function toggleComent(id){var e=document.getElementById(id);e.style.display=e.style.display=='none'?'block':'none';}
function sair(){if(confirm('Queres mesmo sair?')){alert('Volte sempre');window.close();window.location.href='/logout';}}
function voltar(){if(window.history.length>1){window.history.back();}else{window.location.href='/loja';}}
</script>
"""

ENTRADA = CSS + "<div class='topo'><b>NGOLA <span>STORE</span></b><a href='/login'>Login</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror=\"this.style.display='none'\"><div class='container'><div class='card' style='text-align:center'><h1>Ngola Store<br>Online 🇦🇴</h1><p>Compra e vende em toda Angola.</p><br><a href='/escolher-tipo'><button class='btn'>Criar Conta</button></a><br><br><a href='/login'><button class='btn-amarelo'>Login</button></a><br><br><a href='/loja?modo=olhada'><button class='btn-outline'>👀 Só dando uma olhada</button></a></div></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>"
ESCOLHER_TIPO = CSS + "<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror=\"this.style.display='none'\"><div class='container'><div class='card' style='text-align:center'><h1>Criar Conta</h1><a href='/cadastro?tipo=cliente'><button class='btn'>🛒 SOU CLIENTE</button></a><br><br><a href='/cadastro?tipo=parceiro'><button class='btn-amarelo'>🏪 SOU PARCEIRO</button></a></div></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>"
CADASTRO = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'><h2>Criar Conta - {{tipo|upper}}</h2>{% if msg %}<p style='background:#2ecc71;color:white;padding:12px;border-radius:10px'>{{msg}}</p>{% endif %}
<form method='post'><input type='hidden' name='role' value='{{tipo}}'><label>Nome</label><input name='nome' required><label>Senha</label><input name='senha' type='password' required>
<label>Província</label><select name='provincia'><option>Luanda</option><option>Benguela</option><option>Huíla</option><option>Huambo</option><option>Cabinda</option><option>Uíge</option><option>Malanje</option><option>Outros</option></select>
<label>Município</label><input name='municipio' required><label>Bairro</label><input name='bairro' required><label>Número</label><input name='tel_lig' required>
<label>Este número está no WhatsApp?</label><br><label><input type='radio' name='tem_whats' value='sim' onclick="document.getElementById('campo_whats').style.display='none'" checked style='width:auto'> Sim</label><label><input type='radio' name='tem_whats' value='nao' onclick="document.getElementById('campo_whats').style.display='block'" style='width:auto'> Não</label><br><br><div id='campo_whats' style='display:none'><input name='tel_whats' placeholder='Teu WhatsApp'></div>
{% if tipo=='parceiro' %}<hr><b>🏪 Dados da Loja</b><br><br><label>Nome da Loja</label><input name='nome_loja' required>{% endif %}<button class='btn'>Criar Conta</button></form></div></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""
LOGIN = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'><h2>Login</h2>{% if erro %}<p style='background:#CC092F;color:white;padding:10px;border-radius:10px'>{{erro}}</p>{% endif %}{% if msg %}<p style='background:#2ecc71;color:white;padding:10px;border-radius:10px'>{{msg}}</p>{% endif %}
<form method='post'><label>Telefone</label><input name='tel' required><label>Senha</label><input name='senha' type='password' required><button class='btn'>Entrar</button></form><br>
<a href='/esqueci-senha'><button type='button' class='btn-outline'>🔑 Esqueci a minha senha</button></a><br><br>
<a href='/loja?modo=olhada'><button type='button' class='btn-outline'>👀 Só dando uma olhada</button></a><br><br><a href='/escolher-tipo'><button type='button' class='btn-amarelo'>Criar Conta</button></a></div></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""
ESQUECI = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'><h2>🔑 Esqueci a minha senha</h2><p>Escreve nome e telefone. O Admin procura e confirma se és o dono.</p><form method='post'><label>Nome</label><input name='nome' required><label>Telefone</label><input name='telefone' required><button class='btn'>Pedir Recuperação</button></form></div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

MEU_PERFIL = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card' style='text-align:center'><h2>👤 Meu Perfil</h2>
{% if user['foto'] %}<img src='/static/uploads/{{user['foto']}}' class='perfil-foto'>{% else %}<div class='perfil-foto' style='background:#eee;display:flex;align-items:center;justify-content:center;margin:auto;font-size:40px'>👤</div>{% endif %}
<h3>{{user['nome']}}</h3>
<div style='display:flex;justify-content:space-around;text-align:center'>
<div><b style='font-size:28px'>{{n_feitas}}</b><br>Encomendas Feitas</div>
<div><b style='font-size:28px'>{{n_canceladas}}</b><br>Canceladas</div>
<div><b style='font-size:28px'>{{total_gasto}} Kz</b><br>Total Gasto</div>
</div><br>
<button class='btn-outline' onclick="toggle('editar_perfil')">Editar Perfil ▼</button>
<div id='editar_perfil' style='display:none'><form method='post' enctype='multipart/form-data'><label>Foto de Perfil</label><input type='file' name='foto' accept='image/*'><label>Nome</label><input name='nome' value="{{user['nome']}}" required><label>Senha</label><input name='senha' value="{{user['senha']}}" required><label>Número</label><input name='telefone' value="{{user['telefone_ligacao']}}" required><button class='btn'>Guardar</button></form></div>
<button class='btn-outline' onclick="toggle('hist_perfil')">Histórico ▼</button>
<div id='hist_perfil' style='display:none'><form>Data: <input type='date' name='data'> <button class='btn'>Procurar</button></form></div>
</div>
<div class='card'><h3>📦 Encomendas Feitas</h3>
{% for e in feitas %}<div style='border-bottom:1px solid #eee;padding:10px 0;display:flex;justify-content:space-between;align-items:center'>
<div><b>{{e['produto_nome']}}</b><br>{{e['nome_loja']}}</div>
<button class='btn-peq' onclick="toggle('info_{{e['id']}}')">Mais informações ▼</button>
<div id='info_{{e['id']}}' style='display:none'>Preço: {{e['preco']*e['qtd']}} Kz<br>{{e['data_finalizada'] or e['data']}}<br><a href='/chat?com={{e['parceiro_id']}}'><button class='btn-peq' style='background:#CC092F;color:white'>Reclamar</button></a></div>
</div>{% endfor %}</div>
</div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online - Todos os direitos reservados</p>
"""

LOJA = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><div>
<a href='/pesquisa-lojas'>🔍</a> |
<a href='/lojas'>🏪 Loja</a> |
<a href='/carrinho'>🛒 Carrinho</a> |
<a href='/chat'>💬 Chat {% if msgs_novas %}<span class='badge-msg'>{{msgs_novas}}</span>{% endif %}</a> |
{% if user %}<a href='/meu-perfil'>👤 Meu Perfil</a> | {% endif %}
{% if user and user['role']=='parceiro' %}<a href='/painel-parceiro'>🏪 Parceiro</a> | {% endif %}
{% if user and user['role']=='admin' %}<a href='/admin'>⚙️ Opções de Administrador</a> | {% endif %}
<a href='javascript:voltar()'>⬅ Voltar</a></div></div>
<img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'>
{% if mostrar_todos %}<div class='tabs'><a href='/loja'>Todos</a></div>{% endif %}
<div class='tabs'><a href='/loja?filtro=novos'>✨ Novos</a><a href='/loja?filtro=reabastecidos'>🔄 Reabastecidos</a><a href='/lojas'>🏪 Loja</a></div>
<div class='grid'>
{% for p in prods %}
{% if anuncios and loop.index in pos_anuncio %}
{% set a = anuncios|random %}
<div class='produto'><a href='/anuncio/{{a['id']}}'>{% if a['foto'] %}<img src='/static/uploads/{{a['foto']}}'>{% endif %}<div class='produto-info' style='background:#111;color:white'><b>📢 {{a['titulo']}}</b><br>{{a['descricao']}}</div></a></div>
{% endif %}
<div class='produto'>{% if p['foto'] %}<img src='/static/uploads/{{p['foto']}}'>{% else %}<img src='https://via.placeholder.com/400x300?text=Ngola+Store'>{% endif %}
<div class='produto-info'><b>{{p['nome_produto']}}</b><div class='preco'>{{p['preco']}} Kz</div><div class='loja'>🏪 {{p['nome_loja']}} {{p['estrelas_txt']}}<br>📍 {{p['provincia']}} - {{p['bairro']}} | Stock: {{p['stock']}}</div>
<a target='_blank' href='https://www.google.com/maps/search/?api=1&query={{p['gps_lat']}},{{p['gps_lng']}}' class='link-btn'>📍 Ver no Maps</a><br>
<a href='/produto/{{p['id']}}' class='link-btn-amarelo'>⭐ Ver / Comentar</a> <a href='/chat?com={{p['parceiro_id']}}' class='link-btn'>💬 Falar com a Loja</a><br><br>
{% if not p['bloqueado'] and not p['esgotado_manual'] and p['stock']>0 %}
<form action='/add-carrinho/{{p['id']}}' method='post'><button class='btn-amarelo'>🛒 Adicionar ao Carrinho</button></form>
<form action='/encomendar/{{p['id']}}' method='post' style='margin-top:6px'><select name='pagamento'><option>Presencial</option><option>Multicaixa Express / Transferência</option></select><button class='btn'>Encomendar Agora</button></form>
{% else %}
<p style='color:#CC092F;font-weight:bold'>Produto Esgotado</p>
<form action='/avise-me/{{p['id']}}' method='post'><button class='btn-amarelo'>🔔 Avise-me quando abastecerem</button></form>
{% endif %}
</div></div>{% endfor %}</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

PESQUISA_LOJAS = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'><h2>🔍</h2><form><input name='q' placeholder='Pesquisar...' value='{{q}}'><button class='btn'>Pesquisar</button></form>
{% for l in top_lojas %}<a href='/loja-da-loja/{{l['parceiro_id']}}'><div style='border:1px solid #eee;padding:10px;border-radius:10px;margin:6px 0'>🏪 {{l['nome_loja']}} - {{l['estrelas_txt']}}</div></a>{% endfor %}
</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

LOJAS_LISTA = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'><h2>🏪 Todas as Lojas</h2>
{% for l in lojas %}<a href='/loja-da-loja/{{l['parceiro_id']}}'><div style='border:1px solid #eee;padding:12px;border-radius:12px;margin:8px 0'><b>{{l['ponto']}} {{l['nome_loja']}}</b> - {{l['nome']}} - {{l['estrelas_txt']}}<br>📍 {{l['provincia']}} - {{l['bairro']}}</div></a>{% endfor %}
</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

ADD_PRODUTO = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'><h2>Adicionar Produto</h2>
<form method='post' enctype='multipart/form-data'><label>Nome do Produto</label><input name='nome_produto' required><label>Tipo</label><input name='tipo'><label>Preço</label><input name='preco' type='number' required><label>Stock</label><input name='stock' type='number' required>
<label>📸 Foto</label><input type='file' name='foto' accept='image/*' onchange="preview(this)" required><img id='preview' class='foto-preview'>
<button class='btn' type='button' onclick="document.getElementById('inquerito').style.display='block';this.style.display='none'">Enviar para Aprovação</button>
<div id='inquerito' style='display:none;border:2px solid #FFCC00;padding:14px;border-radius:12px;margin-top:10px'>
<p><b>Publicar usando dados existentes ou pretende mudar informações?</b></p>
<label><input type='radio' name='usar_existentes' value='sim' checked style='width:auto' onclick="document.getElementById('novos_dados').style.display='none'"> Publicar usando dados existentes</label><br>
<label><input type='radio' name='usar_existentes' value='nao' style='width:auto' onclick="document.getElementById('novos_dados').style.display='block'"> Pretende mudar informações</label><br>
<div id='novos_dados' style='display:none'><label>Novo nome da loja?</label><input name='nome_loja'><label>Nova localização</label><input name='bairro'><input name='municipio' placeholder='Município'><input name='provincia' placeholder='Província'><label>Novo telefone</label><input name='novo_tel_lig'><label>Novo WhatsApp</label><input name='novo_tel_whats'><button type='button' class='btn-amarelo' onclick="usarLocalizacao()">📍 Usar localização atual</button><input type='hidden' name='gps_lat' id='gps_lat'><input type='hidden' name='gps_lng' id='gps_lng'><p id='gps_ok'></p></div>
<label>Como publicar?</label><select name='alcance_alteracao'><option value='so_produto'>Publicar direto</option><option value='novos_dados_loja'>Atualizar os dados da loja</option></select>
<button class='btn' type='submit'>Publicar</button></div></form></div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
<script>function preview(i){if(i.files&&i.files[0]){var r=new FileReader();r.onload=function(e){var im=document.getElementById('preview');im.src=e.target.result;im.style.display='block'};r.readAsDataURL(i.files[0]);}}function usarLocalizacao(){navigator.geolocation.getCurrentPosition(function(p){document.getElementById('gps_lat').value=p.coords.latitude;document.getElementById('gps_lng').value=p.coords.longitude;document.getElementById('gps_ok').innerText='✅ Marcado!';})}</script>
"""

CARRINHO = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><div><a href='/chat'>💬 Chat {% if msgs_novas %}<span class='badge-msg'>{{msgs_novas}}</span>{% endif %}</a> | <a href='javascript:voltar()'>⬅ Voltar</a></div></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'><h2>🛒 Carrinho</h2>
<div class='tabs'><a href='#' onclick="document.getElementById('c_pend').style.display='block';document.getElementById('c_aceit').style.display='none';return false">Pedidos Pendentes</a><a href='#' onclick="document.getElementById('c_pend').style.display='none';document.getElementById('c_aceit').style.display='block';return false">Pedidos Aceites</a></div>
<div id='c_pend'>
{% for it in itens %}<div style='border-bottom:1px solid #eee;padding:10px 0'><b>{{it['nome_produto']}}</b><br>Quantidade: {{it['qtd']}}<br>Total: <b>{{it['preco']*it['qtd']}} Kz</b><br><a href='/carrinho-menos/{{it['id']}}' class='link-btn'>-</a> <a href='/carrinho-mais/{{it['id']}}' class='link-btn'>+</a> <a href='/remover-carrinho/{{it['id']}}' class='link-btn-vermelho'>Remover</a></div>{% endfor %}
{% for e in encomendas %}{% if e['status_encomenda']=='Solicitada' %}<div style='border-bottom:1px solid #eee;padding:10px 0'><b>{{e['produto_nome']}}</b><br>Quantidade: {{e['qtd']}}<br>Total: <b>{{e['preco']*e['qtd']}} Kz</b><br><a href='/cancelar-encomenda/{{e['id']}}'><button class='btn-peq' style='background:#CC092F;color:white'>Cancelar</button></a></div>{% endif %}{% endfor %}
{% if itens %}<h3>Total: {{total}} Kz</h3><form action='/finalizar-carrinho' method='post'><select name='metodo_pagamento'><option value='Pagar Agora'>💳 Pagar Agora</option><option value='Pagar na Entrega'>💵 Pagar na Entrega</option></select><select name='pagamento'><option>Presencial</option><option>Multicaixa Express / Transferência</option></select><button class='btn'>✅ Finalizar Encomenda - {{total}} Kz</button></form>{% endif %}
</div>
<div id='c_aceit' style='display:none'>
{% for e in encomendas %}{% if e['status_encomenda']=='Pedido Aceito' %}<div style='border-bottom:1px solid #eee;padding:10px 0'><b>{{e['produto_nome']}}</b><br>Quantidade: {{e['qtd']}}<br>Total: <b>{{e['preco']*e['qtd']}} Kz</b><br><a href='/cancelar-encomenda/{{e['id']}}'><button class='btn-peq' style='background:#CC092F;color:white'>Cancelar</button></a></div>{% endif %}{% endfor %}
</div>
</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

SUCESSO = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card sucesso'><div class='check'>✅</div><h1>Obrigado, {{nome}}!</h1>{% if ultimo %}<p style='background:#FFCC00;padding:12px;border-radius:10px;font-weight:bold'>🎉 Você teve sorte, você comprou o último produto!</p>{% endif %}<p>A tua encomenda foi feita.</p><div style='text-align:left;background:#f9f9f9;padding:14px;border-radius:12px'><b>Resumo:</b><br>{% for it in itens %}• {{it['nome_produto']}} - {{it['preco']}} Kz x {{it['qtd']}}<br>{% endfor %}<hr><b>Total: {{total}} Kz</b><br><b>Pagamento:</b> {{metodo}}<br><b>Estado:</b> Solicitada</div><br><a href='/carrinho'><button class='btn'>Ver no Carrinho</button></a><br><br><a href='/loja'><button class='btn-amarelo'>Continuar a Comprar</button></a></div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

ADMIN = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span> - Painel do Administrador</b><div>
<a href='/chat'>💬 Chat {% if msgs_novas %}<span class='badge-msg'>{{msgs_novas}}</span>{% endif %}</a> |
<a href='/pedidos-senha'>🔑 {% if num_senha %}<span class='badge-msg'>{{num_senha}}</span>{% endif %}</a> |
<a href='/denuncias'>❗ {% if num_denuncias %}<span class='badge-msg'>{{num_denuncias}}</span>{% endif %}</a> |
<a href='/loja'>Loja</a> | <a href='javascript:voltar()'>⬅ Voltar</a></div></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'>
{% if aviso_mensalidade %}<div style='background:#FFCC00;padding:12px;border-radius:10px;text-align:center;font-weight:bold'>⚠️ {{aviso_mensalidade}}</div><br>{% endif %}
<div class='card'><h2>📊 Painel do Administrador</h2><div class='total-grande'>{{total_vendas}} Kz</div><p style='text-align:center'>Total</p></div>
<div class='card'><div class='total-peq'><div><b>{{total_dia}} Kz</b><br>Hoje</div><div><b>{{total_semana}} Kz</b><br>Esta Semana</div><div><b>{{total_mes}} Kz</b><br>Este Mês</div><div><b>{{total_ano}} Kz</b><br>Este Ano</div></div></div>
<div class='card'><div class='kpi'><div><b>{{total_clientes}}</b><span>Clientes</span></div><div><b>{{total_parceiros}}</b><span>Parceiros</span></div><div><b>{{total_encomendas}}</b><span>Encomendas</span></div></div><br><div class='kpi'><div><b>{{total_produtos}}</b><span>Produtos Aprovados</span></div><div><b>{{total_pagos}}</b><span>Parceiros Pagos</span></div><div><b>{{total_canceladas}}</b><span>Canceladas</span></div></div></div>
<div class='card'>
<button class='btn-outline' onclick="toggle('relatorio_box')">📅 Pesquisa por dia ▼</button>
<div id='relatorio_box' style='display:none'><form>Data: <input type='date' name='data' value='{{f_data}}'> <button class='btn'>Procurar</button></form><p>Encomendas: {{rel_total}} | Valor: {{rel_valor}} Kz</p></div>
<button class='btn-outline' onclick="toggle('sec_pendentes')">❓ Ver produtos pendentes que ainda não autorizaste {% if num_pendentes %}<span class='badge-msg'>{{num_pendentes}}</span>{% endif %} ▼</button>
<div id='sec_pendentes' style='display:none'>{% for p in pendentes %}<div style='border:1px solid #eee;padding:10px;border-radius:10px;margin:8px 0'>{% if p['foto'] %}<img src='/static/uploads/{{p['foto']}}' style='width:100%;height:120px;object-fit:cover;border-radius:8px'>{% endif %}<b>{{p['nome_produto']}}</b> - {{p['nome_loja']}} - {{p['preco']}} Kz - {{p['status']}}<br><br><a href='/aprovar/{{p['id']}}'><button class='btn-peq' style='background:#2ecc71;color:white'>✅ Aprovar</button></a><a href='/rejeitar/{{p['id']}}'><button class='btn-peq' style='background:#CC092F;color:white'>❌ Rejeitar</button></a><a href='/reavaliacao/{{p['id']}}'><button class='btn-peq' style='background:#FFCC00'>🔄 Pedir Reavaliação</button></a><form action='/rejeitar-motivo/{{p['id']}}' method='post'><input name='motivo' placeholder='Motivo'><button class='btn-peq'>Enviar Motivo</button></form></div>{% endfor %}</div>
<button class='btn-outline' onclick="toggle('sec_encomendas')">📦 Ver Estado de Encomendas ▼</button>
<div id='sec_encomendas' style='display:none'><h2>📦 Encomendas</h2>
<div class='tabs'><a href='#' onclick="document.getElementById('adm_solic').style.display='block';document.getElementById('adm_conf').style.display='none';document.getElementById('adm_canc').style.display='none';return false">Solicitadas ({{n_solic}})</a><a href='#' onclick="document.getElementById('adm_solic').style.display='none';document.getElementById('adm_conf').style.display='block';document.getElementById('adm_canc').style.display='none';return false">Confirmadas ({{n_conf}})</a><a href='#' onclick="document.getElementById('adm_solic').style.display='none';document.getElementById('adm_conf').style.display='none';document.getElementById('adm_canc').style.display='block';return false">Canceladas ({{n_canc}})</a></div>
<div id='adm_solic'>{% for e in encomendas %}{% if e['status_encomenda']=='Solicitada' %}<div> #{{e['id']}} - {{e['produto_nome']}} x {{e['qtd']}} - Cliente: {{e['cliente_nome']}} - Loja: {{e['nome_loja']}}<br><span class='pequeno'>{{e['data_finalizada'] or '-'}}</span> <button class='btn-peq' onclick="toggle('det_{{e['id']}}')">Mais informações ▼</button><div id='det_{{e['id']}}' style='display:none'>Pagamento: {{e['pagamento']}} - {{e['metodo_pagamento']}}<br>Província: {{e['provincia']}} - Bairro: {{e['bairro']}}<br>Telefone: {{e['cliente_telefone']}}</div></div>{% endif %}{% endfor %}</div>
<div id='adm_conf' style='display:none'>{% for e in encomendas %}{% if e['status_encomenda'] in ['Pedido Aceito','Vendida'] %}<div> {{e['nome_loja']}} - {{e['produto_nome']}} - {{e['cliente_nome']}}<br><span class='pequeno'>{{e['data_finalizada'] or '-'}}</span> <button class='btn-peq' onclick="toggle('det2_{{e['id']}}')">Mais informações ▼</button><div id='det2_{{e['id']}}' style='display:none'>Preço: {{e['preco']*e['qtd']}} Kz - Pagamento: {{e['pagamento']}} - {{e['metodo_pagamento']}}</div></div>{% endif %}{% endfor %}</div>
<div id='adm_canc' style='display:none'>{% for e in encomendas %}{% if e['status_encomenda']=='Cancelada' %}<div> #{{e['id']}} - {{e['produto_nome']}} - Cancelado por: {{e['cancelado_por']}}<br><span class='pequeno'>{{e['data_finalizada'] or '-'}}</span></div>{% endif %}{% endfor %}</div>
</div>
<button class='btn-outline' onclick="toggle('sec_gerir')">👤 Gerir Clientes / Parceiros ▼</button>
<div id='sec_gerir' style='display:none'><p>🔍 Pesquisa</p><input placeholder='Pesquisar nome...' onkeyup="filtrar(this,'lista_gerir')">
<button class='btn-outline' onclick="toggle('lista_clientes')">Clientes ▼</button>
<div id='lista_clientes' style='display:none'><div id='lista_gerir'>{% for u2 in todos_users %}{% if u2['role']=='cliente' %}<div style='border-bottom:1px solid #eee;padding:8px 0'><b>{{u2['nome']}}</b> - {{u2['role']}}<button class='btn-peq' onclick="toggle('mais_{{u2['id']}}')">Ver mais informações ▼</button><div id='mais_{{u2['id']}}' style='display:none'>Telefone: {{u2['telefone_ligacao']}}<br>Província: {{u2['provincia']}} - Bairro: {{u2['bairro']}}<br>Rótulo: {{u2['rotulo'] or ''}}<br><a href='/faturacao/{{u2['role']}}/{{u2['id']}}'><button class='btn-peq' style='background:#111;color:white'>💰 Ver Faturação</button></a><form action='/admin/remover-rotulo/{{u2['id']}}' method='post'><button class='btn-peq'>Remover Rótulo</button></form><form action='/admin/apagar-cliente/{{u2['id']}}' method='post'><button class='btn-peq' style='background:#CC092F;color:white'>Eliminar Conta</button></form></div></div>{% endif %}{% endfor %}</div></div>
<button class='btn-outline' onclick="toggle('lista_parceiros')">Parceiros ▼</button>
<div id='lista_parceiros' style='display:none'>
<div class='tabs'><a href='#' onclick="document.getElementById('parc_pagos').style.display='block';document.getElementById('parc_nao').style.display='none';document.getElementById('parc_avis').style.display='none';return false">Pagos ({{n_pagos}})</a><a href='#' onclick="document.getElementById('parc_pagos').style.display='none';document.getElementById('parc_nao').style.display='block';document.getElementById('parc_avis').style.display='none';return false">Não Pagaram ({{n_nao_pagos}})</a><a href='#' onclick="document.getElementById('parc_pagos').style.display='none';document.getElementById('parc_nao').style.display='none';document.getElementById('parc_avis').style.display='block';return false">Avisados ({{n_avisados}})</a></div>
<div id='parc_pagos'>
{% for u2 in todos_users %}{% if u2['role']=='parceiro' and u2['categoria_mens']=='pago' %}<div style='border-bottom:1px solid #eee;padding:8px 0'><b>🟢 {{u2['nome']}}</b> - {{u2['nome_loja']}} - {{u2['texto_mens']}} - {{u2['meses_pagos']}} mês(es) <button class='btn-peq' onclick="toggle('mais_pago_{{u2['id']}}')">Ver ▼</button><div id='mais_pago_{{u2['id']}}' style='display:none'>Telefone: {{u2['telefone_ligacao']}}<br>Data pago: {{u2['data_pago']}}<br><form action='/admin/marcar-pago/{{u2['id']}}' method='post'><label>Quantos meses pagou?</label><select name='meses'><option value='1'>1 mês - 30 dias</option><option value='2'>2 meses - 60 dias</option><option value='3'>3 meses - 90 dias</option><option value='4'>4 meses - 120 dias</option><option value='5'>5 meses - 150 dias</option><option value='6'>6 meses - 180 dias</option><option value='12'>12 meses - 360 dias</option></select><button class='btn-peq' style='background:#2ecc71;color:white'>Atualizar Pagamento</button></form><a href='/admin/bloquear/{{u2['id']}}'><button class='btn-peq' style='background:#CC092F;color:white'>Bloquear</button></a></div></div>{% endif %}{% endfor %}
</div>
<div id='parc_nao' style='display:none'>
{% for u2 in todos_users %}{% if u2['role']=='parceiro' and u2['categoria_mens'] in ['nao_pago','atraso'] %}<div style='border-bottom:1px solid #eee;padding:8px 0'><b>🔴 {{u2['nome']}}</b> - {{u2['nome_loja']}} - {{u2['texto_mens']}} <button class='btn-peq' onclick="toggle('mais_nao_{{u2['id']}}')">Ver ▼</button><div id='mais_nao_{{u2['id']}}' style='display:none'>Telefone: {{u2['telefone_ligacao']}}<br><form action='/admin/marcar-pago/{{u2['id']}}' method='post'><label>Quantos meses pagou?</label><select name='meses'><option value='1'>1 mês - 30 dias</option><option value='2'>2 meses - 60 dias</option><option value='3'>3 meses - 90 dias</option><option value='4'>4 meses - 120 dias</option><option value='5'>5 meses - 150 dias</option><option value='6'>6 meses - 180 dias</option><option value='12'>12 meses - 360 dias</option></select><button class='btn-peq' style='background:#2ecc71;color:white'>Marcar como Pago</button></form><a href='/admin/avisar/{{u2['id']}}'><button class='btn-peq' style='background:#FFCC00'>Avisar</button></a></div></div>{% endif %}{% endfor %}
</div>
<div id='parc_avis' style='display:none'>
{% for u2 in todos_users %}{% if u2['role']=='parceiro' and u2['aviso'] %}<div style='border-bottom:1px solid #eee;padding:8px 0'><b>🟡 {{u2['nome']}}</b> - {{u2['nome_loja']}} - {{u2['texto_mens']}} <button class='btn-peq' onclick="toggle('mais_av_{{u2['id']}}')">Ver ▼</button><div id='mais_av_{{u2['id']}}' style='display:none'>Telefone: {{u2['telefone_ligacao']}}<br>Data pago: {{u2['data_pago'] or '-'}} - {{u2['meses_pagos']}} mês(es)<br><form action='/admin/marcar-pago/{{u2['id']}}' method='post'><label>Quantos meses pagou?</label><select name='meses'><option value='1'>1 mês - 30 dias</option><option value='2'>2 meses - 60 dias</option><option value='3'>3 meses - 90 dias</option><option value='4'>4 meses - 120 dias</option><option value='5'>5 meses - 150 dias</option><option value='6'>6 meses - 180 dias</option><option value='12'>12 meses - 360 dias</option></select><button class='btn-peq' style='background:#2ecc71;color:white'>Marcar como Pago</button></form></div></div>{% endif %}{% endfor %}
</div>
</div>
</div>
<button class='btn-outline' onclick="toggle('sec_anuncios')">📢 Gerir Anúncios ▼</button> <button class='btn-peq' onclick="toggle('novo_anuncio')">+</button>
<div id='sec_anuncios' style='display:none'>{% for a in anuncios %}<div style='border:1px solid #eee;padding:12px;border-radius:12px;margin:10px 0;background:#111;color:white'><a href='/anuncio/{{a['id']}}'>{% if a['foto'] %}<img src='/static/uploads/{{a['foto']}}' style='width:100%;height:140px;object-fit:cover;border-radius:10px'>{% endif %}<b>📢 {{a['titulo']}}</b></a><br><button class='btn-peq' onclick="toggle('det_anuncio_{{a['id']}}')">Mais informações ▼</button><div id='det_anuncio_{{a['id']}}' style='display:none'>Descrição: {{a['descricao']}}<br>Tem site? {% if a['tem_site'] %}Sim - {{a['link_site']}}{% else %}Não{% endif %}<br>WhatsApp: {{a['whatsapp']}}<br><a href='/admin/bloquear-anuncio/{{a['id']}}'><button class='btn-peq'>Bloquear</button></a> <a href='/admin/desbloquear-anuncio/{{a['id']}}'><button class='btn-peq'>Desbloquear</button></a> <a href='/admin/apagar-anuncio/{{a['id']}}'><button class='btn-peq' style='background:#CC092F;color:white'>Apagar</button></a></div></div>{% endfor %}</div>
<div id='novo_anuncio' style='display:none' class='card'><h3>Novo Anúncio</h3><form action='/admin/criar-anuncio' method='post' enctype='multipart/form-data'><input name='titulo' placeholder='Título' required><input name='descricao' placeholder='Descrição'><input name='whatsapp' placeholder='WhatsApp'><input type='file' name='foto'><label><input type='checkbox' name='tem_site' value='1' style='width:auto'> Este anúncio tem um site</label><input name='link_site' placeholder='Link do site (se marcou a caixa)'><button class='btn'>Criar Anúncio</button></form></div>
</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
<script>function filtrar(inp,id){var v=inp.value.toLowerCase();var els=document.getElementById(id).children;for(var i=0;i<els.length;i++){els[i].style.display=els[i].innerText.toLowerCase().includes(v)?'block':'none';}}</script>
"""

PAINEL_PARCEIRO = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span> - Aba Parceiro</b><div><a href='/chat'>💬 Chat {% if msgs_novas %}<span class='badge-msg'>{{msgs_novas}}</span>{% endif %}</a> | <a href='/loja'>Loja</a> | <a href='javascript:voltar()'>⬅ Voltar</a></div></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'>
{% if aviso_mensalidade_parceiro %}<div style='background:#FFCC00;padding:12px;border-radius:10px;text-align:center;font-weight:bold'>{{aviso_mensalidade_parceiro}}</div><br>{% endif %}
<div class='card'><h1>{{ponto}} {{user['nome']}} - {{user['nome_loja']}}</h1>
{% if novas %}<p style='background:#CC092F;color:white;padding:12px;border-radius:10px'>🔔 Tens {{novas}} encomenda(s) nova(s)!</p>{% endif %}
<p><b>Total: {{valor_minhas}} Kz</b> - {{total_minhas}} produtos</p>
<a href='/adicionar-produto'><button class='btn-amarelo'>+ Adicionar Produto</button></a><br><br>
<div class='tabs'>
<a href='#' onclick="document.getElementById('parc_solic').style.display='block';document.getElementById('parc_trans').style.display='none';document.getElementById('parc_pedidos').style.display='none';return false">Encomendas Solicitadas</a>
<a href='#' onclick="document.getElementById('parc_solic').style.display='none';document.getElementById('parc_trans').style.display='block';document.getElementById('parc_pedidos').style.display='none';return false">Transacções Feitas</a>
<a href='#' onclick="document.getElementById('parc_solic').style.display='none';document.getElementById('parc_trans').style.display='none';document.getElementById('parc_pedidos').style.display='block';return false">Pedidos</a>
</div>
<div id='parc_solic'>
{% for e in encomendas %}{% if e['status_encomenda'] not in ['Vendida'] %}<div style='border-bottom:1px solid #eee;padding:8px 0'><b>{{e['produto_nome']}}</b><br><a href='#' onclick="toggle('cli_{{e['id']}}');return false"><b>{{e['cliente_nome']}}</b></a> - {{e['cliente_telefone']}} - {{e['preco']*e['qtd']}} Kz<br>
<div id='cli_{{e['id']}}' style='display:none'><a href='/info-produto/{{e['id']}}'><button class='btn-peq'>Mais informações</button></a><form action='/denunciar-cliente' method='post'><input type='hidden' name='cliente_id' value='{{e['cliente_id']}}'><input name='motivo' placeholder='Motivo' required><button class='btn-peq' style='background:#111;color:white'>Denunciar Cliente</button></form></div>
{% if e['status_encomenda']=='Solicitada' %}<a href='/parceiro/estado/Pedido Aceito/{{e['id']}}'><button class='btn-peq' style='background:#FFCC00'>Pedido Aceito</button></a>{% elif e['status_encomenda']=='Pedido Aceito' %}<a href='/parceiro/estado/Vendida/{{e['id']}}'><button class='btn-peq' style='background:#CC092F;color:white'>Finalizar Transação</button></a>{% endif %}
</div>{% endif %}{% endfor %}
</div>
<div id='parc_trans' style='display:none'>
{% for e in encomendas %}{% if e['status_encomenda']=='Vendida' %}<div style='border-bottom:1px solid #eee;padding:8px 0'><b>{{e['produto_nome']}}</b><br><span class='pequeno'>{{e['cliente_nome']}} - {{e['preco']*e['qtd']}} Kz - {{e['data_finalizada'] or e['data']}}</span></div>{% endif %}{% endfor %}
</div>
<div id='parc_pedidos' style='display:none'>
{% for e in encomendas %}{% if e['status_encomenda']=='Solicitada' %}<div style='border-bottom:1px solid #eee;padding:8px 0'><b>{{e['produto_nome']}}</b> - {{e['cliente_nome']}} - {{e['cliente_telefone']}}<br><a href='/parceiro/estado/Pedido Aceito/{{e['id']}}'><button class='btn-peq' style='background:#2ecc71;color:white'>Tenho disponibilidade para entregar</button></a></div>{% endif %}{% endfor %}
</div>
<h2>📦 Meus Produtos</h2>
<div class='tabs'><a href='#' onclick="document.getElementById('prod_ativos').style.display='block';document.getElementById('prod_esg').style.display='none';return false">✅ Activos</a><a href='#' onclick="document.getElementById('prod_esg').style.display='block';document.getElementById('prod_ativos').style.display='none';return false">🔴 Esgotado {% if n_esg %}<span class='badge-msg'>{{n_esg}}</span>{% endif %}</a></div>
<div id='prod_ativos'>{% for p in meus_produtos %}{% if not p['esgotado_manual'] and p['stock']>0 %}<div style='border:1px solid #eee;padding:10px;border-radius:10px;margin:8px 0'><b>{{p['nome_produto']}}</b><br>Resta: {{p['stock']}}<form action='/parceiro/atualizar-stock/{{p['id']}}' method='post'><input name='stock' type='number' value='{{p['stock']}}' required><button class='btn-peq'>Atualizar Stock</button></form><a href='/parceiro/esgotado/{{p['id']}}'><button class='btn-peq' style='background:#CC092F;color:white'>Marcar como Esgotado</button></a></div>{% endif %}{% endfor %}</div>
<div id='prod_esg' style='display:none'>{% for p in meus_produtos %}{% if p['esgotado_manual'] or p['stock']<=0 %}<div style='border:1px solid #eee;padding:10px;border-radius:10px;margin:8px 0'><b>🔴 {{p['nome_produto']}}</b><br><button class='btn-peq' onclick="toggle('abast_{{p['id']}}')">Abastecer ▼</button><div id='abast_{{p['id']}}' style='display:none'><form action='/parceiro/reabastecer/{{p['id']}}' method='post'><input name='stock' type='number' required placeholder='Quantos abasteceste?'><button class='btn-peq' style='background:#2ecc71;color:white'>Abastecer</button></form></div></div>{% endif %}{% endfor %}</div>
</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

PRODUTO_TPL = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'>{% if p['foto'] %}<img src='/static/uploads/{{p['foto']}}' style='width:100%;height:220px;object-fit:cover;border-radius:12px'>{% endif %}<h2>{{p['nome_produto']}}</h2><div class='preco'>{{p['preco']}} Kz</div><p>🏪 {{p['nome_loja']}} - {{estrelas_txt}} ({{media}} - {{total}} avaliações)</p><p>📍 {{p['provincia']}} - {{p['bairro']}} | Stock: {{p['stock']}}</p>{% if user %}<a href='/chat?com={{p['parceiro_id']}}'><button class='btn-amarelo'>💬 Falar com a Loja</button></a>{% endif %}</div>
<div class='card'><h2>⭐ Comentários</h2>{% for c in comentarios %}<div class='comentario' onclick="toggleComent('com_{{c['id']}}')" style='border-bottom:1px solid #eee;padding:8px 0'><b>{{c['cliente_nome']}}</b> {{c['estrelas_txt']}}<br>{{c['texto']}}<div id='com_{{c['id']}}' style='display:none'>{% if user and user['id']==c['cliente_id'] %}<a href='/apagar-meu-comentario/{{c['id']}}?pid={{p['id']}}' class='link-btn-vermelho'>Apagar</a><form method='post'><input type='hidden' name='cid' value='{{c['id']}}'><select name='estrelas'><option value='5'>5</option><option value='4'>4</option><option value='3'>3</option><option value='2'>2</option><option value='1'>1</option></select><input name='texto' value="{{c['texto']}}"><button class='btn-peq' name='editar_comentario'>Editar</button></form>{% endif %}{% if user and user['role']=='admin' %}<a href='/admin/apagar-comentario/{{c['id']}}' class='link-btn-vermelho'>[Admin Apagar]</a>{% endif %}</div></div>{% endfor %}
{% if user %}<form method='post'><select name='estrelas'><option value='5'>5 ⭐</option><option value='4'>4 ⭐</option><option value='3'>3 ⭐</option><option value='2'>2 ⭐</option><option value='1'>1 ⭐</option></select><input name='texto' placeholder='Escreve o teu comentário...' required><button class='btn' name='comentar'>Comentar</button></form>{% endif %}</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

CHAT_TPL = CSS + """
{% if aviso_pagamento %}<div class='aviso-chat-topo'>⚠️ {{aviso_pagamento}}</div>{% endif %}
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='{{voltar}}'>⬅ Voltar</a></div>
<img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card'><h2>💬 Chat</h2>
{% if not com %}{% for conv in conversas %}<div style='border-bottom:1px solid #eee;padding:10px 0'><a href='/chat?com={{conv['id']}}'><b>{{conv['nome']}}</b></a></div>{% endfor %}{% if not conversas %}<p>Nenhuma mensagem ainda.</p>{% endif %}{% endif %}
{% if com %}{% for m in msgs %}<div style='border-bottom:1px solid #eee;padding:8px 0'><b>{% if m['de_id']==user['id'] %}Tu{% else %}{{m['nome']}}{% endif %}:</b> {{m['texto']}}{% if m['ficheiro'] %}<br>📎 <a href='/static/uploads/{{m['ficheiro']}}' target='_blank'><button class='btn-peq'>Ver Comprovativo</button></a>{% endif %}</div>{% endfor %}
<form method='post' enctype='multipart/form-data'><input type='hidden' name='para_id' value='{{com}}'><div class='chat-input'><input name='texto' placeholder='Escreve...'><label class='grampo'>📎<input type='file' name='ficheiro' accept='image/*,.pdf' style='display:none'></label><button class='btn-peq'>Enviar</button></div></form>{% endif %}
</div></div>
{% if user['role']!='admin' %}<a href='/chat?com=1' class='balao-flutuante'>💬 Falar com o Administrador</a>{% endif %}
<div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

ANUNCIO_TPL = CSS + """
<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><img src='/static/capa.jpg' class='capa-fixa' onerror="this.style.display='none'">
<div class='container'><div class='card' style='text-align:center'>{% if a['foto'] %}<img src='/static/uploads/{{a['foto']}}' style='width:100%;height:220px;object-fit:cover;border-radius:12px'>{% endif %}<h2>📢 {{a['titulo']}}</h2><p>{{a['descricao']}}</p><br>
{% if a['tem_site'] %}<p>Queres abrir o site ou ir para o WhatsApp?</p><a href='{{a['link_site']}}' target='_blank'><button class='btn-amarelo'>🌐 Abrir Site</button></a><br><br><a href='https://wa.me/244{{a['whatsapp']}}' target='_blank'><button class='btn'>💬 Ir para WhatsApp</button></a>
{% else %}<a href='https://wa.me/244{{a['whatsapp']}}' target='_blank'><button class='btn'>💬 Falar no WhatsApp</button></a>{% endif %}</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick="sair()">Sair</button></div><p style='text-align:center;font-size:11px'>© Ngola Store Online</p>
"""

@app.route("/")
def entrada():
    if session.get("user"): return redirect("/loja")
    return render_template_string(ENTRADA)
@app.route("/escolher-tipo")
def escolher_tipo(): return render_template_string(ESCOLHER_TIPO)
@app.route("/cadastro", methods=["GET","POST"])
def cadastro():
    tipo = request.args.get("tipo","cliente"); msg=""
    if request.method=="POST":
        tipo=request.form["role"]; tel_lig=limpar_tel(request.form["tel_lig"]); c=db()
        if c.execute("SELECT * FROM telefones_bloqueados WHERE telefone=?",(tel_lig,)).fetchone():
            c.close(); return render_template_string(CADASTRO,tipo=tipo,msg="⛔ Número bloqueado.")
        tem=request.form.get("tem_whats","sim"); tel_whats=tel_lig if tem=="sim" else limpar_tel(request.form.get("tel_whats","")); senha=request.form["senha"].strip()
        if c.execute("SELECT * FROM users WHERE telefone_ligacao=?",(tel_lig,)).fetchone():
            c.close(); return render_template_string(CADASTRO,tipo=tipo,msg="⚠️ Já tem conta. Vai para Login.")
        c.execute("INSERT INTO users (nome, telefone_ligacao, telefone_whatsapp, provincia, municipio, bairro, nome_loja, role, senha) VALUES (?,?,?,?,?,?,?,?,?)",(request.form["nome"].strip(),tel_lig,tel_whats,request.form.get("provincia",""),request.form.get("municipio",""),request.form.get("bairro",""),request.form.get("nome_loja",""),tipo,senha)); c.commit(); c.close(); return redirect(f"/login?criado={tel_lig}")
    return render_template_string(CADASTRO,tipo=tipo,msg=msg)
@app.route("/login", methods=["GET","POST"])
def login():
    erro=""; msg=""
    if request.args.get("criado"): msg=f"✅ Conta criada! Entra com {request.args.get('criado')} e a tua senha."
    if request.method=="POST":
        tel_digitado=limpar_tel(request.form["tel"]); senha_digitada=request.form["senha"].strip(); c=db(); todos=c.execute("SELECT * FROM users").fetchall(); c.close(); u=None
        for row in todos:
            if (tel_digitado==limpar_tel(row["telefone_ligacao"]) or tel_digitado==limpar_tel(row["telefone_whatsapp"])) and senha_digitada==str(row["senha"]).strip(): u=row; break
        if u:
            session["user"]=dict(u)
            return redirect("/loja")
        erro="Telefone ou senha errada."
    return render_template_string(LOGIN, erro=erro, msg=msg)
@app.route("/esqueci-senha", methods=["GET","POST"])
def esqueci():
    if request.method=="POST":
        c=db(); c.execute("INSERT INTO pedidos_senha(nome,telefone,data) VALUES(?,?,?)",(request.form["nome"],limpar_tel(request.form["telefone"]),datetime.now().strftime("%Y-%m-%d %H:%M"))); c.commit(); c.close(); return pagina_msg("Pedido Enviado", "O Admin vai procurar o teu nome e confirmar se és o dono.", "/login", "Voltar ao Login")
    return render_template_string(ESQUECI)
@app.route("/pedidos-senha")
def pedidos_senha_page():
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); pedidos=c.execute("SELECT * FROM pedidos_senha ORDER BY id DESC").fetchall(); c.close()
    html=CSS+"<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><div class='container'><div class='card'><h2>🔑 Pedidos de Senha</h2>"
    for p in pedidos: html+=f"<div>Nome: {p['nome']} - Tel: {p['telefone']} - {p['data']}</div>"
    html+="</div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick=\"sair()\">Sair</button></div>"; return html
@app.route("/denuncias")
def denuncias_page():
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE denuncias SET vista=1"); dens=c.execute("SELECT * FROM denuncias ORDER BY id DESC").fetchall(); c.commit(); c.close()
    html=CSS+"<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><div class='container'><div class='card'><h2>❗ Denúncias</h2>"
    for d in dens: html+=f"<div>{d['parceiro_nome']} denunciou {d['cliente_nome']}: {d['motivo']} - <a href='/admin/avisar-cliente/{d['cliente_id']}?motivo={d['motivo']}'><button class='btn-peq' style='background:#FFCC00'>Avisar Cliente</button></a></div>"
    html+="</div></div>"; return html
@app.route("/meu-perfil", methods=["GET","POST"])
def meu_perfil():
    u=session.get("user")
    if not u: return redirect("/login")
    c=db(); user_db=c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
    if request.method=="POST":
        foto=user_db["foto"]; f=request.files.get("foto")
        if f and f.filename!="":
            foto=f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"; f.save(os.path.join(app.config["UPLOAD_FOLDER"],foto))
        c.execute("UPDATE users SET foto=?, nome=?, senha=?, telefone_ligacao=? WHERE id=?",(foto,request.form["nome"],request.form["senha"],limpar_tel(request.form["telefone"]),u["id"])); c.commit(); session["user"]=dict(c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()); c.close(); return redirect("/meu-perfil")
    n_feitas=c.execute("SELECT COUNT(*) FROM encomendas WHERE cliente_id=? AND status_encomenda='Vendida'",(u["id"],)).fetchone()[0]
    n_canc=c.execute("SELECT COUNT(*) FROM encomendas WHERE cliente_id=? AND status_encomenda='Cancelada'",(u["id"],)).fetchone()[0]
    total_gasto=c.execute("SELECT COALESCE(SUM(preco*qtd),0) FROM encomendas WHERE cliente_id=? AND status_encomenda='Vendida'",(u["id"],)).fetchone()[0]
    feitas=c.execute("SELECT * FROM encomendas WHERE cliente_id=? AND status_encomenda='Vendida' ORDER BY id DESC",(u["id"],)).fetchall(); c.close()
    return render_template_string(MEU_PERFIL,user=dict(user_db),n_feitas=n_feitas,n_canceladas=n_canc,total_gasto=total_gasto,feitas=feitas)
@app.route("/reclamacao/<int:eid>", methods=["POST"])
def reclamacao(eid):
    u=session.get("user")
    if not u: return redirect("/login")
    c=db(); c.execute("UPDATE encomendas SET reclamacao=? WHERE id=? AND cliente_id=?",(request.form["reclamacao"],eid,u["id"])); c.commit(); c.close(); return redirect("/meu-perfil")
@app.route("/ver-contas")
def ver_contas():
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); clientes=c.execute("SELECT * FROM users WHERE role='cliente'").fetchall(); parceiros=c.execute("SELECT * FROM users WHERE role='parceiro'").fetchall(); c.close()
    html=CSS+"<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><div class='container'>"
    html+="<div class='card'><h1>👤 Clientes</h1>"
    for t in clientes: html+=f"<div style='border:1px solid #ccc;padding:10px;margin:10px;border-radius:10px'>Nome: {t['nome']}<br>Telefone: [{t['telefone_ligacao']}]<br>Senha: [{t['senha']}]<br>Rótulo: {t['rotulo'] or ''}</div>"
    html+="</div><div class='card'><h1>🏪 Parceiros</h1>"
    for t in parceiros:
        m,total=media_estrelas(t["id"])
        html+=f"<div style='border:1px solid #ccc;padding:10px;margin:10px;border-radius:10px'>Nome: {ponto_status(dict(t))} {t['nome']}<br>Loja: {t['nome_loja']}<br>Telefone: [{t['telefone_ligacao']}]<br>Senha: [{t['senha']}]<br>Estrelas: {stars(m)} {m} ({total})</div>"
    html+="</div><a href='/admin'><button class='btn'>Voltar</button></a></div></div>"; return html
@app.route("/logout")
def logout(): session.clear(); return redirect("/")
def get_cart_dict(): return session.get("carrinho_dict",{})
def top_lojas_fn():
    c=db(); rows=c.execute("SELECT DISTINCT parceiro_id, nome_loja FROM produtos WHERE status='aprovado'").fetchall(); c.close(); out=[]
    for r in rows:
        m,total=media_estrelas(r["parceiro_id"])
        if total>0: out.append({"parceiro_id":r["parceiro_id"],"nome_loja":r["nome_loja"],"estrelas_txt":stars(m),"total":total,"media":m})
    out.sort(key=lambda x: x["media"], reverse=True); return out[:5]
@app.route("/loja")
def loja():
    user=session.get("user"); filtro=request.args.get("filtro",""); pesquisa_loja=request.args.get("pesquisa_loja","")
    q="SELECT produtos.*, users.bloqueado as bloqueado FROM produtos LEFT JOIN users ON produtos.parceiro_id=users.id WHERE status='aprovado'"; params=[]
    if user and user["role"]=="parceiro":
        q+=" AND produtos.parceiro_id!=?"; params.append(user["id"])
    if pesquisa_loja: q+=" AND (produtos.nome_loja LIKE ? OR users.nome LIKE ?)"; params.append(f"%{pesquisa_loja}%"); params.append(f"%{pesquisa_loja}%")
    if filtro=="reabastecidos": q+=" AND reabastecido=1"
    q+=" ORDER BY id DESC"; c=db(); rows=c.execute(q,params).fetchall(); anuncios=c.execute("SELECT * FROM anuncios WHERE bloqueado=0").fetchall(); c.close(); prods=[]
    for p in rows:
        d=dict(p); m,total=media_estrelas(p["parceiro_id"]); d["estrelas_txt"]=f"{stars(m)} {m} ({total})" if total else ""; prods.append(d)
    pos_anuncio=set(random.sample(range(1, max(2,len(prods)+1)), min(len(anuncios), max(1,len(prods)//5+1)))) if prods and anuncios else set()
    msgs_novas=num_msgs_novas(user["id"]) if user else 0
    ponto=ponto_status(user) if user else ""
    mostrar_todos=bool(filtro)
    return render_template_string(LOJA,prods=prods,user=user,anuncios=anuncios,top_lojas=top_lojas_fn(),pesquisa_loja=pesquisa_loja,pos_anuncio=pos_anuncio,msgs_novas=msgs_novas,ponto=ponto,mostrar_todos=mostrar_todos)
@app.route("/pesquisa-lojas")
def pesquisa_lojas():
    q=request.args.get("q",""); top=top_lojas_fn()
    if q:
        c=db(); rows=c.execute("SELECT * FROM users WHERE role='parceiro' AND (nome LIKE ? OR nome_loja LIKE ?)",(f"%{q}%",f"%{q}%")).fetchall(); c.close(); top=[]
        for r in rows:
            m,total=media_estrelas(r["id"]); top.append({"parceiro_id":r["id"],"nome_loja":r["nome_loja"],"estrelas_txt":stars(m)})
    return render_template_string(PESQUISA_LOJAS,top_lojas=top,q=q)
@app.route("/lojas")
def lojas_lista():
    c=db(); rows=c.execute("SELECT * FROM users WHERE role='parceiro'").fetchall(); c.close(); lojas=[]
    for r in rows:
        d=dict(r); m,total=media_estrelas(r["id"]); d["estrelas_txt"]=f"{stars(m)} {m} ({total})" if total else "Sem avaliações"; d["ponto"]=ponto_status(d); lojas.append(d)
    return render_template_string(LOJAS_LISTA,lojas=lojas)
@app.route("/loja-da-loja/<int:pid>")
def loja_da_loja(pid):
    c=db(); loja_user=c.execute("SELECT * FROM users WHERE id=?",(pid,)).fetchone()
    rows=c.execute("SELECT produtos.*, users.bloqueado as bloqueado FROM produtos LEFT JOIN users ON produtos.parceiro_id=users.id WHERE status='aprovado' AND parceiro_id=?",(pid,)).fetchall(); anuncios=c.execute("SELECT * FROM anuncios WHERE bloqueado=0").fetchall(); c.close(); prods=[]
    for p in rows:
        d=dict(p); m,total=media_estrelas(p["parceiro_id"]); d["estrelas_txt"]=f"{stars(m)} {m} ({total})" if total else ""; prods.append(d)
    user=session.get("user"); msgs_novas=num_msgs_novas(user["id"]) if user else 0
    return render_template_string(LOJA,prods=prods,user=user,anuncios=anuncios,top_lojas=top_lojas_fn(),pesquisa_loja="",pos_anuncio=set(),msgs_novas=msgs_novas,ponto=ponto_status(user) if user else "",mostrar_todos=True)
@app.route("/add-carrinho/<int:pid>", methods=["POST"])
def add_carrinho(pid):
    d=get_cart_dict(); d[str(pid)]=d.get(str(pid),0)+1; session["carrinho_dict"]=d; return redirect("/loja")
@app.route("/carrinho-mais/<int:pid>")
def carrinho_mais(pid):
    d=get_cart_dict(); d[str(pid)]=d.get(str(pid),0)+1; session["carrinho_dict"]=d; return redirect("/carrinho")
@app.route("/carrinho-menos/<int:pid>")
def carrinho_menos(pid):
    d=get_cart_dict()
    if str(pid) in d:
        d[str(pid)]-=1
        if d[str(pid)]<=0: del d[str(pid)]
    session["carrinho_dict"]=d; return redirect("/carrinho")
@app.route("/remover-carrinho/<int:pid>")
def remover(pid):
    d=get_cart_dict(); d.pop(str(pid),None); session["carrinho_dict"]=d; return redirect("/carrinho")
@app.route("/carrinho")
def carrinho():
    u=session.get("user")
    if not u: return redirect("/login")
    d=get_cart_dict(); itens=[]; total=0; c=db()
    for pid_str,qtd in d.items():
        p=c.execute("SELECT * FROM produtos WHERE id=?",(int(pid_str),)).fetchone()
        if p: dd=dict(p); dd["qtd"]=qtd; itens.append(dd); total+=dd["preco"]*qtd
    enc=c.execute("SELECT * FROM encomendas WHERE cliente_id=? ORDER BY id DESC",(u["id"],)).fetchall(); c.close()
    return render_template_string(CARRINHO,itens=itens,total=total,encomendas=enc,msgs_novas=num_msgs_novas(u["id"]))
@app.route("/finalizar-carrinho", methods=["POST"])
def finalizar_carrinho():
    u=session.get("user")
    if not u: return redirect("/login")
    d=get_cart_dict()
    if not d: return redirect("/loja")
    metodo=request.form.get("metodo_pagamento","Pagar na Entrega"); pagamento=request.form.get("pagamento","Presencial"); c=db(); itens=[]; total=0; ultimo=False
    for pid_str,qtd in d.items():
        p=c.execute("SELECT * FROM produtos WHERE id=?",(int(pid_str),)).fetchone()
        if p and p["stock"]>=qtd:
            if p["stock"]==qtd: ultimo=True
            c.execute("INSERT INTO encomendas (cliente_id, cliente_nome, cliente_telefone, produto_id, produto_nome, parceiro_id, nome_loja, preco, qtd, pagamento, metodo_pagamento, provincia, bairro, data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(u["id"],u["nome"],u["telefone_ligacao"],p["id"],p["nome_produto"],p["parceiro_id"],p["nome_loja"],p["preco"],qtd,pagamento,metodo,u["provincia"],u["bairro"],datetime.now().strftime("%Y-%m-%d %H:%M")))
            c.execute("UPDATE produtos SET stock=stock-? WHERE id=?",(qtd,pid)); dd=dict(p); dd["qtd"]=qtd; itens.append(dd); total+=p["preco"]*qtd
    c.commit(); c.close(); session["carrinho_dict"]={}
    return render_template_string(SUCESSO,nome=u["nome"],itens=itens,total=total,metodo=metodo,ultimo=ultimo)
@app.route("/adicionar-produto", methods=["GET","POST"])
def add_produto():
    u=session.get("user")
    if not u or u["role"] not in ("parceiro","admin"): return redirect("/login")
    if request.method=="POST":
        usar=request.form.get("usar_existentes")=="sim"; c=db(); user_db=c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
        if usar: provincia,municipio,bairro=user_db["provincia"],user_db["municipio"],user_db["bairro"]; lat,lng,loja=user_db["gps_lat"],user_db["gps_lng"],user_db["nome_loja"]
        else:
            provincia=request.form.get("provincia") or user_db["provincia"]; municipio=request.form.get("municipio") or user_db["municipio"]; bairro=request.form.get("bairro") or user_db["bairro"]; lat=request.form.get("gps_lat") or user_db["gps_lat"]; lng=request.form.get("gps_lng") or user_db["gps_lng"]; loja=request.form.get("nome_loja") or user_db["nome_loja"]
            if request.form.get("alcance_alteracao")=="novos_dados_loja":
                c.execute("UPDATE users SET nome_loja=?, provincia=?, municipio=?, bairro=?, gps_lat=?, gps_lng=?, telefone_ligacao=?, telefone_whatsapp=? WHERE id=?",(loja,provincia,municipio,bairro,lat,lng,request.form.get("novo_tel_lig") or user_db["telefone_ligacao"],request.form.get("novo_tel_whats") or user_db["telefone_whatsapp"],u["id"]))
        foto_nome=""; f=request.files.get("foto")
        if f and f.filename!="":
            ext=f.filename.rsplit(".",1)[-1].lower()
            if ext in ALLOWED: foto_nome=f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"; f.save(os.path.join(app.config["UPLOAD_FOLDER"],foto_nome))
        c.execute("INSERT INTO produtos (parceiro_id, nome_loja, nome_produto, tipo, preco, stock, provincia, municipio, bairro, gps_lat, gps_lng, foto, status, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(u["id"],loja,request.form["nome_produto"],request.form["tipo"],float(request.form["preco"]),int(request.form["stock"]),provincia,municipio,bairro,lat,lng,foto_nome,"pendente",datetime.now().strftime("%Y-%m-%d"))); c.commit(); c.close()
        return pagina_msg("Produto Enviado!", "O teu produto foi enviado para aprovação.", "/painel-parceiro", "Voltar para Aba Parceiro")
    return render_template_string(ADD_PRODUTO,user=u)
@app.route("/produto/<int:pid>", methods=["GET","POST"])
def produto(pid):
    u=session.get("user"); c=db(); p=c.execute("SELECT * FROM produtos WHERE id=?",(pid,)).fetchone()
    if not p: c.close(); return redirect("/loja")
    if request.method=="POST" and u:
        if "comentar" in request.form:
            chk=c.execute("SELECT * FROM encomendas WHERE cliente_id=? AND parceiro_id=?",(u["id"],p["parceiro_id"])).fetchone()
            if not chk: c.close(); return pagina_msg("Não podes comentar", "Só quem já comprou pode comentar.", f"/produto/{pid}", "Voltar")
            c.execute("INSERT INTO comentarios(produto_id,parceiro_id,cliente_id,cliente_nome,estrelas,texto) VALUES(?,?,?,?,?,?)",(pid,p["parceiro_id"],u["id"],u["nome"],request.form["estrelas"],request.form["texto"])); c.commit()
        if "editar_comentario" in request.form:
            c.execute("UPDATE comentarios SET estrelas=?, texto=? WHERE id=? AND cliente_id=?",(request.form["estrelas"],request.form["texto"],request.form["cid"],u["id"])); c.commit()
    m,total=media_estrelas(p["parceiro_id"]); coms=[]
    for co in c.execute("SELECT * FROM comentarios WHERE produto_id=? ORDER BY id DESC",(pid,)).fetchall():
        d=dict(co); d["estrelas_txt"]=stars(co["estrelas"]); coms.append(d)
    c.close(); return render_template_string(PRODUTO_TPL,p=p,user=u,comentarios=coms,estrelas_txt=stars(m),media=m,total=total)
@app.route("/apagar-meu-comentario/<int:cid>")
def apagar_meu_comentario(cid):
    u=session.get("user")
    if u: c=db(); c.execute("DELETE FROM comentarios WHERE id=? AND cliente_id=?",(cid,u["id"])); c.commit(); c.close()
    return redirect(f"/produto/{request.args.get('pid',1)}")
@app.route("/cancelar-encomenda/<int:eid>")
def cancelar_encomenda(eid):
    u=session.get("user")
    if not u: return redirect("/login")
    c=db(); e=c.execute("SELECT * FROM encomendas WHERE id=? AND cliente_id=?",(eid,u["id"])).fetchone()
    if e and e["status_encomenda"] in ("Solicitada","Pedido Aceito"):
        c.execute("UPDATE encomendas SET status_encomenda='Cancelada', cancelado_por=? WHERE id=?",(f"Cliente: {u['nome']}",eid)); c.execute("INSERT INTO historico_qtd(encomenda_id,texto,data) VALUES(?,?,?)",(eid,f"Cliente {u['nome']} cancelou a encomenda #{eid}",datetime.now().strftime("%Y-%m-%d %H:%M"))); c.execute("UPDATE produtos SET stock=stock+? WHERE id=?",(e["qtd"],e["produto_id"])); c.commit(); notificar(e["parceiro_id"],f"Encomenda #{eid} cancelada pelo cliente {u['nome']}.")
    c.close(); return redirect("/carrinho")
@app.route("/chat", methods=["GET","POST"])
def chat():
    u=session.get("user")
    if not u: return redirect("/login")
    c=db(); fresh=c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
    if fresh: session["user"]=dict(fresh); u=dict(fresh)
    com=request.args.get("com",type=int) or 0
    aviso_pagamento=None
    if u["role"]=="parceiro":
        info=info_mensalidade(dict(fresh))
        if info["categoria"]=="pago" and info["dias_restantes"] is not None and info["dias_restantes"]<=10:
            aviso_pagamento=f"Faltam {info['dias_restantes']} dias para a tua mensalidade terminar."
        elif info["categoria"]=="atraso":
            aviso_pagamento=f"Estás com {info['atraso']} de atraso na mensalidade."
        elif info["categoria"]=="nao_pago":
            aviso_pagamento="Ainda não pagaste a mensalidade - Paga para manteres a loja ativa."
    if request.method=="POST":
        ficheiro=""
        if u["role"]=="cliente":
            f=request.files.get("ficheiro")
            if f and f.filename!="":
                ext=f.filename.rsplit(".",1)[-1].lower()
                if ext in ALLOWED: ficheiro=f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"; f.save(os.path.join(app.config["UPLOAD_FOLDER"],ficheiro))
        texto=request.form.get("texto","") or "📎 Enviou um documento / comprovativo"
        c.execute("INSERT INTO mensagens(de_id,para_id,texto,data,ficheiro) VALUES(?,?,?,?,?)",(u["id"],request.form["para_id"],texto,datetime.now().strftime("%Y-%m-%d %H:%M"),ficheiro)); c.commit(); notificar(int(request.form["para_id"]),f"💬 Mensagem nova de {u['nome']}"); c.close(); return redirect(f"/chat?com={request.form['para_id']}")
    if com: c.execute("UPDATE mensagens SET lida=1 WHERE para_id=? AND de_id=?",(u["id"],com)); c.commit()
    msgs=[]; conversas=[]
    conversas=c.execute("SELECT DISTINCT users.* FROM mensagens JOIN users ON (mensagens.de_id=users.id OR mensagens.para_id=users.id) WHERE (mensagens.de_id=? OR mensagens.para_id=?) AND users.id!=?",(u["id"],u["id"],u["id"])).fetchall()
    if u["role"]=="admin":
        conversas=c.execute("SELECT DISTINCT users.* FROM mensagens JOIN users ON mensagens.de_id=users.id WHERE mensagens.para_id=?",(u["id"],)).fetchall()
    if com:
        for m in c.execute("SELECT mensagens.*, users.nome FROM mensagens LEFT JOIN users ON mensagens.de_id=users.id WHERE (de_id=? AND para_id=?) OR (de_id=? AND para_id=?) ORDER BY mensagens.id ASC",(u["id"],com,com,u["id"])).fetchall(): msgs.append(dict(m))
    c.close(); return render_template_string(CHAT_TPL,msgs=msgs,com=com,user=u,conversas=conversas,voltar=voltar_para(u),aviso_pagamento=aviso_pagamento)
@app.route("/anuncio/<int:aid>")
def anuncio_view(aid):
    c=db(); a=c.execute("SELECT * FROM anuncios WHERE id=?",(aid,)).fetchone(); c.close()
    if not a: return redirect("/loja")
    return render_template_string(ANUNCIO_TPL,a=a)
@app.route("/faturacao/<tipo>/<int:uid>")
def faturacao_page(tipo, uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    dia,semana,mes,ano=faturacao(uid,tipo); c=db(); user_db=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone(); c.close()
    html=CSS+f"<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><div class='container'><div class='card'><h2>💰 Faturação - {user_db['nome']}</h2><p>Hoje: <b>{dia} Kz</b></p><p>Esta Semana: <b>{semana} Kz</b></p><p>Este Mês: <b>{mes} Kz</b></p><p>Este Ano: <b>{ano} Kz</b></p><a href='/admin'><button class='btn'>Voltar</button></a></div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick=\"sair()\">Sair</button></div>"; return html
@app.route("/info-produto/<int:eid>")
def info_produto(eid):
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    c=db(); e=c.execute("SELECT * FROM encomendas WHERE id=? AND parceiro_id=?",(eid,u["id"])).fetchone()
    if not e: c.close(); return redirect("/painel-parceiro")
    p=c.execute("SELECT * FROM produtos WHERE id=?",(e["produto_id"],)).fetchone(); c.close()
    html=CSS+f"<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><div class='container'><div class='card'><h2>ℹ️ Informações do Produto - Pedido #{e['id']}</h2><p>Produto: {e['produto_nome']}</p><p>Preço: {e['preco']} Kz x {e['qtd']}</p><p>Tipo: {p['tipo'] if p else ''}</p><p>Província: {p['provincia'] if p else ''} - Bairro: {p['bairro'] if p else ''}</p><p>Stock: {p['stock'] if p else ''}</p><p>Cliente: {e['cliente_nome']} - {e['cliente_telefone']}</p></div></div>"; return html
@app.route("/admin")
def admin():
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    f_data=request.args.get("data",""); hoje=datetime.now(); c=db()
    total_vendas=c.execute("SELECT COALESCE(SUM(preco*qtd),0) FROM encomendas WHERE status_encomenda='Vendida'").fetchone()[0]
    total_dia=c.execute("SELECT COALESCE(SUM(preco*qtd),0) FROM encomendas WHERE status_encomenda='Vendida' AND date(data)=?",(hoje.strftime("%Y-%m-%d"),)).fetchone()[0]
    total_semana=c.execute("SELECT COALESCE(SUM(preco*qtd),0) FROM encomendas WHERE status_encomenda='Vendida' AND date(data)>=?",((hoje-timedelta(days=hoje.weekday())).strftime("%Y-%m-%d"),)).fetchone()[0]
    total_mes=c.execute("SELECT COALESCE(SUM(preco*qtd),0) FROM encomendas WHERE status_encomenda='Vendida' AND substr(data,1,7)=?",(hoje.strftime("%Y-%m"),)).fetchone()[0]
    total_ano=c.execute("SELECT COALESCE(SUM(preco*qtd),0) FROM encomendas WHERE status_encomenda='Vendida' AND substr(data,1,4)=?",(hoje.strftime("%Y"),)).fetchone()[0]
    total_parceiros=c.execute("SELECT COUNT(*) FROM users WHERE role='parceiro'").fetchone()[0]; total_clientes=c.execute("SELECT COUNT(*) FROM users WHERE role='cliente'").fetchone()[0]
    total_produtos=c.execute("SELECT COUNT(*) FROM produtos WHERE status='aprovado'").fetchone()[0]; total_encomendas=c.execute("SELECT COUNT(*) FROM encomendas").fetchone()[0]
    total_pagos=c.execute("SELECT COUNT(*) FROM users WHERE role='parceiro' AND pago=1").fetchone()[0]; total_canceladas=c.execute("SELECT COUNT(*) FROM encomendas WHERE status_encomenda='Cancelada'").fetchone()[0]
    aviso_mensalidade=None
    for pr in c.execute("SELECT * FROM users WHERE role='parceiro'").fetchall():
        info=info_mensalidade(dict(pr))
        if info["categoria"]=="atraso":
            aviso_mensalidade=f"O parceiro {pr['nome']} - {info['texto']}."
            break
        if info["categoria"]=="pago" and info["dias_restantes"] is not None and info["dias_restantes"]<=10:
            aviso_mensalidade=f"O parceiro {pr['nome']} - {info['texto']}."
            break
    todos_raw=c.execute("SELECT * FROM users WHERE role IN ('cliente','parceiro')").fetchall(); todos_users=[]
    n_pagos=0; n_nao_pagos=0; n_avisados=0
    for r in todos_raw:
        d=dict(r); d["ponto"]=ponto_status(d)
        if d["role"]=="parceiro":
            info=info_mensalidade(d); d["texto_mens"]=info["texto"]; d["categoria_mens"]=info["categoria"]; d["dias_restantes"]=info["dias_restantes"]; d["atraso"]=info["atraso"]
            if info["categoria"]=="pago": n_pagos+=1
            if info["categoria"] in ("nao_pago","atraso"): n_nao_pagos+=1
            if d["aviso"]: n_avisados+=1
        todos_users.append(d)
    pendentes=c.execute("SELECT * FROM produtos WHERE status IN ('pendente','reavaliacao','rejeitado') ORDER BY id DESC").fetchall(); anuncios=c.execute("SELECT * FROM anuncios").fetchall(); historico=c.execute("SELECT * FROM historico_qtd ORDER BY id DESC LIMIT 50").fetchall()
    n_solic=c.execute("SELECT COUNT(*) FROM encomendas WHERE status_encomenda='Solicitada'").fetchone()[0]; n_conf=c.execute("SELECT COUNT(*) FROM encomendas WHERE status_encomenda IN ('Pedido Aceito','Vendida')").fetchone()[0]; n_canc=total_canceladas
    if f_data: rel=c.execute("SELECT COUNT(*), COALESCE(SUM(preco*qtd),0) FROM encomendas WHERE status_encomenda='Vendida' AND date(data)=?",(f_data,)).fetchone()
    else: rel=(total_encomendas,total_vendas)
    encomendas=c.execute("SELECT * FROM encomendas ORDER BY id DESC LIMIT 100").fetchall(); c.close()
    return render_template_string(ADMIN,total_vendas=total_vendas,total_dia=total_dia,total_semana=total_semana,total_mes=total_mes,total_ano=total_ano,total_parceiros=total_parceiros,total_clientes=total_clientes,total_produtos=total_produtos,total_encomendas=total_encomendas,total_pagos=total_pagos,total_canceladas=total_canceladas,todos_users=todos_users,pendentes=pendentes,anuncios=anuncios,f_data=f_data,rel_total=rel[0],rel_valor=rel[1],encomendas=encomendas,historico=historico,msgs_novas=num_msgs_novas(u["id"]),num_senha=num_pedidos_senha(),num_pendentes=num_pendentes(),num_denuncias=num_denuncias_novas(),n_solic=n_solic,n_conf=n_conf,n_canc=n_canc,aviso_mensalidade=aviso_mensalidade,n_pagos=n_pagos,n_nao_pagos=n_nao_pagos,n_avisados=n_avisados)
@app.route("/admin/marcar-pago/<int:uid>", methods=["GET","POST"])
def marcar_pago(uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    if request.method=="POST":
        meses=int(request.form.get("meses",1))
        c=db(); c.execute("UPDATE users SET pago=1, aviso=0, data_pago=?, meses_pagos=? WHERE id=?",(datetime.now().strftime("%Y-%m-%d"),meses,uid)); c.commit(); c.close()
        notificar(uid, f"Pagamento confirmado - {meses} mes(es) - {meses*30} dias.")
        return redirect("/admin")
    c=db(); c.execute("UPDATE users SET pago=0, aviso=0, meses_pagos=0, data_pago='' WHERE id=?",(uid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/avisar/<int:uid>")
def avisar(uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE users SET aviso=1 WHERE id=?",(uid,)); c.commit(); c.close(); notificar(uid,"⚠️ Aviso de Pagamento: Estás com a mensalidade em atraso."); return redirect("/admin")
@app.route("/admin/bloquear/<int:uid>")
def bloquear(uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); cur=c.execute("SELECT bloqueado FROM users WHERE id=?",(uid,)).fetchone(); c.execute("UPDATE users SET bloqueado=? WHERE id=?",(0 if cur["bloqueado"] else 1,uid)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/limpar-loja/<int:uid>")
def limpar_loja(uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("DELETE FROM produtos WHERE parceiro_id=?",(uid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/apagar-parceiro/<int:uid>", methods=["POST"])
def apagar_parceiro(uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    motivo=request.form.get("motivo",""); c=db()
    for e in c.execute("SELECT * FROM encomendas WHERE parceiro_id=? AND status_encomenda IN ('Solicitada','Pedido Aceito')",(uid,)).fetchall():
        c.execute("UPDATE encomendas SET status_encomenda='Cancelada', cancelado_por='Admin' WHERE id=?",(e["id"],)); notificar(e["cliente_id"],f"⚠️ Por motivos de: {motivo}, bloqueamos a empresa e as encomendas foram canceladas.")
    c.execute("DELETE FROM produtos WHERE parceiro_id=?",(uid,)); c.execute("DELETE FROM users WHERE id=?",(uid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/remover-rotulo/<int:uid>", methods=["POST"])
def admin_remover_rotulo(uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE users SET rotulo='' WHERE id=?",(uid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/apagar-cliente/<int:uid>", methods=["POST"])
def admin_apagar_cliente(uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("DELETE FROM users WHERE id=?",(uid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/avisar-cliente/<int:uid>")
def admin_avisar_cliente(uid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    motivo=request.args.get("motivo","Denúncia recebida"); c=db(); c.execute("INSERT INTO avisos_cliente(cliente_id,texto,de_nome,data) VALUES(?,?,?,?)",(uid,f"⚠️ Aviso: {motivo} - Entra em contacto com o Admin para esclarecimento.",u["nome"],datetime.now().strftime("%Y-%m-%d %H:%M"))); c.commit(); c.close(); notificar(uid,f"⚠️ Recebeste um aviso do Admin: {motivo}"); return redirect("/admin")
@app.route("/admin/criar-anuncio", methods=["POST"])
def criar_anuncio():
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    foto=""; f=request.files.get("foto")
    if f and f.filename!="": foto=f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"; f.save(os.path.join(app.config["UPLOAD_FOLDER"],foto))
    tem_site=1 if request.form.get("tem_site") else 0
    c=db(); c.execute("INSERT INTO anuncios(titulo,descricao,foto,link_site,whatsapp,tem_site) VALUES(?,?,?,?,?,?)",(request.form["titulo"],request.form["descricao"],foto,request.form["link_site"],limpar_tel(request.form["whatsapp"]),tem_site)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/bloquear-anuncio/<int:aid>")
def bloquear_anuncio(aid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE anuncios SET bloqueado=1 WHERE id=?",(aid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/desbloquear-anuncio/<int:aid>")
def desbloquear_anuncio(aid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE anuncios SET bloqueado=0 WHERE id=?",(aid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/apagar-anuncio/<int:aid>")
def apagar_anuncio(aid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("DELETE FROM anuncios WHERE id=?",(aid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/admin/apagar-comentario/<int:cid>")
def admin_apagar_comentario(cid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("DELETE FROM comentarios WHERE id=?",(cid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/aprovar/<int:pid>")
def aprovar(pid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE produtos SET status='aprovado', motivo='' WHERE id=?",(pid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/rejeitar/<int:pid>")
def rejeitar(pid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE produtos SET status='rejeitado', motivo='Rejeitado pelo Admin' WHERE id=?",(pid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/reavaliacao/<int:pid>")
def reavaliacao(pid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE produtos SET status='reavaliacao', motivo='Precisa de correção' WHERE id=?",(pid,)); c.commit(); c.close(); return redirect("/admin")
@app.route("/rejeitar-motivo/<int:pid>", methods=["POST"])
def rejeitar_motivo(pid):
    u=session.get("user")
    if not u or u["role"]!="admin": return redirect("/login")
    c=db(); c.execute("UPDATE produtos SET status='reavaliacao', motivo=? WHERE id=?",(request.form.get("motivo",""),pid)); c.commit(); c.close(); return redirect("/admin")
@app.route("/corrigir-produto/<int:pid>", methods=["GET","POST"])
def corrigir(pid):
    u=session.get("user")
    if not u: return redirect("/login")
    c=db(); p=c.execute("SELECT * FROM produtos WHERE id=?",(pid,)).fetchone()
    if p["status"] not in ("reavaliacao","rejeitado"):
        c.close(); return pagina_msg("Não podes editar", "Só podes corrigir depois do Admin pedir reavaliação.", "/painel-parceiro", "Voltar para Aba Parceiro")
    if request.method=="POST":
        c.execute("UPDATE produtos SET nome_produto=?, preco=?, stock=?, status='pendente', motivo='Reenviado após correção' WHERE id=?",(request.form["nome_produto"],float(request.form["preco"]),int(request.form["stock"]),pid)); c.commit(); c.close(); return redirect("/painel-parceiro")
    c.close(); return render_template_string(CSS+f"<div class='topo'><b>NGOLA <span>STORE</span></b><a href='javascript:voltar()'>⬅ Voltar</a></div><div class='container'><div class='card'><h2>Corrigir - {p['nome_produto']}</h2><p>Motivo: <b>{p['motivo']}</b></p><form method='post'><label>Nome</label><input name='nome_produto' value=\"{p['nome_produto']}\" required><label>Preço</label><input name='preco' type='number' value='{p['preco']}' required><label>Stock</label><input name='stock' type='number' value='{p['stock']}' required><button class='btn'>Reenviar</button></form></div></div><div style='text-align:center;padding:20px'><button class='btn-outline' onclick=\"sair()\">Sair</button></div>")
@app.route("/painel-parceiro")
def painel_parceiro():
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    c=db(); uu=c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
    novas=c.execute("SELECT COUNT(*) FROM encomendas WHERE parceiro_id=? AND vista_parceiro=0",(u["id"],)).fetchone()[0]
    c.execute("UPDATE encomendas SET vista_parceiro=1 WHERE parceiro_id=?",(u["id"],)); c.commit()
    session["user"]=dict(uu); minhas=c.execute("SELECT * FROM encomendas WHERE parceiro_id=? ORDER BY id DESC",(u["id"],)).fetchall(); meus=c.execute("SELECT * FROM produtos WHERE parceiro_id=? ORDER BY id DESC",(u["id"],)).fetchall(); n_esg=len([p for p in meus if p["esgotado_manual"] or p["stock"]<=0]); total_minhas=len(minhas); valor=sum([x["preco"]*x["qtd"] for x in minhas if x["status_encomenda"]=="Vendida"]); c.close()
    info=info_mensalidade(dict(uu))
    aviso_parceiro=None
    if info["categoria"]=="pago" and info["dias_restantes"] is not None and info["dias_restantes"]<=10:
        aviso_parceiro=f"Faltam {info['dias_restantes']} dias para a tua mensalidade terminar."
    elif info["categoria"]=="atraso":
        aviso_parceiro=f"Estás com {info['atraso']} de atraso na mensalidade."
    elif info["categoria"]=="nao_pago":
        aviso_parceiro="Ainda não pagaste a mensalidade."
    return render_template_string(PAINEL_PARCEIRO,encomendas=minhas,meus_produtos=meus,user=dict(uu),total_minhas=total_minhas,valor_minhas=valor,ponto=ponto_status(dict(uu)),msgs_novas=num_msgs_novas(u["id"]),novas=novas,n_esg=n_esg,aviso_mensalidade_parceiro=aviso_parceiro)
@app.route("/parceiro/estado/<estado>/<int:eid>")
def parceiro_estado(estado,eid):
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    c=db()
    if estado=="Vendida":
        c.execute("UPDATE encomendas SET status_encomenda=?, data_finalizada=? WHERE id=? AND parceiro_id=?",(estado,datetime.now().strftime("%Y-%m-%d %H:%M"),eid,u["id"]))
    else:
        c.execute("UPDATE encomendas SET status_encomenda=? WHERE id=? AND parceiro_id=?",(estado,eid,u["id"]))
    c.commit(); c.close(); return redirect("/painel-parceiro")
@app.route("/parceiro/atualizar-stock/<int:pid>", methods=["POST"])
def atualizar_stock(pid):
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    novo=int(request.form["stock"]); c=db(); c.execute("UPDATE produtos SET stock=?, esgotado_manual=0 WHERE id=? AND parceiro_id=?",(novo,pid,u["id"])); c.commit(); c.close(); return redirect("/painel-parceiro")
@app.route("/parceiro/reabastecer/<int:pid>", methods=["POST"])
def reabastecer(pid):
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    novo=int(request.form["stock"]); c=db(); prod=c.execute("SELECT * FROM produtos WHERE id=? AND parceiro_id=?",(pid,u["id"])).fetchone()
    c.execute("UPDATE produtos SET stock=?, esgotado_manual=0, reabastecido=1 WHERE id=?",(novo,pid))
    avisos=c.execute("SELECT * FROM avisos WHERE produto_id=? ORDER BY id ASC LIMIT ?",(pid,novo)).fetchall()
    for av in avisos:
        notificar(av["cliente_id"],f"🔔 O produto {prod['nome_produto']} voltou ao estoque!")
        c.execute("DELETE FROM avisos WHERE id=?",(av["id"],))
    c.commit(); c.close(); return redirect("/painel-parceiro")
@app.route("/parceiro/esgotado/<int:pid>")
def parceiro_esgotado(pid):
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    c=db(); c.execute("UPDATE produtos SET esgotado_manual=1 WHERE id=? AND parceiro_id=?",(pid,u["id"])); c.commit(); c.close(); return redirect("/painel-parceiro")
@app.route("/parceiro/disponivel/<int:pid>")
def parceiro_disponivel(pid):
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    c=db(); c.execute("UPDATE produtos SET esgotado_manual=0 WHERE id=? AND parceiro_id=?",(pid,u["id"])); c.commit(); c.close(); return redirect("/painel-parceiro")
@app.route("/parceiro/rotular", methods=["POST"])
def parceiro_rotular():
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    c=db(); c.execute("UPDATE users SET rotulo=? WHERE id=?",(request.form["rotulo"],request.form["cliente_id"])); c.commit(); c.close(); return redirect("/painel-parceiro")
@app.route("/parceiro/remover-rotulo", methods=["POST"])
def parceiro_remover_rotulo():
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    c=db(); c.execute("UPDATE users SET rotulo='' WHERE id=?",(request.form["cliente_id"],)); c.commit(); c.close(); return redirect("/painel-parceiro")
@app.route("/denunciar-cliente", methods=["POST"])
def denunciar_cliente():
    u=session.get("user")
    if not u or u["role"]!="parceiro": return redirect("/login")
    c=db(); cli=c.execute("SELECT * FROM users WHERE id=?",(request.form["cliente_id"],)).fetchone(); c.execute("INSERT INTO denuncias(parceiro_id,parceiro_nome,cliente_id,cliente_nome,motivo,data) VALUES(?,?,?,?,?,?)",(u["id"],u["nome"],request.form["cliente_id"],cli["nome"] if cli else "",request.form["motivo"],datetime.now().strftime("%Y-%m-%d %H:%M"))); c.commit(); c.close(); notificar(1,f"⚠️ Denúncia: {u['nome']} denunciou {cli['nome'] if cli else ''} - {request.form['motivo']}"); return redirect("/painel-parceiro")
@app.route("/encomendar/<int:pid>", methods=["POST"])
def encomendar(pid):
    u=session.get("user")
    if not u: return redirect("/login")
    c=db(); p=c.execute("SELECT * FROM produtos WHERE id=?",(pid,)).fetchone()
    if p["stock"]<=0 or p["esgotado_manual"]: c.close(); return pagina_msg("Esgotado", "Este produto já esgotou.", "/loja", "Voltar à Loja")
    ultimo=(p["stock"]==1); metodo=request.form.get("metodo_pagamento","Pagar na Entrega")
    c.execute("INSERT INTO encomendas (cliente_id, cliente_nome, cliente_telefone, produto_id, produto_nome, parceiro_id, nome_loja, preco, qtd, pagamento, metodo_pagamento, provincia, bairro, data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(u["id"],u["nome"],u["telefone_ligacao"],p["id"],p["nome_produto"],p["parceiro_id"],p["nome_loja"],p["preco"],1,request.form.get("pagamento","Presencial"),metodo,u["provincia"],u["bairro"],datetime.now().strftime("%Y-%m-%d %H:%M")))
    c.execute("UPDATE produtos SET stock=stock-1 WHERE id=?",(pid,)); c.commit(); parc=c.execute("SELECT * FROM users WHERE id=?",(p["parceiro_id"],)).fetchone(); c.close()
    if parc and parc["bloqueado"]: notificar(parc["id"],"❓ Tens uma encomenda nova! Mas estás bloqueado.")
    elif parc: notificar(parc["id"],f"🔔 Encomenda nova - {p['nome_produto']} de {u['nome']}")
    dd=dict(p); dd["qtd"]=1
    return render_template_string(SUCESSO,nome=u["nome"],itens=[dd],total=p["preco"],metodo=metodo,ultimo=ultimo)
@app.route("/avise-me/<int:pid>", methods=["POST"])
def avise(pid):
    u=session.get("user")
    if not u: return redirect("/login")
    c=db(); ordem=c.execute("SELECT COUNT(*) FROM avisos WHERE produto_id=?",(pid,)).fetchone()[0]+1; c.execute("INSERT INTO avisos (cliente_id, produto_id, provincia, ordem) VALUES (?,?,?,?)",(u["id"],pid,u["provincia"],ordem)); c.commit(); c.close(); return pagina_msg("Vais ser avisado!", f"Estás na posição {ordem} da fila.", "/loja", "Voltar à Loja")
if __name__=="__main__":
    init(); print("✅ Ngola Store pronta - Admin: 900000000 / admin123"); app.run(debug=True, host="127.0.0.1", port=5000)
