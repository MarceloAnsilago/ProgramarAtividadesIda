import streamlit as st
from datetime import date, timedelta

# ------------------------------------------------------------------------------
# Sessão e Estruturas de Dados
# ------------------------------------------------------------------------------
if "all_servidores" not in st.session_state:
    st.session_state["all_servidores"] = []
if "all_atividades" not in st.session_state:
    st.session_state["all_atividades"] = []
if "all_veiculos" not in st.session_state:
    st.session_state["all_veiculos"] = []
if "all_ul_sups" not in st.session_state:
    st.session_state["all_ul_sups"] = []

if "servidores" not in st.session_state:
    st.session_state["servidores"] = []
if "atividades" not in st.session_state:
    st.session_state["atividades"] = []
if "veiculos" not in st.session_state:
    st.session_state["veiculos"] = []
if "ul_sups" not in st.session_state:
    st.session_state["ul_sups"] = []

if "plantao_itens" not in st.session_state:
    st.session_state["plantao_itens"] = []

# ------------------------------------------------------------------------------
# Função para ler arquivos TXT com fallback
# ------------------------------------------------------------------------------
def read_text_file(uploaded_file):
    content = uploaded_file.getvalue()
    try:
        return content.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return content.decode("latin-1").splitlines()

# ------------------------------------------------------------------------------
# Layout da Aba "Dados"
# ------------------------------------------------------------------------------
st.title("Teste - Aba Dados")
st.header("Gerenciar Dados")

# Divisão em colunas para centralizar os widgets
c1, c2, c3 = st.columns([1, 2, 1])
with c2:
    # -------------------------------------------------------------------
    # Upload de Servidores
    # -------------------------------------------------------------------
    up_serv = st.file_uploader("Arquivo de Servidores (txt)", type="txt", key="upload_servidores")
    if up_serv is not None:
        lines = read_text_file(up_serv)
        st.session_state["all_servidores"] = [l.strip() for l in lines if l.strip()]
    st.write("### Buscar txt Servidores")
    sel_serv = st.multiselect(
        "Selecione os Servidores",
        st.session_state["all_servidores"],
        default=st.session_state["all_servidores"]
    )
    st.session_state["servidores"] = sel_serv

    st.divider()

    # -------------------------------------------------------------------
    # Upload de Atividades
    # -------------------------------------------------------------------
    up_ativ = st.file_uploader("Arquivo de Atividades (txt)", type="txt", key="upload_atividades")
    if up_ativ is not None:
        lines = read_text_file(up_ativ)
        st.session_state["all_atividades"] = [l.strip() for l in lines if l.strip()]
    st.write("### Buscar txt Atividades")
    sel_ativ = st.multiselect(
        "Selecione as Atividades",
        st.session_state["all_atividades"],
        default=st.session_state["all_atividades"]
    )
    st.session_state["atividades"] = sel_ativ

    st.divider()

    # -------------------------------------------------------------------
    # Upload de Veículos
    # -------------------------------------------------------------------
    up_veic = st.file_uploader("Arquivo de Veículos (txt)", type="txt", key="upload_veiculos")
    if up_veic is not None:
        lines = read_text_file(up_veic)
        st.session_state["all_veiculos"] = [l.strip() for l in lines if l.strip()]
    st.write("### Buscar txt Veículos")
    sel_veic = st.multiselect(
        "Selecione os Veículos",
        st.session_state["all_veiculos"],
        default=st.session_state["all_veiculos"]
    )
    st.session_state["veiculos"] = sel_veic

    st.divider()

    # -------------------------------------------------------------------
    # Upload de ULSAV e Supervisão
    # -------------------------------------------------------------------
    up_ul_sups = st.file_uploader("Arquivo de ULSAV e Supervisão (txt)", type="txt", key="upload_ul_sups")
    if up_ul_sups is not None:
        lines = read_text_file(up_ul_sups)
        st.session_state["all_ul_sups"] = [l.strip() for l in lines if l.strip()]
    st.write("### Buscar txt ULSAV e Supervisão")
    sel_ul_sups = st.multiselect(
        "Selecione ULSAV/ Supervisão",
        st.session_state["all_ul_sups"],
        default=st.session_state["all_ul_sups"]
    )
    st.session_state["ul_sups"] = sel_ul_sups

    st.divider()

    # -------------------------------------------------------------------
    # Upload de Plantão (nome;telefone)
    # -------------------------------------------------------------------
    st.write("### Buscar txt Arquivo de Plantão (Nome e Telefone)")
    up_plantao = st.file_uploader("Carregue seu arquivo TXT (nome;telefone)", type=["txt"], key="upload_plantao")
    if up_plantao is not None:
        content_bytes = up_plantao.read()
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = content_bytes.decode("latin-1")
        lines = content.strip().split("\n")
        itens_plantao = []
        for line in lines:
            parts = line.split(";")
            if len(parts) == 2:
                nome, telefone = parts
                itens_plantao.append((nome.strip(), telefone.strip()))
        st.session_state["plantao_itens"] = itens_plantao
    else:
        st.session_state["plantao_itens"] = []

    # Exibe o multiselect somente se houver itens
    if st.session_state["plantao_itens"]:
        nomes_disponiveis = [item[0] for item in st.session_state["plantao_itens"]]
        st.write("### Selecionar Nomes para Plantão")
        selected_names = st.multiselect(
            "Selecione os nomes:",
            nomes_disponiveis,
            default=nomes_disponiveis,
            key="selected_plantao_names"
        )
    else:
        st.write("Nenhum dado de plantão carregado.")
