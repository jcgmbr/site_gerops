import re
import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import conexao.conexao_db as db

warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURAÇÃO DE CAMINHOS E IMAGENS
# ============================================================

CONFIG = {
    "ano_relatorio": None,
    "mes_relatorio": None,
    "diretorio_saida": "relatorios",
    "caminho_logo_esquerda": Path("imagens") / "portos_rio.jpg",
    "caminho_logo_direita": Path("imagens") / "logo-guarda.jpg",
    "caminho_rodape": Path("imagens") / "rodape.jpg",
    "campo_data": "data_ocorrencia",
    "campo_hora": "hora_ocorrencia",
    "campo_tipo_original": "titulo_ocorrencia",
    "campo_local_original": "local_ocorrencia",
    "campo_classificacao_ocorrencia": "classificacao_ocorrencia",
    "campo_classificacao_local": "classificacao_local",
    "campo_porto": "porto",
    "campo_topico": "topico",
    "valores_nulos": [
        "", "-", "--", "N/A", "NA", "NÃO INFORMADO",
        "NAO INFORMADO", "SEM INFORMAÇÃO", "SEM INFORMACAO",
        "NULL", "NONE", "NAN"
    ],
    "classificacoes_empresas": ["ESTACIONAMENTO IRREGULAR", "INCÊNDIO", "DESACATO"]
}

MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

# ============================================================
# UTILITÁRIOS E TRATAMENTO DE DADOS
# ============================================================

def obter_classificacoes_com_empresas(df):
    if df.empty or "_empresa_envolvida" not in df.columns:
        return []
    
    mask = df["_empresa_envolvida"].apply(lambda x: isinstance(x, list) and len(x) > 0)
    classificacoes = (
        df.loc[mask, "_classificacao_ocorrencia"]
        .dropna()
        .unique()
        .tolist()
    )
    return sorted(classificacoes)

def obter_portos_unicos(df):
    """Extrai e retorna uma lista ordenada com os valores únicos do campo porto."""
    campo_porto = CONFIG["campo_porto"]
    if campo_porto in df.columns:
        portos = df[campo_porto].dropna().astype(str).str.strip().str.upper().unique()
        portos_validos = sorted([p for p in portos if p not in CONFIG["valores_nulos"]])
        if portos_validos:
            return portos_validos
    return ["RIO DE JANEIRO"]

def normalizar_texto(valor):
    if pd.isna(valor):
        return np.nan
    valor = str(valor).strip()
    if valor.upper() in CONFIG["valores_nulos"]:
        return np.nan
    return re.sub(r"\s+", " ", valor)

def normalizar_classificacao(valor):
    valor = normalizar_texto(valor)
    if pd.isna(valor):
        return "NÃO INFORMADO"
    return valor.upper()

def formatar_periodo(periodo):
    return f"{MESES[int(periodo.month)]}/{int(periodo.year)}"

def extrair_empresa_envolvida(val):
    if pd.isna(val) or val is None:
        return []
    if isinstance(val, str):
        val_clean = val.strip()
        if not val_clean:
            return []
        try:
            val = json.loads(val_clean)
        except Exception:
            return [e.strip() for e in val_clean.split(",") if e.strip()]
    if isinstance(val, dict):
        empresa = val.get("empresa_envolvida")
        if empresa and str(empresa).strip():
            return [e.strip() for e in str(empresa).split(",") if e.strip()]
    return []

# ============================================================
# CARREGAMENTO E PROCESSAMENTO
# ============================================================

def carregar_dados():
    bos = pd.read_sql('SELECT * FROM gerops.registro_ocorrencias', con=db.conexao_bd_postgres().engine)
    bos.columns = [str(c).strip() for c in bos.columns]
    return bos

def tratar_dados(df):
    df = df.copy()
    for coluna in df.select_dtypes(include=["object", "string"]).columns:
        if coluna != "dados_extraidos":
            df[coluna] = df[coluna].apply(normalizar_texto)

    df[CONFIG["campo_data"]] = pd.to_datetime(df[CONFIG["campo_data"]], errors="coerce")
    
    # Remove registos sem data válida antes de prosseguir
    df = df.dropna(subset=[CONFIG["campo_data"]])

    df["_classificacao_ocorrencia"] = df[CONFIG["campo_classificacao_ocorrencia"]].apply(normalizar_classificacao)
    df["_classificacao_local"] = df[CONFIG["campo_classificacao_local"]].apply(normalizar_classificacao)
    df["_periodo"] = df[CONFIG["campo_data"]].dt.to_period("M")
    
    campo_porto = CONFIG["campo_porto"]
    if campo_porto in df.columns:
        # Campo auxiliar usado pelos filtros do dashboard.
        # Mantém o mesmo padrão usado em obter_portos_unicos().
        df["_porto"] = (
            df[campo_porto]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .str.upper()
        )
        df.loc[df["_porto"].isin(CONFIG["valores_nulos"]) | (df["_porto"] == ""), "_porto"] = np.nan
    else:
        df["_porto"] = "RIO DE JANEIRO"

    if "dados_extraidos" in df.columns:
        df["_empresa_envolvida"] = df["dados_extraidos"].apply(extrair_empresa_envolvida)
    else:
        df["_empresa_envolvida"] = df.apply(lambda _: [], axis=1)

    return df

def determinar_periodos(df):
    """
    Retorna SOMENTE os períodos que possuem pelo menos uma ocorrência
    real no DataFrame recebido.

    Importante:
    - Não cria períodos intermediários;
    - Não usa intervalo entre a primeira e a última ocorrência;
    - Ignora datas inválidas/nulas;
    - Remove duplicidades;
    - Funciona somente sobre os registros que já foram filtrados pelo porto.
    """
    if df is None or df.empty or "_periodo" not in df.columns:
        return []

    periodos = (
        df["_periodo"]
        .dropna()
        .astype("period[M]")
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    return periodos

# ============================================================
# AGRUPAMENTOS E ESTATÍSTICAS
# ============================================================

def agrupar_por_campo(df, campo, nome_categoria):
    if df.empty:
        return pd.DataFrame(columns=["Ranking", nome_categoria, "Quantidade", "Percentual"])

    dados = df[campo].fillna("NÃO INFORMADO").astype(str).str.strip()
    tabela = (
        dados.value_counts(dropna=False)
        .rename_axis(nome_categoria)
        .reset_index(name="Quantidade")
    )

    tabela = tabela.sort_values(
        by=["Quantidade", nome_categoria],
        ascending=[False, True],
        kind="stable"
    ).reset_index(drop=True)

    total = int(tabela["Quantidade"].sum())
    if total > 0:
        tabela["Percentual"] = (tabela["Quantidade"] / total * 100).round().astype(int).astype(str) + "%"
    else:
        tabela["Percentual"] = "0%"

    tabela["Ranking"] = np.arange(1, len(tabela) + 1)

    return tabela[["Ranking", nome_categoria, "Quantidade", "Percentual"]]

def gerar_resumo_mensal(df, periodos):
    resultados = []
    acumulado = 0
    for periodo in periodos:
        qtd_mes = len(df[df["_periodo"] == periodo])
        if qtd_mes > 0:  # Garante que só inclui se houver ocorrências
            acumulado += qtd_mes
            resultados.append({
                "Período": formatar_periodo(periodo),
                "Ocorrências no Mês": qtd_mes,
                "Ocorrências Acumuladas": acumulado
            })
    return pd.DataFrame(resultados)

def agrupar_empresas_por_classificacao(df, classificacao):
    df_filtrado = df[
        (df["_classificacao_ocorrencia"] == classificacao.upper()) &
        (df["_empresa_envolvida"].apply(lambda x: isinstance(x, list) and len(x) > 0))
    ].copy()

    if df_filtrado.empty:
        return pd.DataFrame(columns=["Ranking", "Empresa Envolvida", "Quantidade", "Percentual"])

    df_exploded = df_filtrado.explode("_empresa_envolvida")
    df_exploded = df_exploded[
        df_exploded["_empresa_envolvida"].notna() & 
        (df_exploded["_empresa_envolvida"] != "")
    ]

    return agrupar_por_campo(df_exploded, "_empresa_envolvida", "Empresa Envolvida")

# ============================================================
# CONSTRUÇÃO DAS TABELAS PDF
# ============================================================

def montar_tabela_pdf(df, col_widths=None):
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors

    if df is None or df.empty:
        return None
    
    dados_df = df.copy()

    style_header_left = ParagraphStyle('TH_Left', fontName='Arial-Bold', fontSize=8, leading=10, textColor=colors.white, alignment=0)
    style_header_center = ParagraphStyle('TH_Center', fontName='Arial-Bold', fontSize=8, leading=10, textColor=colors.white, alignment=1)
    
    style_cell_left = ParagraphStyle('TD_Left', fontName='Arial', fontSize=8, leading=10, textColor=colors.HexColor("#000000"), alignment=0)
    style_cell_center = ParagraphStyle('TD_Center', fontName='Arial', fontSize=8, leading=10, textColor=colors.HexColor("#000000"), alignment=1)

    dados = []
    
    row_header = []
    for idx, col in enumerate(dados_df.columns):
        if idx == 0 and col not in ["Ranking", "Período"]:
            row_header.append(Paragraph(str(col), style_header_left))
        elif col in ["Classificação da Ocorrência", "Classificação do Local", "Empresa Envolvida"]:
            row_header.append(Paragraph(str(col), style_header_left))
        else:
            row_header.append(Paragraph(str(col), style_header_center))
    dados.append(row_header)

    for row in dados_df.values:
        row_cells = []
        for idx, (col_name, val) in enumerate(zip(dados_df.columns, row)):
            val_str = str(val)
            if col_name in ["Classificação da Ocorrência", "Classificação do Local", "Empresa Envolvida"]:
                row_cells.append(Paragraph(val_str, style_cell_left))
            elif idx == 0 and col_name not in ["Ranking"]:
                row_cells.append(Paragraph(val_str, style_cell_left))
            else:
                row_cells.append(Paragraph(val_str, style_cell_center))
        dados.append(row_cells)

    tabela = Table(dados, colWidths=col_widths, repeatRows=1, hAlign='CENTER')
    
    estilo_tabela = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    tabela.setStyle(TableStyle(estilo_tabela))
    return tabela

# ============================================================
# GERADOR DO PDF COMPLETO
# ============================================================

def desenhar_rodape_pagina(canvas_obj, doc):
    from reportlab.lib.units import cm
    
    caminho_rodape = CONFIG["caminho_rodape"]
    if caminho_rodape.exists():
        canvas_obj.saveState()
        canvas_obj.drawImage(
            str(caminho_rodape),
            x=2.5 * cm,
            y=0.6 * cm,
            width=17.7 * cm,
            height=0.9 * cm,
            preserveAspectRatio=False,
            mask='auto'
        )
        canvas_obj.restoreState()

def gerar_pdf_modelo(df_completo, periodos, caminho_saida, porto_nome="RIO DE JANEIRO"):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    try:
        pdfmetrics.registerFont(TTFont('Courier-Bold', 'courbd.ttf'))
        pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
        pdfmetrics.registerFont(TTFont('Arial-Bold', 'arialbd.ttf'))
        pdfmetrics.registerFont(TTFont('Arial-Italic', 'ariali.ttf'))
    except Exception:
        pdfmetrics.registerFont(TTFont('Courier-Bold', '/usr/share/fonts/truetype/msttcorefonts/Courier_New_Bold.ttf'))
        pdfmetrics.registerFont(TTFont('Arial', '/usr/share/fonts/truetype/msttcorefonts/Arial.ttf'))
        pdfmetrics.registerFont(TTFont('Arial-Bold', '/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf'))
        pdfmetrics.registerFont(TTFont('Arial-Italic', '/usr/share/fonts/truetype/msttcorefonts/Arial_Italic.ttf'))

    doc = SimpleDocTemplate(
        str(caminho_saida),
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=2.0 * cm
    )

    style_courier_header = ParagraphStyle('CourierHeader', fontName='Courier-Bold', fontSize=11, leading=13, alignment=1, textColor=colors.black)
    style_report_title = ParagraphStyle('ReportTitle', fontName='Arial-Bold', fontSize=13, leading=16, alignment=1, textColor=colors.black)
    style_period_sub = ParagraphStyle('PeriodSub', fontName='Arial', fontSize=11, leading=13, alignment=2, textColor=colors.black)
    style_section_title = ParagraphStyle('SectionTitle', fontName='Arial-Bold', fontSize=12, leading=15, alignment=0, textColor=colors.black, spaceBefore=10, spaceAfter=6)
    style_table_subtitle = ParagraphStyle('TableSubTitle', fontName='Arial-Bold', fontSize=10, leading=12, alignment=0, textColor=colors.HexColor("#2C4A6F"), spaceBefore=4, spaceAfter=6)

    style_signature_date = ParagraphStyle('SigDate', fontName='Arial', fontSize=10, leading=13, alignment=0)
    style_signature_name = ParagraphStyle('SigName', fontName='Arial-Italic', fontSize=10, leading=13, alignment=1)
    style_signature_role = ParagraphStyle('SigRole', fontName='Arial', fontSize=10, leading=13, alignment=1)

    elementos = []
    
    # Recalcula e valida estritamente os períodos existentes no df_completo já filtrado do porto
    periodos_reais = determinar_periodos(df_completo)
    periodo_ultimo = formatar_periodo(periodos_reais[-1]) if periodos_reais else "Sem Registros"

    # --- CABEÇALHO ---
    col_centro = [
        Paragraph("SUPERINTENDÊNCIA DA GUARDA PORTUÁRIA", style_courier_header),
        Paragraph("GERÊNCIA DE OPERAÇÕES DE SEGURANÇA", style_courier_header),
        Paragraph("- GEROPS -", style_courier_header)
    ]

    img_esq = Image(str(CONFIG["caminho_logo_esquerda"]), width=3.8 * cm, height=2.0 * cm) if CONFIG["caminho_logo_esquerda"].exists() else Paragraph("", style_courier_header)
    img_dir = Image(str(CONFIG["caminho_logo_direita"]), width=2.4 * cm, height=2.5 * cm) if CONFIG["caminho_logo_direita"].exists() else Paragraph("", style_courier_header)

    header_table = Table([[img_esq, col_centro, img_dir]], colWidths=[4.0 * cm, 10.0 * cm, 4.0 * cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))

    elementos.append(header_table)
    elementos.append(Spacer(1, 0.4 * cm))

    elementos.append(Paragraph("RELATÓRIO ESTATÍSTICO OCORRÊNCIAS DE SEGURANÇA", style_report_title))
    elementos.append(Spacer(1, 0.1 * cm))
    elementos.append(Paragraph(f"Porto: {porto_nome.title()}", style_report_title))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph(f"Período final: {periodo_ultimo}", style_period_sub))
    elementos.append(Spacer(1, 0.3 * cm))

    # --- SEÇÃO 1 ---
    elementos.append(Paragraph("1 - RESUMO MENSAL E ACUMULADO", style_section_title))
    elementos.append(Spacer(1, 0.5 * cm))
    df_resumo = gerar_resumo_mensal(df_completo, periodos_reais)
    t_resumo = montar_tabela_pdf(df_resumo, col_widths=[3.0 * cm, 4.5 * cm, 4.5 * cm])
    if t_resumo:
        elementos.append(t_resumo)
    elementos.append(Spacer(1, 0.5 * cm))

    # --- SEÇÃO 2 ---
    elementos.append(Paragraph("2 - ESTATÍSTICAS DE TODO O PERÍODO", style_section_title))
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(Paragraph("Ocorrências por classificação", style_table_subtitle))
    elementos.append(Spacer(1, 0.5 * cm))
    df_class_todo = agrupar_por_campo(df_completo, "_classificacao_ocorrencia", "Classificação da Ocorrência")
    t_class_todo = montar_tabela_pdf(df_class_todo, col_widths=[2.0 * cm, 5.5 * cm, 2.3 * cm, 2.2 * cm])
    if t_class_todo:
        elementos.append(t_class_todo)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(PageBreak())
    elementos.append(header_table)
    elementos.append(Spacer(1, 0.4 * cm))

    elementos.append(Paragraph("Ocorrências por local", style_table_subtitle))
    elementos.append(Spacer(1, 0.5 * cm))
    df_local_todo = agrupar_por_campo(df_completo, "_classificacao_local", "Classificação do Local")
    t_local_todo = montar_tabela_pdf(df_local_todo, col_widths=[2.0 * cm, 5.5 * cm, 2.3 * cm, 2.2 * cm])
    if t_local_todo:
        elementos.append(t_local_todo)
    elementos.append(Spacer(1, 0.5 * cm))

    # --- SEÇÃO 3 ---
    elementos.append(Paragraph(f"3 - ESTATÍSTICAS DE {periodo_ultimo.upper()}", style_section_title))
    
    if periodos_reais:
        df_mes_atual = df_completo[df_completo["_periodo"] == periodos_reais[-1]]
    else:
        df_mes_atual = df_completo.iloc[0:0]

    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(Paragraph("Ocorrências por classificação", style_table_subtitle))
    elementos.append(Spacer(1, 0.5 * cm))
    df_class_mes = agrupar_por_campo(df_mes_atual, "_classificacao_ocorrencia", "Classificação da Ocorrência")
    t_class_mes = montar_tabela_pdf(df_class_mes, col_widths=[2.0 * cm, 5.5 * cm, 2.3 * cm, 2.2 * cm])
    if t_class_mes:
        elementos.append(t_class_mes)
    elementos.append(Spacer(1, 0.4 * cm))

    elementos.append(Paragraph("Ocorrências por local", style_table_subtitle))
    elementos.append(Spacer(1, 0.5 * cm))
    df_local_mes = agrupar_por_campo(df_mes_atual, "_classificacao_local", "Classificação do Local")
    t_local_mes = montar_tabela_pdf(df_local_mes, col_widths=[2.0 * cm, 5.5 * cm, 2.3 * cm, 2.2 * cm])
    if t_local_mes:
        elementos.append(t_local_mes)
    elementos.append(Spacer(1, 0.5 * cm))

    # --- SEÇÃO 4 ---
    elementos.append(Paragraph("4 - EMPRESAS ENVOLVIDAS POR TIPO DE OCORRÊNCIA", style_section_title))
    elementos.append(Spacer(1, 0.5 * cm))
    for classificacao in CONFIG["classificacoes_empresas"]:
        df_emp = agrupar_empresas_por_classificacao(df_completo, classificacao)
        elementos.append(Paragraph(f"Ocorrência: {classificacao.title()}", style_table_subtitle))
        elementos.append(Spacer(1, 0.5 * cm))
        if not df_emp.empty:
            t_emp = montar_tabela_pdf(df_emp, col_widths=[2.0 * cm, 5.5 * cm, 2.3 * cm, 2.2 * cm])
            if t_emp:
                elementos.append(t_emp)
        else:
            p_sem_dados = Paragraph("<i>Nenhuma empresa registrada para esta classificação no período.</i>", style_signature_date)
            elementos.append(p_sem_dados)
            
        elementos.append(Spacer(1, 0.4 * cm))

    # --- ASSINATURA ---
    elementos.append(Spacer(1, 1.5 * cm))
    data_atual_str = f"Data: {datetime.now().strftime('%d/%m/%Y')}"
    elementos.append(Paragraph(data_atual_str, style_signature_date))
    elementos.append(Spacer(1, 3.0 * cm))
    elementos.append(Paragraph("______________________________________________", style_signature_role))
    elementos.append(Paragraph("Júlio César Gomes Machado", style_signature_name))
    elementos.append(Paragraph("Matrícula: 9153", style_signature_name))
    elementos.append(Paragraph("Responsável Técnico", style_signature_role))

    doc.build(elementos, onFirstPage=desenhar_rodape_pagina, onLaterPages=desenhar_rodape_pagina)

def executar():
    df = carregar_dados()
    df = tratar_dados(df)
    
    # Se existirem múltiplos portos, filtra o dataframe para o porto específico antes de extrair os períodos
    portos = obter_portos_unicos(df)
    pasta_saida = Path(CONFIG["diretorio_saida"])
    pasta_saida.mkdir(parents=True, exist_ok=True)
    
    for porto in portos:
        df_porto = df[df["_porto"] == porto].copy()
        if df_porto.empty:
            continue
            
        periodos_porto = determinar_periodos(df_porto)
        nome_arquivo = f"Relatorio_Ocorrencias_{porto.replace(' ', '_')}.pdf"
        arquivo_pdf = pasta_saida / nome_arquivo
        
        gerar_pdf_modelo(df_porto, periodos_porto, arquivo_pdf, porto_nome=porto)
        print(f"Relatório gerado com sucesso para {porto}: {arquivo_pdf.resolve()}")

if __name__ == "__main__":
    executar()