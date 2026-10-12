import ast
import json
import logging
from datetime import datetime
from pathlib import Path
from functools import wraps
from flask import Flask, flash, redirect, render_template, request, send_file, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, text

import conexao.conexao_db as db
import estatistica_bo_final as ebo

app = Flask(__name__)
app.secret_key = "chave_secreta_super_segura_para_sessoes_trocar_em_producao"
logging.basicConfig(level=logging.INFO)

_engine_base = db.conexao_bd_postgres().engine

# Engine com reconexão automática
engine = create_engine(
    _engine_base.url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
)
_engine_base.dispose()

COLUNAS_BO = [
    'porto',
    'numero_bo',
    'topico',
    'data_ocorrencia',
    'titulo_ocorrencia',
    'classificacao_ocorrencia',
    'local_ocorrencia',
    'classificacao_local',
    'hora_ocorrencia',
    'nome_agente',
    'funcao_agente',
    'registro_agente',
    'testemunha1_nome',
    'testemunha1_pai',
    'testemunha1_mae',
    'testemunha1_data_nascimento',
    'testemunha1_cpf',
    'testemunha1_residencia',
    'testemunha1_bairro',
    'testemunha1_telefone',
    'testemunha2_nome',
    'testemunha2_pai',
    'testemunha2_mae',
    'testemunha2_data_nascimento',
    'testemunha2_cpf',
    'testemunha2_residencia',
    'testemunha2_bairro',
    'testemunha2_telefone',
    'narrativa_fatos',
    'dados_extraidos',
]

COLUNAS_ROIP = [
    "instalacao_roip_numero",
    "instalacao_razao_social",
    "instalacao_cnpj",
    "instalacao_endereco",
    "instalacao_municipio",
    "instalacao_uf",
    "instalacao_dentro_porto_organizado",
    "instalacao_nome_porto",
    "embarcacao_nome",
    "embarcacao_bandeira",
    "embarcacao_imo",
    "embarcacao_tipo",
    "embarcacao_ultimo_porto",
    "embarcacao_pais",
    "embarcacao_proximo_porto",
    "embarcacao_oficial_protecao",
    "embarcacao_comandante",
    "ocorrencia_local_descricao",
    "ocorrencia_tipo_descricao",
    "ocorrencia_identificacao_pessoas",
    "ocorrencia_identificacao_veiculos",
    "ocorrencia_narrativa",
    "fechamento_municipio",
    "fechamento_uf",
    "fechamento_data",
    "fechamento_horario",
    "fechamento_ssp_nome",
    "fechamento_ssp_cpf",
]


# --- DECORADOR DE SEGURANÇA PARA AUTENTICAÇÃO ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Por favor, faça login para acessar esta página.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def tratar_json_postgresql(campo_raw):
    if not campo_raw or not str(campo_raw).strip():
        return None
    campo_str = str(campo_raw).strip()
    try:
        dict_obj = ast.literal_eval(campo_str)
        if isinstance(dict_obj, dict):
            return json.dumps(dict_obj, ensure_ascii=False)
    except Exception:
        pass
    try:
        json_obj = json.loads(campo_str)
        return json.dumps(json_obj, ensure_ascii=False)
    except Exception:
        return json.dumps({"conteudo": campo_str}, ensure_ascii=False)


def verificar_coerencia_ano(numero_bo, data_ocorrencia):
    try:
        ano_bo = str(numero_bo).strip().split("/")[-1]
        ano_data = str(data_ocorrencia).strip()[:4]
        if ano_bo.isdigit() and len(ano_bo) == 4 and ano_data.isdigit() and ano_bo != ano_data:
            return (
                f"Atenção: o BO {numero_bo} possui data de ocorrência no ano {ano_data}. "
                f"Verifique se o ano da data está correto."
            )
    except Exception:
        pass
    return None


def buscar_inconsistencias_ano(porto=None):
    condicao_porto = ""
    params = {}
    if porto and porto != "TODOS":
        condicao_porto = "AND UPPER(TRIM(porto)) = :porto"
        params["porto"] = porto

    with engine.connect() as conn:
        query = text(f"""
            SELECT id, porto, numero_bo, data_ocorrencia, titulo_ocorrencia
            FROM gerops.registro_ocorrencias
            WHERE numero_bo IS NOT NULL
              AND data_ocorrencia IS NOT NULL
              {condicao_porto}
            ORDER BY id ASC
        """)
        registros = conn.execute(query, params).mappings().all()

    return [
        dict(r) for r in registros
        if verificar_coerencia_ano(r["numero_bo"], r["data_ocorrencia"])
    ]


def obter_classificacoes_unicas(porto=None):
    with engine.connect() as conn:
        if porto and porto != "TODOS":
            query = text("""
                SELECT DISTINCT classificacao_ocorrencia 
                FROM gerops.registro_ocorrencias 
                WHERE classificacao_ocorrencia IS NOT NULL 
                  AND TRIM(classificacao_ocorrencia) != ''
                  AND UPPER(TRIM(porto)) = :porto
                ORDER BY classificacao_ocorrencia ASC
            """)
            resultado = conn.execute(query, {"porto": porto}).scalars().all()
        else:
            query = text("""
                SELECT DISTINCT classificacao_ocorrencia 
                FROM gerops.registro_ocorrencias 
                WHERE classificacao_ocorrencia IS NOT NULL 
                  AND TRIM(classificacao_ocorrencia) != ''
                ORDER BY classificacao_ocorrencia ASC
            """)
            resultado = conn.execute(query).scalars().all()
        return resultado


def obter_portos_unicos_db():
    with engine.connect() as conn:
        query = text("""
            SELECT DISTINCT UPPER(TRIM(porto)) 
            FROM gerops.registro_ocorrencias 
            WHERE porto IS NOT NULL AND TRIM(porto) != ''
            ORDER BY 1 ASC
        """)
        return conn.execute(query).scalars().all()


def obter_razoes_sociais_roip_unicas():
    """Busca as razões sociais distintas cadastradas na tabela de ROIP de Itaguaí."""
    with engine.connect() as conn:
        query = text("""
            SELECT DISTINCT TRIM(instalacao_razao_social) 
            FROM gerops.roip_registros_itaguai 
            WHERE instalacao_razao_social IS NOT NULL 
              AND TRIM(instalacao_razao_social) != ''
            ORDER BY 1 ASC
        """)
        return conn.execute(query).scalars().all()


def extrair_dados_form_roip(form):
    dados = {}
    for col in COLUNAS_ROIP:
        val = form.get(col)
        if col == "instalacao_dentro_porto_organizado":
            dados[col] = str(val).lower() in ["true", "1", "on", "sim"]
        else:
            dados[col] = val.strip() if val and val.strip() else None
    return dados


# --- ROTAS DE AUTENTICAÇÃO ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not email or not senha:
            flash("Preencha todos os campos de login.", "danger")
            return render_template("login.html")

        with engine.connect() as conn:
            query = text("SELECT id, nome, email, senha_hash, ativo FROM gerops.usuarios WHERE email = :email")
            usuario = conn.execute(query, {"email": email}).mappings().first()

        if usuario and usuario["ativo"] and check_password_hash(usuario["senha_hash"], senha):
            session.clear()
            session.permanent = True
            session["user_id"] = usuario["id"]
            session["user_name"] = usuario["nome"]
            session["user_email"] = usuario["email"]
            flash(f"Bem-vindo(a), {usuario['nome']}!", "success")
            return redirect(url_for("index"))
        else:
            flash("E-mail ou senha incorretos, ou conta desativada.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada com segurança.", "info")
    return redirect(url_for("login"))


# --- MENU INICIAL (Protegido) ---

@app.route("/")
@login_required
def index():
    return render_template("index.html")


# --- MÓDULO DE GESTÃO DE OCORRÊNCIAS (CRUD BO) ---

@app.route("/ocorrencias")
@login_required
def modulo_ocorrencias():
    portos = obter_portos_unicos_db()
    porto_selecionado = request.args.get("porto", "TODOS").upper()
    classificacao_selecionada = request.args.get("classificacao", "TODAS")

    classificacoes = obter_classificacoes_unicas(porto_selecionado)

    condicoes = []
    params = {}

    if porto_selecionado and porto_selecionado != "TODOS":
        condicoes.append("UPPER(TRIM(porto)) = :porto")
        params["porto"] = porto_selecionado

    if classificacao_selecionada and classificacao_selecionada != "TODAS":
        condicoes.append("classificacao_ocorrencia = :classificacao")
        params["classificacao"] = classificacao_selecionada

    where_clause = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

    with engine.connect() as conn:
        query = text(f"""
            SELECT id, porto, numero_bo, data_ocorrencia, titulo_ocorrencia, local_ocorrencia, classificacao_ocorrencia 
            FROM gerops.registro_ocorrencias 
            {where_clause}
            ORDER BY id ASC
        """)
        registros = conn.execute(query, params).mappings().all()

    inconsistencias = buscar_inconsistencias_ano(porto_selecionado)

    return render_template(
        "ocorrencias.html", 
        registros=registros, 
        portos=portos, 
        porto_atual=porto_selecionado,
        classificacoes=classificacoes,
        classificacao_atual=classificacao_selecionada,
        inconsistencias=inconsistencias
    )


@app.route("/novo", methods=["GET", "POST"])
@login_required
def criar():
    if request.method == "POST":
        dados = {col: request.form.get(col) or None for col in COLUNAS_BO}
        dados["dados_extraidos"] = tratar_json_postgresql(
            dados.get("dados_extraidos")
        )

        colunas_sql = ", ".join(COLUNAS_BO)
        params_sql = ", ".join([f":{col}" for col in COLUNAS_BO])

        with engine.begin() as conn:
            query = text(f"""
                INSERT INTO gerops.registro_ocorrencias ({colunas_sql})
                VALUES ({params_sql})
            """)
            conn.execute(query, dados)

        flash("Ocorrência cadastrada com sucesso!", "success")
        aviso = verificar_coerencia_ano(dados.get("numero_bo"), dados.get("data_ocorrencia"))
        if aviso:
            flash(aviso, "warning")
        return redirect(url_for("modulo_ocorrencias"))

    classificacoes = obter_classificacoes_unicas()
    return render_template("form.html", registro=None, classificacoes=classificacoes)


@app.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar(id):
    if request.method == "POST":
        dados = {col: request.form.get(col) or None for col in COLUNAS_BO}
        dados["dados_extraidos"] = tratar_json_postgresql(
            dados.get("dados_extraidos")
        )
        dados["id"] = id

        set_sql = ", ".join([f"{col} = :{col}" for col in COLUNAS_BO])

        with engine.begin() as conn:
            query = text(f"""
                UPDATE gerops.registro_ocorrencias
                SET {set_sql}
                WHERE id = :id
            """)
            conn.execute(query, dados)

        flash("Registro atualizado com sucesso!", "success")
        aviso = verificar_coerencia_ano(dados.get("numero_bo"), dados.get("data_ocorrencia"))
        if aviso:
            flash(aviso, "warning")
        return redirect(url_for("modulo_ocorrencias"))

    with engine.connect() as conn:
        query = text("SELECT * FROM gerops.registro_ocorrencias WHERE id = :id")
        registro = conn.execute(query, {"id": id}).mappings().first()

    classificacoes = obter_classificacoes_unicas()
    return render_template("form.html", registro=registro, classificacoes=classificacoes)


@app.route("/excluir/<int:id>", methods=["POST"])
@login_required
def excluir(id):
    with engine.begin() as conn:
        query = text("DELETE FROM gerops.registro_ocorrencias WHERE id = :id")
        conn.execute(query, {"id": id})
    flash("Registro excluído com sucesso!", "success")
    return redirect(url_for("modulo_ocorrencias"))


# --- MÓDULO NOVO: GESTÃO DE ROIP (Itaguaí) ---

@app.route("/roip")
@login_required
def roip_index():
    razoes_sociais = obter_razoes_sociais_roip_unicas()
    razao_selecionada = request.args.get("razao_social", "TODAS")

    condicoes = []
    params = {}

    if razao_selecionada and razao_selecionada != "TODAS":
        condicoes.append("TRIM(instalacao_razao_social) = :razao_social")
        params["razao_social"] = razao_selecionada

    where_clause = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

    with engine.connect() as conn:
        query = text(f"""
            SELECT id, instalacao_roip_numero, instalacao_razao_social, 
                   ocorrencia_tipo_descricao, ocorrencia_local_descricao, 
                   fechamento_data, fechamento_ssp_nome 
            FROM gerops.roip_registros_itaguai 
            {where_clause}
            ORDER BY id ASC
        """)
        registros = conn.execute(query, params).mappings().all()

    return render_template(
        "roip_index.html", 
        registros=registros, 
        razoes_sociais=razoes_sociais, 
        razao_atual=razao_selecionada
    )


@app.route("/roip/novo", methods=["GET", "POST"])
@login_required
def roip_criar():
    if request.method == "POST":
        dados = extrair_dados_form_roip(request.form)

        colunas_sql = ", ".join(COLUNAS_ROIP)
        params_sql = ", ".join([f":{col}" for col in COLUNAS_ROIP])

        with engine.begin() as conn:
            query = text(f"""
                INSERT INTO gerops.roip_registros_itaguai ({colunas_sql})
                VALUES ({params_sql})
            """)
            conn.execute(query, dados)

        flash("Ocorrência ROIP cadastrada com sucesso!", "success")
        return redirect(url_for("roip_index"))

    return render_template("form_roip.html", registro=None)


@app.route("/roip/editar/<int:id>", methods=["GET", "POST"])
@login_required
def roip_editar(id):
    if request.method == "POST":
        dados = extrair_dados_form_roip(request.form)
        dados["id"] = id

        set_sql = ", ".join([f"{col} = :{col}" for col in COLUNAS_ROIP])

        with engine.begin() as conn:
            query = text(f"""
                UPDATE gerops.roip_registros_itaguai
                SET {set_sql}
                WHERE id = :id
            """)
            conn.execute(query, dados)

        flash("Registro ROIP atualizado com sucesso!", "success")
        return redirect(url_for("roip_index"))

    with engine.connect() as conn:
        query = text("SELECT * FROM gerops.roip_registros_itaguai WHERE id = :id")
        registro = conn.execute(query, {"id": id}).mappings().first()

    return render_template("form_roip.html", registro=registro)


@app.route("/roip/excluir/<int:id>", methods=["POST"])
@login_required
def roip_excluir(id):
    with engine.begin() as conn:
        query = text("DELETE FROM gerops.roip_registros_itaguai WHERE id = :id")
        conn.execute(query, {"id": id})
    flash("Registro ROIP excluído com sucesso!", "success")
    return redirect(url_for("roip_index"))


# --- MÓDULO 1: BANCO DE DADOS E CONEXÃO ---

@app.route("/banco")
@login_required
def modulo_banco():
    status_conexao = False
    erro_mensagem = None
    tabelas = []

    try:
        with engine.connect() as conn:
            status_conexao = True
            result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='gerops'"))
            tabelas = [row[0] for row in result]
    except Exception as e:
        erro_mensagem = str(e)

    return render_template("banco.html", status=status_conexao, erro=erro_mensagem, tabelas=tabelas)


# --- MÓDULO 2: ESTATÍSTICA E DASHBOARD DE BOs ---

@app.route("/dashboard")
@login_required
def modulo_dashboard():
    try:
        df_bruto = ebo.carregar_dados()
        df_completo = ebo.tratar_dados(df_bruto)

        portos_unicos = ebo.obter_portos_unicos(df_completo)
        porto_default = "RIO DE JANEIRO" if "RIO DE JANEIRO" in portos_unicos else (portos_unicos[0] if portos_unicos else "RIO DE JANEIRO")
        porto_selecionado = request.args.get("porto", porto_default).upper()

        if "_porto" in df_completo.columns:
            df_porto = df_completo[
                df_completo["_porto"].fillna("").astype(str).str.strip().str.upper()
                == porto_selecionado.strip().upper()
            ].copy()
        else:
            df_porto = df_completo.copy()

        periodos = ebo.determinar_periodos(df_porto)
        periodos_str = [p.strftime("%Y-%m") for p in periodos]

        periodo_solicitado = request.args.get("periodo")

        if periodo_solicitado in periodos_str:
            periodo_selecionado = periodo_solicitado
        elif periodos_str:
            periodo_selecionado = periodos_str[-1]
        else:
            periodo_selecionado = "Sem Registros"

        if periodo_selecionado != "Sem Registros":
            df_mes = df_porto[
                df_porto["_periodo"].dt.strftime("%Y-%m") == periodo_selecionado
            ].copy()
        else:
            df_mes = df_porto.iloc[0:0].copy()

        total_ocorrencias = len(df_porto)
        total_mes = len(df_mes)

        df_resumo = ebo.gerar_resumo_mensal(df_porto, periodos)
        df_class_todo = ebo.agrupar_por_campo(df_porto, "_classificacao_ocorrencia", "Classificação da Ocorrência")
        df_local_todo = ebo.agrupar_por_campo(df_porto, "_classificacao_local", "Classificação do Local")
        df_class_mes = ebo.agrupar_por_campo(df_mes, "_classificacao_ocorrencia", "Classificação da Ocorrência")

        chart_labels = df_class_todo["Classificação da Ocorrência"].tolist()[:10] if not df_class_todo.empty else []
        chart_values = df_class_todo["Quantidade"].tolist()[:10] if not df_class_todo.empty else []

        total_inconsistencias = len(buscar_inconsistencias_ano(porto_selecionado))

        return render_template(
            "dashboard.html",
            total_inconsistencias=total_inconsistencias,
            total_ocorrencias=total_ocorrencias,
            total_mes=total_mes,
            portos=portos_unicos,
            porto_atual=porto_selecionado,
            periodo_atual=periodo_selecionado,
            periodos=periodos_str,
            resumo_mensal=df_resumo.to_dict(orient="records") if not df_resumo.empty else [],
            class_todo=df_class_todo.to_dict(orient="records") if not df_class_todo.empty else [],
            local_todo=df_local_todo.to_dict(orient="records") if not df_local_todo.empty else [],
            class_mes=df_class_mes.to_dict(orient="records") if not df_class_mes.empty else [],
            chart_labels=chart_labels,
            chart_values=chart_values
        )
    except Exception as e:
        logging.error(f"Erro no Módulo Dashboard: {e}")
        return render_template("dashboard.html", erro=str(e))


@app.route("/empresas")
@login_required
def modulo_empresas():
    try:
        df_bruto = ebo.carregar_dados()
        df = ebo.tratar_dados(df_bruto)

        porto_selecionado = request.args.get("porto", "RIO DE JANEIRO").upper()
        if "_porto" in df.columns:
            df = df[df["_porto"] == porto_selecionado]

        empresas_por_classificacao = {}
        for cat in ebo.CONFIG["classificacoes_empresas"]:
            df_emp = ebo.agrupar_empresas_por_classificacao(df, cat)
            empresas_por_classificacao[cat] = df_emp.to_dict(orient="records")

        return render_template("detalhe_empresas.html", dados_empresas=empresas_por_classificacao, porto_atual=porto_selecionado)
    except Exception as e:
        logging.error(f"Erro no Módulo Empresas: {e}")
        return redirect(url_for("modulo_dashboard"))


@app.route("/download-pdf")
@login_required
def download_pdf():
    porto_selecionado = request.args.get("porto", "RIO DE JANEIRO").upper()
    try:
        df_bruto = ebo.carregar_dados()
        df = ebo.tratar_dados(df_bruto)

        if "_porto" in df.columns:
            df_porto = df[df["_porto"] == porto_selecionado]
        else:
            df_porto = df

        periodos = ebo.determinar_periodos(df_porto)

        pasta_saida = Path(ebo.CONFIG["diretorio_saida"]).resolve()
        pasta_saida.mkdir(parents=True, exist_ok=True)

        nome_arquivo_sanitizado = porto_selecionado.replace(" ", "_")
        caminho_pdf = pasta_saida / f"Relatorio_Ocorrencias_{nome_arquivo_sanitizado}.pdf"

        ebo.gerar_pdf_modelo(df_porto, periodos, caminho_pdf, porto_nome=porto_selecionado)

        if not caminho_pdf.exists():
            raise FileNotFoundError(f"Arquivo PDF não foi encontrado em: {caminho_pdf}")

        return send_file(
            str(caminho_pdf),
            as_attachment=True,
            download_name=f"Relatorio_{nome_arquivo_sanitizado}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        logging.error(f"Erro ao gerar PDF: {e}")
        flash(f"Erro ao gerar PDF: {str(e)}", "danger")
        return redirect(url_for("modulo_dashboard", porto=porto_selecionado))


# --- MÓDULO 3: INDICADORES ISP (BASE EVOLUTIVA CISP) ---

CISP_ISP = 50
ANO_INICIAL_ISP = 2016


def _para_int(valor):
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def executar_consulta_isp():
    sql_ultimo_mes = text("""
        SELECT
            cisp AS "Delegacia",
            munic AS "Município",
            ano AS "Ano",
            mes AS "Mês",
            (COALESCE(roubo_veiculo, 0) + COALESCE(roubo_carga, 0)) AS "Total de Roubos",
            COALESCE(roubo_veiculo, 0) AS "Roubo de Veículo",
            COALESCE(roubo_carga, 0) AS "Roubo de Cargas",
            (COALESCE(furto_veiculos, 0) + COALESCE(outros_furtos, 0)) AS "Total de Furtos",
            COALESCE(furto_veiculos, 0) AS "Furto de Veículo",
            COALESCE(outros_furtos, 0) AS "Outros Furtos",
            (COALESCE(apreensao_drogas, 0) + COALESCE(trafico_drogas, 0) + COALESCE(cmp, 0)) AS "Total Produtividade Policial",
            COALESCE(apreensao_drogas, 0) AS "Apreensão de Drogas",
            COALESCE(trafico_drogas, 0) AS "Tráfico de Drogas",
            COALESCE(cmp, 0) AS "Mandado de Prisão",
            COALESCE(registro_ocorrencias, 0) AS "Total de Ocorrências"
        FROM gerops.base_dp_evolucao_mensal_cisp
        WHERE cisp = :cisp AND ano >= :ano_inicial
        ORDER BY ano DESC, mes DESC
        LIMIT 1;
    """)

    sql_acumulado = text("""
        SELECT
            COUNT(*) as total_meses,
            SUM(COALESCE(roubo_veiculo, 0) + COALESCE(roubo_carga, 0)) AS acumulado_roubos,
            SUM(COALESCE(furto_veiculos, 0) + COALESCE(outros_furtos, 0)) AS acumulado_furtos,
            SUM(COALESCE(apreensao_drogas, 0) + COALESCE(trafico_drogas, 0) + COALESCE(cmp, 0)) AS acumulado_produtividade,
            SUM(COALESCE(registro_ocorrencias, 0)) AS acumulado_total_ocorrencias
        FROM gerops.base_dp_evolucao_mensal_cisp
        WHERE cisp = :cisp AND ano >= :ano_inicial;
    """)

    params = {"cisp": CISP_ISP, "ano_inicial": ANO_INICIAL_ISP}
    with engine.connect() as conn:
        res_ultimo = conn.execute(sql_ultimo_mes, params).mappings().fetchone()
        res_acumulado = conn.execute(sql_acumulado, params).mappings().fetchone()

    ultimo_mes = dict(res_ultimo) if res_ultimo else None
    acumulado = dict(res_acumulado) if res_acumulado else None

    if ultimo_mes:
        for chave, valor in ultimo_mes.items():
            if chave != "Município":
                ultimo_mes[chave] = _para_int(valor)
    if acumulado:
        acumulado = {chave: _para_int(valor) for chave, valor in acumulado.items()}

    return ultimo_mes, acumulado


@app.route("/isp")
@login_required
def modulo_isp():
    try:
        ultimo_mes, acumulado = executar_consulta_isp()

        if not ultimo_mes or not acumulado or not acumulado["total_meses"]:
            return render_template(
                "dashboard_isp.html",
                erro="Nenhum registro encontrado em gerops.base_dp_evolucao_mensal_cisp "
                     f"para a CISP {CISP_ISP}."
            )

        total_oc = ultimo_mes["Total de Ocorrências"] or 1
        demais_oc = ultimo_mes["Total de Ocorrências"] - (ultimo_mes["Total de Roubos"] + ultimo_mes["Total de Furtos"])

        tot_ac = acumulado["acumulado_total_ocorrencias"] or 1
        tot_meses = acumulado["total_meses"] or 1

        ac_roubos = acumulado["acumulado_roubos"]
        ac_furtos = acumulado["acumulado_furtos"]
        ac_prod = acumulado["acumulado_produtividade"]
        ac_demais = tot_ac - (ac_roubos + ac_furtos)

        metricas = {
            "ultimo_mes": ultimo_mes,
            "ano_inicial": ANO_INICIAL_ISP,
            "perc_rv": round((ultimo_mes["Roubo de Veículo"] / total_oc) * 100, 1),
            "perc_rc": round((ultimo_mes["Roubo de Cargas"] / total_oc) * 100, 1),
            "perc_fv": round((ultimo_mes["Furto de Veículo"] / total_oc) * 100, 1),
            "perc_of": round((ultimo_mes["Outros Furtos"] / total_oc) * 100, 1),
            "demais_oc": demais_oc,
            "perc_demais": round((demais_oc / total_oc) * 100, 1),
            "acumulado": {
                "tot_ac": acumulado["acumulado_total_ocorrencias"],
                "ac_roubos": ac_roubos, "perc_ac_roubos": round((ac_roubos / tot_ac) * 100, 1), "media_roubos": round(ac_roubos / tot_meses, 1),
                "ac_furtos": ac_furtos, "perc_ac_furtos": round((ac_furtos / tot_ac) * 100, 1), "media_furtos": round(ac_furtos / tot_meses, 1),
                "ac_prod": ac_prod, "perc_ac_prod": round((ac_prod / tot_ac) * 100, 1), "media_prod": round(ac_prod / tot_meses, 1),
                "ac_demais": ac_demais, "perc_ac_demais": round((ac_demais / tot_ac) * 100, 1), "media_demais": round(ac_demais / tot_meses, 1),
                "media_total": round(tot_ac / tot_meses, 1), "tot_meses": acumulado["total_meses"]
            }
        }

        return render_template("dashboard_isp.html", m=metricas)
    except Exception as e:
        logging.error(f"Erro no Módulo ISP: {e}")
        return render_template("dashboard_isp.html", erro=str(e))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)