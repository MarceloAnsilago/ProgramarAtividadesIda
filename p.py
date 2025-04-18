import streamlit as st
from datetime import date, timedelta
from io import BytesIO
import time
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
import pdf_relatorio
from pdf_utils import generate_pdf_for_week
from pdf_escala import gerar_pdf_escala
import streamlit.components.v1 as components
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
import datetime as dt
import locale
from st_aggrid import AgGrid, GridOptionsBuilder
from babel.numbers import format_currency


# ------------------------------------------------------------------------------
# CSS para personalizar estilos
# ------------------------------------------------------------------------------
st.markdown("""
<style>
.summary-card {
    border: 1px solid #ccc; 
    border-radius: 5px; 
    padding: 10px; 
    margin: 5px 0;
    background-color: #ffffff;
}
.summary-flex {
    display: flex; 
    gap: 20px; 
    justify-content: space-between;
}
.summary-column {
    flex: 1; 
    min-width: 0; 
}
.full-width-hr {
    width: 100%;
    border: 1px solid #ccc;
    margin-top: 50px;
}
.day-title {
    font-size: 1.3rem !important;
    font-weight: 600 !important;
    margin: 0.5rem 0 0.5rem 0 !important;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Sessão e Estruturas de Dados
# ------------------------------------------------------------------------------
def init_plantao_session_state():
    st.session_state.setdefault("semanas", {})
    st.session_state.setdefault("week_order", [])
    st.session_state.setdefault("atividades_dia", {})
    st.session_state.setdefault("unavailable_periods", {})
    st.session_state.setdefault("plantao_itens", [])
    st.session_state.setdefault("checklist", {})
    st.session_state.setdefault("all_servidores", [])
    st.session_state.setdefault("servidores", [])
    st.session_state.setdefault("all_atividades", [])
    st.session_state.setdefault("all_veiculos", [])
    st.session_state.setdefault("all_ul_sups", [])
    
    # [NOVO] Session compacta para checkboxes
    st.session_state.setdefault("checkbox_off", {})

init_plantao_session_state()


def get_supabase_client() -> Client:
        SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wlbvahpkcaksqkzdhnbv.supabase.co")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndsYnZhaHBrY2Frc3FremRobmJ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDMyODMxMTUsImV4cCI6MjA1ODg1OTExNX0.Cph86UhT8Q67-1x2oVfTFyELgQqWRgJ3yump1JpHSc8")
        return create_client(SUPABASE_URL, SUPABASE_KEY)



NOME_MESES = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }

def get_week_label(week_id):
    week_dates = st.session_state["semanas"].get(week_id, [])
    if not week_dates:
        return "Semana não identificada"

    first_date = week_dates[0]
    year = first_date.year
    month = first_date.month
    _, week_number = first_date.isocalendar()[:2]
    first_day_of_month = date(year, month, 1)
    _, first_week_number = first_day_of_month.isocalendar()[:2]
    week_position_in_month = week_number - first_week_number + 1
    if week_position_in_month < 1:
        week_position_in_month = 1

    ordinal_name = get_ordinal_week_in_month(week_position_in_month)
    month_name_pt = NOME_MESES.get(month, f"[{month}]")
    return f"{ordinal_name} semana de {month_name_pt}"

class SemanaState:
    def __init__(self):
        self._semanas = st.session_state.setdefault("semanas", {})
        self._week_order = st.session_state.setdefault("week_order", [])

    def get_semanas(self):
        return self._semanas

    def get_week_order(self):
        return self._week_order

    def remover_semana(self, week_id):
        if week_id in self._semanas:
            for day_date in self._semanas[week_id]:
                date_str = day_date.strftime("%d/%m/%Y")
                if date_str in st.session_state["atividades_dia"]:
                    del st.session_state["atividades_dia"][date_str]
            del self._semanas[week_id]

        if week_id in self._week_order:
            self._week_order.remove(week_id)

    def adicionar_semana(self, week_id, datas):
        self._semanas[week_id] = datas
        if week_id not in self._week_order:
            self._week_order.append(week_id)



class AtividadeState:

    def __init__(self):
        self._data = st.session_state.setdefault("atividades_dia", {})

    def get_dia(self, date_str):
        return self._data.setdefault(date_str, [])

    def add_atividade(self, date_str, atividade, servidores, veiculo):
        self._data.setdefault(date_str, []).append({
            "atividade": atividade,
            "servidores": servidores,
            "veiculo": veiculo
        })

    def remover_atividade(self, date_str, idx):
        atividades = self._data.get(date_str, [])
        if 0 <= idx < len(atividades):
            atividade = atividades[idx]

            # Só realoca se não for expediente
            if atividade["atividade"] != "Expediente Administrativo":
                servidores = atividade["servidores"]
                # Garante que expediente existe
                if not any(a["atividade"] == "Expediente Administrativo" for a in atividades):
                    self.add_atividade(date_str, "Expediente Administrativo", [], "Nenhum")

                for s in servidores:
                    self.adicionar_no_expediente(date_str, s)

            # Remove a atividade
            del atividades[idx]


    def remover_servidor(self, date_str, idx, servidor):
        atividades = self._data.get(date_str, [])
        if 0 <= idx < len(atividades):
            atividade = atividades[idx]
            if atividade["atividade"] != "Expediente Administrativo":
                if servidor in atividade["servidores"]:
                    atividade["servidores"].remove(servidor)
                    self.adicionar_no_expediente(date_str, servidor)



    def adicionar_no_expediente(self, date_str, servidor):
        for atividade in self._data.get(date_str, []):
            if atividade["atividade"] == "Expediente Administrativo":
                if servidor not in atividade["servidores"]:
                    atividade["servidores"].append(servidor)
                return

##################################################################################
##################################################################################
##################################################################################
# [REFATORADO] Classe auxiliar para encapsular interações com atividades da semana
class SemanaManager:
    def __init__(self):
        self.dados = st.session_state.setdefault("atividades_dia", {})

    def get_dia(self, data_str):
        return self.dados.setdefault(data_str, [])

    def add_atividade(self, date_str, atividade, servidores, veiculo):
        if date_str not in self._data:
            self._data[date_str] = []

        self._data[date_str].append({
            "atividade": atividade,
            "servidores": servidores,
            "veiculo": veiculo
        })

    def remover_atividade(self, data_str, idx):
        atividade = self.dados.get(data_str, [])[idx]
        for s in atividade["servidores"]:
            self.adicionar_no_expediente(data_str, s)
        del self.dados[data_str][idx]

    def adicionar_no_expediente(self, data_str, servidor):
        for atividade in self._data.get(data_str, []):
            if atividade["atividade"] == "Expediente Administrativo":
                if servidor not in atividade["servidores"]:
                    atividade["servidores"].append(servidor)
                return  # ← interrompe após encontrar e adicionar


# [REFATORADO] Encapsulamento da lógica de indisponibilidade por servidor
class IndisponibilidadeManager:
    def __init__(self):
        self.data = st.session_state.setdefault("unavailable_periods", {})

    def get_periodos(self, nome):
        return self.data.get(nome, [])

    def adicionar_periodo(self, nome, inicio, fim):
        if nome not in self.data:
            self.data[nome] = []
        self.data[nome].append((inicio, fim))

    def remover_periodo(self, nome, idx):
        if nome in self.data and 0 <= idx < len(self.data[nome]):
            self.data[nome].pop(idx)

# [REFATORADO] Gerenciador da geração de plantões
class PlantaoManager:
    def __init__(self, nomes_selecionados, itens, indisponibilidades):
        self.nomes = nomes_selecionados
        self.telefones = {nome: tel for nome, tel in itens}
        self.indisponibilidades = indisponibilidades
        self.blocos = []

    def alinhar_para_sabado(self, data_ref):
        dia_semana = data_ref.weekday()
        diff = 5 - dia_semana if dia_semana <= 5 else 6
        return data_ref + timedelta(days=diff)

    def esta_indisponivel(self, nome, ini_bloco, fim_bloco):
        if nome not in self.indisponibilidades:
            return False
        for ini_ind, fim_ind in self.indisponibilidades[nome]:
            if not (fim_bloco < ini_ind or ini_bloco > fim_ind):
                return True
        return False

    def gerar_blocos(self, data_inicio, data_fim):
        if not self.nomes:
            return []

        data_corrente = self.alinhar_para_sabado(data_inicio)
        if data_corrente > data_fim:
            return []

        idx = 0
        while data_corrente <= data_fim:
            fim_bloco = min(data_corrente + timedelta(days=6), data_fim)
            servidor_escolhido = None

            tentativas = 0
            while tentativas < len(self.nomes):
                nome_atual = self.nomes[idx]
                if not self.esta_indisponivel(nome_atual, data_corrente, fim_bloco):
                    servidor_escolhido = nome_atual
                    idx = (idx + 1) % len(self.nomes)
                    break
                idx = (idx + 1) % len(self.nomes)
                tentativas += 1

            if servidor_escolhido:
                telefone = self.telefones.get(servidor_escolhido, "")
            else:
                servidor_escolhido = "— Sem Servidor —"
                telefone = ""

            self.blocos.append({
                "start": data_corrente,
                "end": fim_bloco,
                "servidor": servidor_escolhido,
                "telefone": telefone
            })

            data_corrente = fim_bloco + timedelta(days=1)
            data_corrente = self.alinhar_para_sabado(data_corrente)

        return self.blocos

# [REFATORADO] Renderizador HTML para escala de plantão
class HtmlEscalaRenderer:
    def __init__(self, blocos, nome_meses, titulo_pagina="Escala de Plantão"):
        self.blocos = blocos
        self.nome_meses = nome_meses
        self.titulo_pagina = titulo_pagina

    def agrupar_por_mes(self):
        agrupado = {}
        for bloco in self.blocos:
            dt_start = bloco["start"]
            dt_end = bloco["end"]
            servidor = bloco["servidor"]
            telefone = bloco["telefone"]

            ano = dt_start.year
            mes = dt_start.month
            data_str = f"Do dia {dt_start.strftime('%d/%m/%Y')} ao dia {dt_end.strftime('%d/%m/%Y')}"

            if (ano, mes) not in agrupado:
                agrupado[(ano, mes)] = []

            agrupado[(ano, mes)].append({
                "Data": data_str,
                "Servidor": servidor,
                "Contato": telefone
            })

        return dict(sorted(agrupado.items(), key=lambda x: (x[0][0], x[0][1])))

    def render(self):
        grupos = self.agrupar_por_mes()

        html = f"""<html>
<head>
<meta charset="UTF-8">
<title>{self.titulo_pagina}</title>
<style>
    body {{ font-family: Helvetica, sans-serif; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #999; padding: 6px 10px; text-align: left; }}
    h2 {{ margin-top: 30px; }}
    @media print {{
        #printButton {{ display: none; }}
    }}
</style>
<script>
    function printIframe() {{
        window.print();
    }}
</script>
</head>
<body>
<h3>{self.titulo_pagina} IDARON para recebimento de vacinas agrotóxicos e produtos biológicos</h3>
"""

        for (ano, mes), itens in grupos.items():
            nome_mes = self.nome_meses.get(mes, str(mes))
            html += f'<h2>{nome_mes} de {ano}</h2>\n'
            html += '<table>\n<tr><th>Data</th><th>Servidor</th><th>Contato</th></tr>\n'
            for item in itens:
                html += f"<tr><td>{item['Data']}</td><td>{item['Servidor']}</td><td>{item['Contato']}</td></tr>\n"
            html += '</table>\n'

        html += '<button id="printButton" onclick="printIframe()">Imprimir</button>\n'
        html += '</body></html>'

        return html


def iniciar_com_loading():
       st.session_state.exibir_loading = True
       st.rerun()
   
if st.session_state.get("exibir_loading"):
    with st.spinner("Processando..."):
        time.sleep(1)  # Dá tempo do spinner aparecer antes do rerun
        st.session_state.exibir_loading = False  # Reseta para não repetir
    st.rerun()

# # [REFATORADO] Gerenciador leve de checkboxes
def is_checkbox_checked(date_str, tipo, idx, nome=None):
    key = f"{tipo}_{idx}" if nome is None else f"{tipo}_{idx}_{nome}"
    return not st.session_state.get("checkbox_off", {}).get(date_str, {}).get(key, False)

def set_checkbox_unchecked(date_str, tipo, idx, nome=None):
    key = f"{tipo}_{idx}" if nome is None else f"{tipo}_{idx}_{nome}"
    if "checkbox_off" not in st.session_state:
        st.session_state["checkbox_off"] = {}
    if date_str not in st.session_state["checkbox_off"]:
        st.session_state["checkbox_off"][date_str] = {}
    st.session_state["checkbox_off"][date_str][key] = True


if st.session_state.get("recarregar", False):
    st.session_state["recarregar"] = False
    st.rerun()


# Inicializa chaves necessárias, se ainda não existirem
if "week_order" not in st.session_state:
    st.session_state["week_order"] = []
if "unavailable_periods" not in st.session_state:
    st.session_state["unavailable_periods"] = {}
if "plantao_itens" not in st.session_state:
    st.session_state["plantao_itens"] = []

def render_selecao_servidores():
    st.write("### 👥 Servidores para o Plantão")
    itens = st.session_state.get("plantao_itens", [])
    if not itens:
        st.info("ℹ️ Nenhum 👥 servidor encontrado para o plantão.")
        return

    nomes_disponiveis = [nome for nome, _ in itens]
    st.multiselect(
        "Selecione os servidores:",
        nomes_disponiveis,
        default=nomes_disponiveis,
        key="selected_plantao_names"
    )

# Função para gerar blocos de plantão (Sábado a Sexta)
def gerar_blocos_sabado_sexta(data_inicio, data_fim, selected_names, itens, unavailable_periods):
    """
    Gera uma lista de blocos com a data e os servidores disponíveis,
    considerando que o plantão é para dias de sábado a sexta (excluindo domingos).
    """
    blocos = []
    current_date = data_inicio
    while current_date <= data_fim:
        # Se não for domingo (weekday() == 6)
        if current_date.weekday() != 6:
            disponiveis = []
            for nome in selected_names:
                # Se não houver período de indisponibilidade ou se o servidor estiver disponível
                if nome not in unavailable_periods or all(not (start <= current_date <= end)
                                                           for start, end in unavailable_periods[nome]):
                    disponiveis.append(nome)
            blocos.append({
                "data": current_date.strftime("%d/%m/%Y"),
                "disponiveis": disponiveis
            })
        current_date += timedelta(days=1)
    return blocos
def render_indisponibilidades():
    st.subheader("❌ Indisponibilidades")
    selected_names = st.session_state.get("selected_plantao_names", [])
    itens = st.session_state.get("plantao_itens", [])

    if not selected_names:
        st.info("Selecione ao menos um servidor.")
        return

    tabs_inner = st.tabs(selected_names)

    for i, tab in enumerate(tabs_inner):
        with tab:
            nome_tab = selected_names[i]
            tel_tab = next((tel for nm, tel in itens if nm == nome_tab), "Sem Telefone")
            st.write(f"**🧑Nome:** {nome_tab}")
            st.write(f"**📞Telefone:** {tel_tab}")

            indispo = IndisponibilidadeManager()

            st.subheader("➕❌ Adicionar Período de Indisponibilidade")
            col_dt1, col_dt2 = st.columns(2)
            with col_dt1:
                inicio = st.date_input("Data de Início", key=f"inicio_{nome_tab}", value=date.today())
            with col_dt2:
                fim = st.date_input("Data de Fim", key=f"fim_{nome_tab}", value=date.today())

            if st.button("➕ Adicionar Período", key=f"btn_{nome_tab}"):
                indispo.adicionar_periodo(nome_tab, inicio, fim)
                st.success(f"Período adicionado para {nome_tab}.")

            st.write("### 📋 Períodos de Indisponibilidade Registrados")
            periodos = indispo.get_periodos(nome_tab)
            if periodos:
                for idx, (start_dt, end_dt) in enumerate(periodos):
                    colA, colB, colC = st.columns([3, 3, 1])
                    colA.write(f"**Início:** {start_dt}")
                    colB.write(f"**Fim:** {end_dt}")
                    if colC.button("🗑️ Remover", key=f"remover_{nome_tab}_{idx}"):
                        indispo.remover_periodo(nome_tab, idx)
                        iniciar_com_loading()

            else:
                st.info("📭 Nenhum período cadastrado até o momento.")
def render_cronograma_plantao():
    col_cronograma1, col_cronograma2 = st.columns(2)
    with col_cronograma1:
        data_cronograma_inicio = st.date_input(
            "Data inicial do cronograma",
            value=date.today(),
            key="cronograma_inicio_plantao"
        )
    with col_cronograma2:
        data_cronograma_fim = st.date_input(
            "Data final do cronograma",
            value=date.today(),
            key="cronograma_fim_plantao"
        )

    if st.button("⚙️ Gerar Escala", key="gerar_plantao_btn"):
        if data_cronograma_inicio > data_cronograma_fim:
            st.error("A data inicial deve ser anterior ou igual à data final.")
        else:
            plantao_mgr = PlantaoManager(
                nomes_selecionados=st.session_state.get("selected_plantao_names", []),
                itens=st.session_state.get("plantao_itens", []),
                indisponibilidades=IndisponibilidadeManager().data
            )
            blocos = plantao_mgr.gerar_blocos(data_cronograma_inicio, data_cronograma_fim)

            if not blocos:
                st.warning("⚠️ Não foi possível gerar escala (todos indisponíveis ou sem intervalos).")
            else:
                html_iframe = HtmlEscalaRenderer(
                    blocos=blocos,
                    nome_meses=NOME_MESES,
                    titulo_pagina="Relatório de Plantão"
                ).render()
                components.html(html_iframe, height=600, scrolling=True)


# Lista de ordinal para semanas no mês
ordinal_names = [
    "Primeira", "Segunda", "Terceira", "Quarta", "Quinta", "Sexta",
    "Sétima", "Oitava", "Nona", "Décima", "Décima Primeira", "Décima Segunda"
]

def get_ordinal_week_in_month(n: int) -> str:
    """Retorna o ordinal em português para a semana do mês (1->Primeira, 2->Segunda, etc.)"""
    if 1 <= n <= len(ordinal_names):
        return ordinal_names[n-1]
    else:
        return f"{n}ª"

# Dias da semana em português (para exibição)

def dia_semana_pt(data):
    dias_semana = {
        0: "Segunda-feira",
        1: "Terça-feira",
        2: "Quarta-feira",
        3: "Quinta-feira",
        4: "Sexta-feira",
        5: "Sábado",
        6: "Domingo"
    }
    return dias_semana.get(data.weekday(), "Desconhecido")

# ------------------------------------------------------------------------------
# Funções Auxiliares para Programação
# ------------------------------------------------------------------------------
def get_week_id(ref_date):
    year, week, _ = ref_date.isocalendar()
    return f"{year}-W{week:02d}"

def get_week_dates(ref_date, include_saturday=False, include_sunday=False):
    """Retorna as datas da semana: sempre segunda a sexta; inclui sábado/domingo se marcado."""
    year, week, weekday = ref_date.isocalendar()
    monday = ref_date - timedelta(days=weekday - 1)
    dates = [monday + timedelta(days=i) for i in range(5)]
    if include_saturday:
        dates.append(monday + timedelta(days=5))
    if include_sunday:
        dates.append(monday + timedelta(days=6))
    return dates

def add_week_if_not_exists(ref_date, include_saturday=False, include_sunday=False):
    wid = get_week_id(ref_date)
    semana_state = SemanaState()
    
    if wid not in semana_state.get_semanas():
        datas = get_week_dates(ref_date, include_saturday, include_sunday)
        semana_state.get_semanas()[wid] = datas
        semana_state.get_week_order().append(wid)

        servidores = st.session_state.get("servidores", [])
        for day_date in datas:
           
            AtividadeState().add_atividade(
                day_date.strftime("%d/%m/%Y"),
                "Expediente Administrativo",
                servidores,
                "Nenhum"
            )


# [REFATORADO]
def add_activity_to_date(activity_date, atividade, servidores, veiculo):
    date_str = activity_date.strftime("%d/%m/%Y")
    AtividadeState().add_atividade(date_str, atividade, servidores, veiculo)

def add_server_to_expediente(date_str, server):
    for act in st.session_state["atividades_dia"].get(date_str, []):
        if act["atividade"] == "Expediente Administrativo":
            if server not in act["servidores"]:
                act["servidores"].append(server)
            return

# [REFATORADO]
def remove_server_from_card(date_str, card_index, server):
    AtividadeState().remover_atividade(date_str, card_index)

# [REFATORADO]
def remove_activity_card(date_str, card_index):
   
    AtividadeState().remover_atividade(date_str, card_index)
  

def remove_week(week_id):
    SemanaState().remover_semana(week_id)

# ------------------------------------------------------------------------------
# Resumo: conta itens (exceto Expediente Administrativo)
# ------------------------------------------------------------------------------
def get_summary_details_for_week(week_id):
    activities = {}
    servers = {}
    vehicles = {}
    week_dates = st.session_state["semanas"].get(week_id, [])
    for day_date in week_dates:
        date_str = day_date.strftime("%d/%m/%Y")
        day_acts = AtividadeState().get_dia(date_str)
        for act_idx, act in enumerate(day_acts):
            if act["atividade"] != "Expediente Administrativo":
                activities[act["atividade"]] = activities.get(act["atividade"], 0) + 1
                for s in act["servidores"]:
                    key_server = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                    if st.session_state.get(key_server, True):
                        servers[s] = servers.get(s, 0) + 1
                if act["veiculo"] and act["veiculo"] != "Nenhum":
                    vehicles[act["veiculo"]] = vehicles.get(act["veiculo"], 0) + 1
    return activities, servers, vehicles


# --------------------------------------------------
# FUNÇÕES AUXILIARES PARA IMPRESSÃO
# --------------------------------------------------

# [REFATORADO]
def build_cards_list(week_dates):
    cards_list = []
    semana = SemanaManager()

    for day_date in week_dates:
        date_str = day_date.strftime("%d/%m/%Y")
        day_name_pt = dia_semana_pt(day_date)
        day_label = f"{day_name_pt} ({date_str})"

        filtered_acts = []

        for act_idx, act in enumerate(semana.get_dia(date_str)):
            if act["atividade"] != "Expediente Administrativo":
                if not is_checkbox_checked(date_str, "atividade", act_idx):
                    continue

            filtered_servers = [
                s for s in act["servidores"]
                if is_checkbox_checked(date_str, "servidor", act_idx, s)
            ]

            if act["atividade"] != "Expediente Administrativo" and not filtered_servers:
                continue

            filtered_acts.append({
                "atividade": act["atividade"],
                "servidores": filtered_servers,
                "veiculo": act["veiculo"]
            })

        cards_list.append({
            "Dia": day_label,
            "Activities": filtered_acts
        })

    return cards_list

# [REFATORADO]
def build_atividades_por_servidor(week_dates):
    atividades_por_servidor = {}
    semana = SemanaManager()

    for day_date in week_dates:
        date_str = day_date.strftime("%d/%m/%Y")
        for act_idx, act in enumerate(semana.get_dia(date_str)):
            if act["atividade"] != "Expediente Administrativo":
                if not is_checkbox_checked(date_str, "atividade", act_idx):
                    continue
                for s in act["servidores"]:
                    if is_checkbox_checked(date_str, "servidor", act_idx, s):
                        if s not in atividades_por_servidor:
                            atividades_por_servidor[s] = []
                        atividades_por_servidor[s].append({
                            "Data": date_str,
                            "Atividade": act["atividade"]
                        })

    return atividades_por_servidor

def alinhar_sabado_ou_proximo(data_ref):
    dia_semana = data_ref.weekday()
    if dia_semana <= 5:
        diff = 5 - dia_semana
    else:
        diff = 6
    return data_ref + timedelta(days=diff)

def servidor_indisponivel(nome_servidor, ini_bloco, fim_bloco, indisponibilidades):
    if nome_servidor not in indisponibilidades:
        return False
    for (ini_indisp, fim_indisp) in indisponibilidades[nome_servidor]:
        # Verifica sobreposição de intervalos
        if not (fim_bloco < ini_indisp or ini_bloco > fim_indisp):
            return True
    return False

def agrupar_blocos_mensalmente(blocos, NOME_MESES):
    grupos = {}
    for bloco in blocos:
        dt_start = bloco["start"]
        dt_end = bloco["end"]
        servidor = bloco["servidor"]
        telefone = bloco["telefone"]

        y = dt_start.year
        m = dt_start.month

        data_str = (f"Do dia {dt_start.strftime('%d/%m/%Y')} "
                    f"ao dia {dt_end.strftime('%d/%m/%Y')}")

        if (y, m) not in grupos:
            grupos[(y, m)] = []
        grupos[(y, m)].append({
            "Data": data_str,
            "Servidor": servidor,
            "Contato": telefone
        })
    return grupos

def render_formulario_ferias(supabase):
    st.title("📅 Cadastro de Escala de Férias")

    ano_escala = st.number_input(
        "Ano da escala",
        value=dt.date.today().year,
        step=1,
        format="%d",
        key="ano_escala_input"
    )
    st.session_state["ano_escala"] = ano_escala

    unidade_id = st.session_state.get("selected_unidade_id", 3)

    try:
        response = supabase.table("servidores").select("*").eq("escritorio_id", unidade_id).execute()
        servidores = [s["nome"] for s in response.data] if response.data else []
    except Exception as e:
        st.error(f"Erro ao carregar servidores: {e}")
        servidores = []

    if servidores:
        servidor = st.selectbox("Selecione o servidor", servidores, key="ferias_servidor")
    else:
        servidor = None
        st.warning("Nenhum servidor encontrado para o escritório.")

    col_data1, col_data2 = st.columns(2)
    with col_data1:
        data_inicial = st.date_input("Data Inicial", value=dt.date.today(), key="ferias_inicio")
    with col_data2:
        data_final = st.date_input("Data Final", value=dt.date.today(), key="ferias_fim")

    if st.button("➕ Adicionar Intervalo", key="add_intervalo_ferias"):
        if not servidor:
            st.warning("Selecione um servidor.")
        elif data_final < data_inicial:
            st.error("A data final não pode ser anterior à data inicial.")
        else:
            st.session_state.setdefault("intervalos", []).append({
                "servidor": servidor,
                "data_inicial": data_inicial,
                "data_final": data_final
            })
            iniciar_com_loading()


def render_tabela_ferias():
    st.subheader("📋 Intervalos Inseridos")
    if st.session_state.get("intervalos"):
        for i, item in enumerate(st.session_state["intervalos"]):
            col_l, col_r = st.columns([6, 1])
            with col_l:
                st.markdown(f"**{i+1}. {item['servidor']}**: {item['data_inicial']} a {item['data_final']}")
            with col_r:
                if st.button("❌ Remover", key=f"remove_ferias_{i}"):
                    st.session_state["intervalos"].pop(i)
                    iniciar_com_loading()

    else:
        st.info("Nenhum intervalo cadastrado.")

def render_botao_gerar_pdf():
    st.markdown("---")
    if st.button("📥 Gerar Escala em PDF", key="gerar_pdf_ferias"):
        if st.session_state.get("intervalos"):
            caminho_pdf = "escala_de_ferias.pdf"
            gerar_pdf_escala(
                st.session_state["intervalos"],
                caminho_pdf,
                ano_titulo=st.session_state.get("ano_escala", dt.date.today().year)
            )
            with open(caminho_pdf, "rb") as f:
                pdf_bytes = f.read()

            st.download_button(
                label="⬇️ Baixar Escala de Férias",
                data=pdf_bytes,
                file_name="escala_de_ferias.pdf",
                mime="application/pdf"
            )
        else:
            st.warning("Nenhum intervalo cadastrado.")

            
def render_filtros_programacao(supabase):
    st.markdown("### 🎯 Filtros da Programação")

    unidade_id = st.session_state.get("selected_unidade_id", None)

    # --- Servidores ---
    if unidade_id:
        res_serv = supabase.table("servidores").select("nome").eq("escritorio_id", unidade_id).execute()
        nomes_servidores = [s["nome"] for s in res_serv.data] if res_serv.data else []
    else:
        nomes_servidores = []

    sel_serv = st.multiselect(
        "🧑‍💼 Servidores",
        nomes_servidores,
        default=nomes_servidores,
        key="multiselect_servidores_programacao_dados"
    )
    st.session_state["servidores"] = sel_serv

    # --- Atividades ---
    if unidade_id:
        res_ativ = supabase.table("atividades").select("descricao").eq("escritorio_id", unidade_id).execute()
        atividades_list = [a["descricao"] for a in res_ativ.data] if res_ativ.data else []
    else:
        atividades_list = []

    sel_ativ = st.multiselect(
        "🗂️ Atividades",
        atividades_list,
        default=atividades_list,
        key="multiselect_atividades"
    )
    st.session_state["atividades"] = sel_ativ

    # --- Veículos ---
    if unidade_id:
        res_veic = supabase.table("veiculos").select("veiculo").eq("escritorio_id", unidade_id).execute()
        veiculos_list = [v["veiculo"] for v in res_veic.data] if res_veic.data else []
    else:
        veiculos_list = []

    sel_veic = st.multiselect(
        "🚗 Veículos",
        veiculos_list,
        default=veiculos_list,
        key="multiselect_veiculos"
    )
    st.session_state["veiculos"] = sel_veic

    # --- ULSAV/Supervisão ---
    if unidade_id:
        res_unidade = supabase.table("unidades").select("nome, supervisao").eq("id", unidade_id).execute()
        if res_unidade.data:
            row = res_unidade.data[0]
            st.session_state["all_ul_sups"] = [row["nome"], row["supervisao"]]
        else:
            st.session_state["all_ul_sups"] = []
    else:
        st.session_state["all_ul_sups"] = []

    sel_ul_sups = st.multiselect(
        "📝 ULSAV/Supervisão",
        st.session_state["all_ul_sups"],
        default=st.session_state["all_ul_sups"],
        key="multiselect_ul_sups"
    )
    st.session_state["ul_sups"] = sel_ul_sups




def main_app():
  
    # ------------------------------------------------------------------------------
    # Layout com Abas
    # ------------------------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dados (Informações Gerais)", 
        "🗓️ Programação (Gerar programação de atividades)", 
        "📦 Programação para recebimento",
        "📅 Gerar Escala de Férias",
        "📄 Requerimento para  Parcelar Auto de Infração"
    ])
        # ------------------------------------------------------------------------------
    # Aba 1: Dados
    # ------------------------------------------------------------------------------
    with tab1:

        supabase = get_supabase_client()

        # Função para carregar os escritórios (unidades)
        def get_escritorios():
            res = supabase.table("unidades").select("*").execute()
            if res.data:
                return res.data  # Lista de dicts
            else:
                return []

        # Inicializa chaves do session_state se não existirem
        if "all_servidores" not in st.session_state:
            st.session_state["all_servidores"] = []
        if "all_atividades" not in st.session_state:
            st.session_state["all_atividades"] = []
        if "all_veiculos" not in st.session_state:
            st.session_state["all_veiculos"] = []
        if "all_ul_sups" not in st.session_state:
            st.session_state["all_ul_sups"] = []
        if "unavailable_periods" not in st.session_state:
            st.session_state["unavailable_periods"] = {}

   
        
        # Filtra a aplicação pela unidade selecionada (do login)
        unidade_nome = st.session_state.get("selected_unidade", None)
        unidade_id = st.session_state.get("selected_unidade_id", None)
        usuario_admin = st.session_state.get("is_admin", False)

        if unidade_nome and unidade_id:
            st.write(f"🏢 Unidade de: {unidade_nome} (ID: {unidade_id})")
        else:
            if usuario_admin:
                st.warning("⚠️ Nenhuma unidade selecionada.")
                
        # --- PARTE DE DADOS (Uploads e multiselects) ---
        st.header("🛠️ Gerenciar Dados")
     
     
        # --- TABS DE CRUD (Servidores, Atividades, Veículos) ---
        tabs_crud = st.tabs(["🧑‍💼 Servidores", "🗂️ Atividades", "🚗 Veículos"])
       
        # -------- ABA 1: Servidores --------
        with tabs_crud[0]:
            st.header("🧑‍💼 Gerenciamento de Servidores")
            # Se houver um filtro de unidade, aplica-o
            if unidade_id:
                res_serv = supabase.table("servidores").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_serv = supabase.table("servidores").select("*").execute()
            if res_serv.data:
                st.subheader("📋 Servidores Cadastrados")
                st.dataframe(res_serv.data)
            else:
                st.info("Nenhum servidor cadastrado.")
            
            st.write("---")
            st.subheader("➕ Cadastrar Novo Servidor")

            # Carrega escritórios para escolha
            lista_escritorios = get_escritorios()
            dict_escritorios = {esc["nome"]: esc["id"] for esc in lista_escritorios}
            nomes_escritorios = list(dict_escritorios.keys())

            # Se a unidade já foi selecionada, usa-a; caso contrário, permite escolha
            if unidade_id:
                st.write(f"Escritório: {st.session_state.get('selected_unidade')}")
                chosen_esc_id = unidade_id
            else:
                esc_escolhido_nome = st.selectbox("Escritório", nomes_escritorios, key="esc_escolhido_servidor")
                chosen_esc_id = dict_escritorios[esc_escolhido_nome]

            with st.form("cadastro_servidor"):
                novo_nome = st.text_input("Nome do Servidor", key="novo_nome_servidor").strip()
                novo_telefone = st.text_input("Telefone", key="novo_telefone_servidor").strip()
                nova_matricula = st.text_input("Matrícula", key="nova_matricula_servidor").strip()
                novo_cargo = st.text_input("Cargo", key="novo_cargo_servidor").strip()
                status_servidor = st.checkbox("Ativo?", value=True, key="status_servidor_cadastro")
                submit_cadastro_serv = st.form_submit_button("➕ Cadastrar Servidor")

            if submit_cadastro_serv:
                # VALIDAÇÕES
                if not novo_nome:
                    st.error("❌ O nome do servidor é obrigatório.")
                elif not novo_telefone:
                    st.error("❌ O telefone é obrigatório.")
                elif not nova_matricula:
                    st.error("❌ A matrícula é obrigatória.")
                elif not novo_cargo:
                    st.error("❌ O cargo é obrigatório.")
                else:
                    status_val = "Ativo" if status_servidor else "Inativo"
                    insert_res = supabase.table("servidores").insert({
                        "nome": novo_nome,
                        "telefone": novo_telefone,
                        "matricula": nova_matricula,
                        "cargo": novo_cargo,
                        "status": status_val,
                        "escritorio_id": chosen_esc_id
                    }).execute()
                    if insert_res.data:
                        st.success("✅ Servidor cadastrado com sucesso!")
                        iniciar_com_loading()

                    else:
                        st.error(f"❌ Erro ao cadastrar o servidor: {insert_res.error}")

            st.write("---")
            st.subheader("✏️ Editar Servidor Existente")
            if unidade_id:
                res_edit_serv = supabase.table("servidores").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_edit_serv = supabase.table("servidores").select("*").execute()
            servidores_edit = res_edit_serv.data if res_edit_serv.data else []
            if servidores_edit:
                servidor_escolhido = st.selectbox("Selecione o Servidor para editar",
                                                options=servidores_edit,
                                                format_func=lambda x: x["nome"],
                                                key="select_servidor_editar")
                if servidor_escolhido:
                    novo_nome_edit = st.text_input("Novo Nome", value=servidor_escolhido["nome"], key=f"nome_edit_{servidor_escolhido['id']}")
                    novo_telefone_edit = st.text_input("Telefone", value=servidor_escolhido.get("telefone", ""), key=f"tel_edit_{servidor_escolhido['id']}")
                    nova_matricula_edit = st.text_input("Matrícula", value=servidor_escolhido.get("matricula", ""), key=f"mat_edit_{servidor_escolhido['id']}")
                    novo_cargo_edit = st.text_input("Cargo", value=servidor_escolhido.get("cargo", ""), key=f"cargo_edit_{servidor_escolhido['id']}")
                    st.write(f"Escritório atual (ID): {servidor_escolhido.get('escritorio_id')}")
                  
                    status_padrao = (servidor_escolhido.get("status", "Inativo") == "Ativo")

                    status_edit = st.checkbox("Ativo?", value=status_padrao, key=f"status_serv_{servidor_escolhido['id']}")
                    if st.button("🔄 Atualizar Servidor", key=f"btn_atualizar_serv_{servidor_escolhido['id']}"):
                        status_val_edit = "Ativo" if status_edit else "Inativo"
                        update_res = supabase.table("servidores").update({
                            "nome": novo_nome_edit,
                            "telefone": novo_telefone_edit,
                            "matricula": nova_matricula_edit,
                            "cargo": novo_cargo_edit,
                            "status": status_val_edit
                        }).eq("id", servidor_escolhido["id"]).execute()
                        if update_res.data:
                            st.success("Servidor atualizado com sucesso!")
                            iniciar_com_loading()

                        else:
                            st.error("Erro ao atualizar o servidor!")
            else:
                st.info("Não há servidores para editar.")

        # -------- ABA 2: Atividades --------
        with tabs_crud[1]:
         
            st.header("Gerenciamento de Atividades")

            if unidade_id:
                res_ativ = supabase.table("atividades").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_ativ = supabase.table("atividades").select("*").execute()

            if res_ativ.data:
                st.subheader("Atividades Cadastradas")
                st.dataframe(res_ativ.data)
            else:
                st.info("Nenhuma atividade cadastrada.")

            st.write("---")
            st.subheader("Cadastrar Nova Atividade")

            lista_escritorios_ativ = get_escritorios()
            dict_escritorios_ativ = {esc["nome"]: esc["id"] for esc in lista_escritorios_ativ}
            nomes_escritorios_ativ = list(dict_escritorios_ativ.keys())

            if unidade_id:
                st.write(f"Escritório: {st.session_state.get('selected_unidade')}")
                chosen_esc_ativ = unidade_id
            else:
                esc_nome_ativ = st.selectbox("Escritório", nomes_escritorios_ativ, key="esc_ativ_cadastro")
                chosen_esc_ativ = dict_escritorios_ativ[esc_nome_ativ]

            with st.form("cadastro_atividade"):
                desc_atividade = st.text_input("Descrição", key="desc_atividade").strip()
                data_atividade = st.date_input("Data", key="data_atividade")
                status_atividade = st.checkbox("Ativo?", value=True, key="status_atividade_cadastro")
                submit_cadastro_ativ = st.form_submit_button("Cadastrar Atividade")

            if submit_cadastro_ativ:
                if not desc_atividade:
                    st.error("❌ A descrição da atividade é obrigatória.")
                else:
                    status_val = "Ativo" if status_atividade else "Inativo"
                    insert_res = supabase.table("atividades").insert({
                        "descricao": desc_atividade,
                        "data": data_atividade.isoformat(),
                        "status": status_val,
                        "escritorio_id": chosen_esc_ativ
                    }).execute()
                    if insert_res.data:
                        st.success("✅ Atividade cadastrada com sucesso!")
                        iniciar_com_loading()

                    else:
                        st.error(f"❌ Erro ao cadastrar a atividade: {insert_res.error}")

            st.write("---")

            st.subheader("Editar Atividade Existente")
            if unidade_id:
                res_edit_ativ = supabase.table("atividades").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_edit_ativ = supabase.table("atividades").select("*").execute()
            atividades_edit = res_edit_ativ.data if res_edit_ativ.data else []
            if atividades_edit:
                atividade_escolhida = st.selectbox(
                    "Selecione a Atividade para editar",
                    options=atividades_edit,
                    format_func=lambda x: x["descricao"],
                    key="select_atividade_editar"
                )
                if atividade_escolhida:
                    nova_desc_edit = st.text_input("Nova Descrição", value=atividade_escolhida["descricao"], key=f"desc_edit_{atividade_escolhida['id']}")
                    # data_atv_edit = st.date_input("Data", value=atividade_escolhida.get("data",""), key=f"data_edit_{atividade_escolhida['id']}")
                    data_str = atividade_escolhida.get("data", "")
                    if isinstance(data_str, str) and data_str:
                        try:
                            valor_data = datetime.strptime(data_str, "%Y-%m-%d").date()

                            # AttributeError: module 'datetime' has no attribute 'strptime'

                        except ValueError:
                            valor_data = date.today()
                    elif isinstance(data_str, date):
                        valor_data = data_str
                    else:
                        valor_data = date.today()

                    data_atv_edit = st.date_input(
                        "Data",
                        value=valor_data,
                        key=f"data_edit_{atividade_escolhida['id']}"
                    )
                                    
                   
                   
                    status_padrao_ativ = (atividade_escolhida.get("status","Inativo") == "Ativo")
                    status_edit_ativ = st.checkbox("Ativo?", value=status_padrao_ativ, key=f"status_ativ_{atividade_escolhida['id']}")
                    if unidade_id:
                        st.write(f"Escritório: {st.session_state.get('selected_unidade')}")
                        chosen_esc_edit = unidade_id
                    else:
                        esc_nome_edit = st.selectbox("Escritório", nomes_escritorios_ativ,
                                                    index=nomes_escritorios_ativ.index(atividade_escolhida["escritorio_id"]) if atividade_escolhida["escritorio_id"] in nomes_escritorios_ativ else 0,
                                                    key=f"esc_edit_ativ_{atividade_escolhida['id']}")
                        chosen_esc_edit = dict_escritorios_ativ[esc_nome_edit]
                    if st.button("Atualizar Atividade", key=f"btn_atualizar_ativ_{atividade_escolhida['id']}"):
                        status_val_edit = "Ativo" if status_edit_ativ else "Inativo"
                        update_res = supabase.table("atividades").update({
                            "descricao": nova_desc_edit,
                            "data": str(data_atv_edit),
                            "status": status_val_edit,
                            "escritorio_id": chosen_esc_edit
                        }).eq("id", atividade_escolhida["id"]).execute()
                        if update_res.data:
                            st.success("Atividade atualizada com sucesso!")
                            iniciar_com_loading()

                        else:
                            st.error("Erro ao atualizar a atividade!")
            else:
                st.info("Não há atividades para editar.")

        # -------- ABA 3: Veículos --------
        with tabs_crud[2]:
            st.header("Gerenciamento de Veículos")
            if unidade_id:
                res_veic = supabase.table("veiculos").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_veic = supabase.table("veiculos").select("*").execute()
            if res_veic.data:
                st.subheader("Veículos Cadastrados")
                st.dataframe(res_veic.data)
            else:
                st.info("Nenhum veículo cadastrado.")
            st.write("---")
       
            st.subheader("Cadastrar Novo Veículo")

            lista_escritorios_veic = get_escritorios()
            dict_escritorios_veic = {esc["nome"]: esc["id"] for esc in lista_escritorios_veic}
            nomes_escritorios_veic = list(dict_escritorios_veic.keys())

            if unidade_id:
                st.write(f"Escritório: {st.session_state.get('selected_unidade')}")
                chosen_esc_veic = unidade_id
            else:
                esc_nome_veic = st.selectbox("Escritório", nomes_escritorios_veic, key="esc_veic_cadastro")
                chosen_esc_veic = dict_escritorios_veic[esc_nome_veic]

            with st.form("cadastro_veiculo"):
                nome_veic = st.text_input("Nome do Veículo", key="nome_veiculo").strip()
                status_veic = st.checkbox("Ativo?", value=True, key="status_veiculo_cadastro")
                submit_cadastro_veic = st.form_submit_button("Cadastrar Veículo")

            if submit_cadastro_veic:
                if not nome_veic:
                    st.error("❌ O nome do veículo é obrigatório.")
                else:
                    status_val = "Ativo" if status_veic else "Inativo"
                    insert_veic = supabase.table("veiculos").insert({
                        "veiculo": nome_veic,
                        "status": status_val,
                        "escritorio_id": chosen_esc_veic
                    }).execute()
                    if insert_veic.data:
                        st.success("✅ Veículo cadastrado com sucesso!")
                        iniciar_com_loading()

                    else:
                        st.error(f"❌ Erro ao cadastrar o veículo: {insert_veic.error}")

            st.write("---")
            st.subheader("Editar Veículo Existente")
            if unidade_id:
                res_edit_veic = supabase.table("veiculos").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_edit_veic = supabase.table("veiculos").select("*").execute()
            veiculos_edit = res_edit_veic.data if res_edit_veic.data else []
            if veiculos_edit:
                veic_escolhido = st.selectbox(
                    "Selecione o Veículo para editar",
                    options=veiculos_edit,
                    format_func=lambda x: x["veiculo"],
                    key="select_veic_editar"
                )
                if veic_escolhido:
                    novo_nome_veic = st.text_input("Novo Nome do Veículo", value=veic_escolhido["veiculo"], key=f"nome_veic_{veic_escolhido['id']}")
                    status_padrao_veic = (veic_escolhido.get("status", "Inativo") == "Ativo")
                    status_ativo_veic_edit = st.checkbox("Ativo?", value=status_padrao_veic, key=f"status_veic_{veic_escolhido['id']}")
                    st.write(f"Escritório atual (ID): {veic_escolhido.get('escritorio_id')}")
                    if st.button("Atualizar Veículo", key=f"btn_atualizar_veic_{veic_escolhido['id']}"):
                        status_val_edit = "Ativo" if status_ativo_veic_edit else "Inativo"
                        update_veic = supabase.table("veiculos").update({
                            "veiculo": novo_nome_veic,
                            "status": status_val_edit
                            # Não atualizamos o 'escritorio_id'
                        }).eq("id", veic_escolhido["id"]).execute()
                        if update_veic.data:
                            st.success("Veículo atualizado com sucesso!")
                            iniciar_com_loading()

                        else:
                            st.error("Erro ao atualizar o veículo!")
            else:
                st.info("Não há veículos para editar.")
    # ------------------------------------------------------------------------------
    # Aba 2: Programação
    # ------------------------------------------------------------------------------
    # ======================================================
    # FUNÇÕES AUXILIARES PARA IMPRESSÃO
    # ======================================================
    def build_cards_list(week_dates):
        cards_list = []
        for day_date in week_dates:
            date_str = day_date.strftime("%d/%m/%Y")
            day_label = f"{dia_semana_pt(day_date)} ({date_str})"
            
            day_acts = AtividadeState().get_dia(date_str)

            filtered_acts = []
            for act_idx, act in enumerate(day_acts):
                if act["atividade"] != "Expediente Administrativo":
                    act_key = f"checkbox_atividade_{date_str}_{act_idx}"
                    if not st.session_state.get(act_key, True):
                        continue

                filtered_servers = []
                for s in act["servidores"]:
                    server_key = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                    if st.session_state.get(server_key, True):
                        filtered_servers.append(s)

                if act["atividade"] != "Expediente Administrativo" and not filtered_servers:
                    continue

                new_act = {
                    "atividade": act["atividade"],
                    "servidores": filtered_servers,
                    "veiculo": act["veiculo"]
                }
                filtered_acts.append(new_act)
            cards_list.append({
                "Dia": day_label,
                "Activities": filtered_acts
            })
        return cards_list



    def build_atividades_por_servidor(week_dates):
        """
        Monta um dicionário {servidor: [lista de atividades]} para a impressão,
        considerando somente atividades e servidores com checkbox marcado.
        """
        atividades_por_servidor = {}
        for day_date in week_dates:
            date_str = day_date.strftime("%d/%m/%Y")
            day_acts = AtividadeState().get_dia(date_str)

            for act_idx, act in enumerate(day_acts):
                if act["atividade"] != "Expediente Administrativo":
                    act_key = f"checkbox_atividade_{date_str}_{act_idx}"
                    if not st.session_state.get(act_key, True):
                        continue  # atividade desmarcada
                    for s in act["servidores"]:
                        server_key = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                        if st.session_state.get(server_key, True):
                            if s not in atividades_por_servidor:
                                atividades_por_servidor[s] = []
                            atividades_por_servidor[s].append({
                                "Data": date_str,
                                "Atividade": act["atividade"]
                            })
        return atividades_por_servidor


    # ===================== INÍCIO DA ABA 2 =====================
    with tab2:
        with st.expander("🎯 Filtros da Programação: 🧑‍💼 Servidores | 🗂️ Atividades | 🚗 Veículos | 📝 ULSAV/Supervisão", expanded=False):
            col1, col2, col3,col4 = st.columns([2,2,1,1])
            # --- Coluna 1: Servidores Programação de Atividades ---
            with col1:
                unidade_id = st.session_state.get("selected_unidade_id", None)
                if unidade_id:
                    res_serv = supabase.table("servidores").select("nome").eq("escritorio_id", unidade_id).execute()
                    if res_serv.data:
                        # Extrai o primeiro nome de cada servidor
                        # nomes_servidores = [server["nome"].split()[0] for server in res_serv.data]
                        nomes_servidores = [server["nome"] for server in res_serv.data]
                    else:
                        nomes_servidores = []
                else:
                    nomes_servidores = []
                
                st.write("### 🧑‍💼 Servidores")

                sel_serv = st.multiselect(
                    "Selecione os Servidores",
                    nomes_servidores,
                    default=nomes_servidores,
                    key="multiselect_servidores_programacao_dados"
                )
                st.session_state["servidores"] = sel_serv

            # --- Coluna 2: Atividades ---
            with col2:
                unidade_id = st.session_state.get("selected_unidade_id", None)
                if unidade_id:
                    res_ativ = supabase.table("atividades").select("descricao").eq("escritorio_id", unidade_id).execute()
                    if res_ativ.data:
                        atividades_list = [atividade["descricao"] for atividade in res_ativ.data]
                    else:
                        atividades_list = []
                else:
                    atividades_list = []

                st.write("### 🗂️ Atividades")
                sel_ativ = st.multiselect(
                    "Selecione as Atividades",
                    atividades_list,
                    default=atividades_list,
                    key="multiselect_atividades"
                )
                st.session_state["atividades"] = sel_ativ

            # --- Coluna 3: Veículos ---
            with col3:
                unidade_id = st.session_state.get("selected_unidade_id", None)
                if unidade_id:
                    res_veic = supabase.table("veiculos").select("veiculo").eq("escritorio_id", unidade_id).execute()
                    if res_veic.data:
                        veiculos_list = [veic["veiculo"] for veic in res_veic.data]
                    else:
                        veiculos_list = []
                else:
                    veiculos_list = []

                st.write("### 🚗 Veículos")
                sel_veic = st.multiselect(
                    "Selecione os Veículos",
                    veiculos_list,
                    default=veiculos_list,
                    key="multiselect_veiculos"
                )
                st.session_state["veiculos"] = sel_veic

            # # --- Coluna 4: ULSAV e Supervisão ---
            with col4:
                unidade_id = st.session_state.get("selected_unidade_id", None)
                if unidade_id:
                    res_unidade = supabase.table("unidades").select("nome, supervisao").eq("id", unidade_id).execute()
                    if res_unidade.data and len(res_unidade.data) > 0:
                        row = res_unidade.data[0]
                        st.session_state["all_ul_sups"] = [row["nome"], row["supervisao"]]
                    else:
                        st.session_state["all_ul_sups"] = []
                else:
                    st.session_state["all_ul_sups"] = []

                st.write("### 📝ULSAV e Supervisão")

                sel_ul_sups = st.multiselect(
                    "Selecione ULSAV/ Supervisão",
                    st.session_state["all_ul_sups"],
                    default=st.session_state["all_ul_sups"],
                    key="multiselect_ul_sups"
                )
                st.session_state["ul_sups"] = sel_ul_sups

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("## 📋 Programação de Atividades", unsafe_allow_html=True)

            if (not st.session_state["servidores"]) or (not st.session_state["atividades"]) or (not st.session_state["veiculos"]):
                st.warning("Carregue e selecione Servidores, Atividades e Veículos na aba 'Dados'.")
            else:
                for ds, atividades in st.session_state.get("atividades_dia", {}).items():
                    for atividade in atividades:
                        if atividade["atividade"] == "Expediente Administrativo":
                            atividade["servidores"] = [s for s in atividade["servidores"] if s in st.session_state["servidores"]]

                st.markdown("##### 📅 Selecione uma data para criar (ou visualizar) a semana correspondente:")

                col_data, col_sabado, col_domingo = st.columns([2, 1, 1])
                with col_data:
                    selected_date = st.date_input("Data para a semana:", value=date.today())
                with col_sabado:
                    include_saturday = st.checkbox("Incluir Sábado", value=False)
                    include_sunday = st.checkbox("Incluir Domingo", value=False)
             
                if st.button("🗓️Adicionar Semana"):
                    add_week_if_not_exists(selected_date, include_saturday, include_sunday)
                

        # 🔚 Volta para o layout total da página
        st.markdown("---")

        if st.session_state["week_order"]:
           
                # Gera os rótulos das semanas
                week_labels = []

                for wid in st.session_state["week_order"]:
                    week_dates = st.session_state["semanas"].get(wid, [])
                    if not week_dates:
                        week_labels.append("Semana vazia")
                        continue

                    first_date = week_dates[0]
                    year = first_date.year
                    month = first_date.month
                    _, week_number = first_date.isocalendar()[:2]
                    first_day_of_month = date(year, month, 1)
                    _, first_week_number = first_day_of_month.isocalendar()[:2]
                    week_position_in_month = week_number - first_week_number + 1
                    if week_position_in_month < 1:
                        week_position_in_month = 1

                    ordinal_name = get_ordinal_week_in_month(week_position_in_month)
                    month_name_pt = NOME_MESES.get(month, f"[{month}]")
                    week_labels.append(f"{ordinal_name} semana do mês de {month_name_pt}")

                # Cria as abas com os nomes corretos
                weeks_tabs = st.tabs(week_labels)


               
                for idx, wid in enumerate(st.session_state["week_order"]):
                    with weeks_tabs[idx]:
                        st.markdown(f"##### {week_labels[idx]}")
                        week_dates = st.session_state["semanas"][wid]

                        # =============== TOPO: LINHA COM FORMULÁRIO + RESUMO ===============
                        top_col1, top_col2, top_col3 = st.columns([1, 1, 1])

                        # --- COLUNA 1: Botão de excluir semana
                        with top_col1:
                            if st.button("🗑️Excluir Semana", key=f"excluir_{wid}"):
                                remove_week(wid)
                                st.warning(f"Semana {wid} excluída!")
                                iniciar_com_loading()


                        # --- COLUNA 2: Formulário
                        with top_col2:
                       
                            st.markdown("#### ➕ Nova Atividade")

                            # Detecta mudança no dia e força atualização
                            dia_key = f"dia_select_{wid}"
                            if dia_key not in st.session_state:
                                st.session_state[dia_key] = week_dates[0]

                            selected_day = st.selectbox(
                                "Escolha o dia:",
                                options=week_dates,
                                format_func=lambda d: f"{dia_semana_pt(d)} - {d.strftime('%d/%m/%Y')}",
                                key=dia_key
                            )

                            # Verifica se o dia mudou e força atualização
                            prev_key = f"{dia_key}_prev"
                            if st.session_state.get(prev_key) != selected_day:
                                st.session_state[prev_key] = selected_day
                                iniciar_com_loading()


                            with st.form(key=f"form_nova_atividade_{wid}"):
                                atividade = st.selectbox("Atividade", st.session_state["atividades"])
                                veiculo = st.selectbox("Veículo", st.session_state["veiculos"])

                                # --- Recupera servidores já alocados hoje (exceto expediente)
                                def get_alocados_no_dia(chosen_date):
                                    ds = chosen_date.strftime("%d/%m/%Y")
                                    alocados = set()
                                    if ds in st.session_state["atividades_dia"]:
                                        for act in st.session_state["atividades_dia"][ds]:
                                            if act["atividade"] != "Expediente Administrativo":
                                                alocados.update(act["servidores"])
                                    return alocados

                                alocados_hoje = get_alocados_no_dia(selected_day)

                                def contar_alocacoes_por_servidor_na_semana(week_dates):
                                    contagem = {}
                                    for dia in week_dates:
                                        ds = dia.strftime("%d/%m/%Y")
                                        atividades = st.session_state["atividades_dia"].get(ds, [])
                                        for act in atividades:
                                            if act["atividade"] != "Expediente Administrativo":
                                                for s in act["servidores"]:
                                                    contagem[s] = contagem.get(s, 0) + 1
                                    return contagem

                                contagem = contar_alocacoes_por_servidor_na_semana(week_dates)
                                servidores_base = st.session_state["servidores"]
                                labels = []
                                mapa_label_para_nome = {}

                                for s in servidores_base:
                                    ja_alocado = "✅ " if s in alocados_hoje else ""
                                    count = contagem.get(s, 0)
                                    label = f"{ja_alocado}{s} ({count} atividades)"
                                    labels.append(label)
                                    mapa_label_para_nome[label] = s

                                servidores_escolhidos_labels = st.multiselect(
                                    "Servidores",
                                    options=labels,
                                    placeholder="Selecione um ou mais servidores..."
                                )
                                servidores_escolhidos = [mapa_label_para_nome[lbl] for lbl in servidores_escolhidos_labels]

                                if st.form_submit_button("➕ Adicionar"):
                                    date_str = selected_day.strftime("%d/%m/%Y")
                                    for act in st.session_state["atividades_dia"][date_str]:
                                        if act["atividade"] == "Expediente Administrativo":
                                            act["servidores"] = [s for s in act["servidores"] if s not in servidores_escolhidos]
                                            break

                                    AtividadeState().add_atividade(date_str, atividade, servidores_escolhidos, veiculo)
                                    iniciar_com_loading()



                        # --- COLUNA 3: Resumo da semana
                        with top_col3:
                            dias_com_atividades = []
                            for d in week_dates:
                                ds = d.strftime("%d/%m/%Y")
                                if any(act["atividade"] != "Expediente Administrativo" for act in st.session_state["atividades_dia"].get(ds, [])):
                                    dias_com_atividades.append(dia_semana_pt(d))
                            dias_label = "<br>".join(dias_com_atividades) if dias_com_atividades else "Nenhum"

                            activities_summary, servers_summary, vehicles_summary = get_summary_details_for_week(wid)

                            # Aplica CSS e estrutura em três colunas
                           # Garante ao menos uma linha na tabela
                            # Garante estrutura mesmo sem dados
                            dias_html = dias_label if dias_com_atividades else "Nenhum"
                            servidores_html = "".join([f"👤 <strong>{s.split()[0]}</strong>: {c}<br>" for s, c in servers_summary.items()]) or "Nenhum"
                            veiculos_html = "".join([f"🚗 <strong>{v}</strong>: {c}<br>" for v, c in vehicles_summary.items()]) or "Nenhum"
                            atividades_html = "".join([f"🗂️ <strong>{a}</strong>: {c}<br>" for a, c in activities_summary.items()]) or "Nenhum"

                            summary_html = f"""
                            <div class="summary-card">
                                <style>
                                    .resumo-semana-table {{
                                        width: 100%;
                                        border-collapse: collapse;
                                        font-family: Arial, sans-serif;
                                    }}
                                    .resumo-semana-table th {{
                                        background-color: #eaeaea;
                                        border: 1px solid #ccc;
                                        padding: 8px;
                                        text-align: center;
                                        font-weight: bold;
                                        font-size: 14px;
                                    }}
                                    .resumo-semana-table td {{
                                        border: 1px solid #ccc;
                                        padding: 8px;
                                        vertical-align: top;
                                        font-size: 13px;
                                        text-align: left;
                                    }}
                                    .resumo-semana-table tr:nth-child(even) {{
                                        background-color: #f9f9f9;
                                    }}
                                </style>
                                <table class="resumo-semana-table">
                                    <thead>
                                        <tr>
                                            <th>📅 Dias</th>
                                            <th>👥 Servidores</th>
                                            <th>🚗 Veículos</th>
                                            <th>📋 Atividades</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr>
                                            <td>{dias_html}</td>
                                            <td>{servidores_html}</td>
                                            <td>{veiculos_html}</td>
                                            <td>{atividades_html}</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                            """

                            st.markdown(summary_html, unsafe_allow_html=True)


                        st.markdown("---")


                        # =========== Listagem das atividades (um bloco por dia) ===========
                     
                        cols = st.columns(len(week_dates))

                        for j, current_date in enumerate(week_dates):
                            with cols[j]:
                                date_str = current_date.strftime("%d/%m/%Y")
                                day_name_pt = dia_semana_pt(current_date)

                                st.markdown(f"### {day_name_pt}")
                                st.markdown(f"**📅 {date_str}**")
                                st.markdown("---")

                                day_acts = AtividadeState().get_dia(date_str)

                                if day_acts:
                                    for idx_act, atividade in enumerate(day_acts):
                                        st.markdown(f"**🗂️ {atividade['atividade']}**")

                                        # Lista de servidores, um por linha
                                        if atividade["servidores"]:
                                            st.markdown("👥 **Servidores:**")
                                            st.markdown("\n".join([f"- {s}" for s in atividade["servidores"]]))
                                        else:
                                            st.markdown("👥 **Servidores:** Nenhum")

                                        # Veículo
                                        if atividade["veiculo"] and atividade["veiculo"] != "Nenhum":
                                            st.markdown(f"🚗 **Veículo:** {atividade['veiculo']}")
                                        else:
                                            st.markdown("🚗 **Veículo:** Nenhum")

                                        # BOTÃO DE REMOVER (apenas para atividades diferentes de expediente)
                                        if atividade["atividade"] != "Expediente Administrativo":
                                            if st.button("❌ Remover", key=f"remover_{date_str}_{idx_act}"):
                                                AtividadeState().remover_atividade(date_str, idx_act)
                                                iniciar_com_loading()

                                        st.markdown("---")
                                else:
                                    st.markdown("📭 Nenhuma atividade para este dia.")

                        st.markdown('<hr class="full-width-hr">', unsafe_allow_html=True)

                        # ===================== IMPRESSÃO: Semana Atual =====================
                      # ===================== IMPRESSÃO: Semana Atual =====================
                        report_col1, report_col2, report_col3 = st.columns([1,2,1])
                        with report_col2:
                            st.write("#### 🖨️ Impressões")
                            st.markdown("""
                            <style>
                            button[data-testid="stButton"] {
                                width: 100% !important;
                                font-size: 1rem !important;
                                text-align: left !important;
                            }
                            </style>
                            """, unsafe_allow_html=True)

                            plantao = st.selectbox(
                                "Plantão para recebimento de vacinas e agrotóxicos",
                                options=st.session_state["servidores"],
                                key=f"plantao_{wid}"
                            )

                            colA, colB = st.columns([1,1])
                            with colA:
                                # Usa a função build_cards_list para filtrar somente itens marcados
                                cards_list = build_cards_list(week_dates)
                                pdf_bytes_programacao = generate_pdf_for_week(
                                    cards_list,
                                    get_week_label(wid),
                                    st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada",
                                    st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada",
                                    plantao
                                )
                                st.download_button(
                                    label="📄 Imprimir Programação",
                                    data=pdf_bytes_programacao,
                                    file_name="programacao_semana.pdf",
                                    mime="application/pdf",
                                    key=f"download_prog_{wid}_{idx}_prog"
                                )
                            with colB:
                                # Usa a função build_atividades_por_servidor para filtrar atividades por servidor
                                atividades_por_servidor = build_atividades_por_servidor(week_dates)
                                pdf_bytes_relatorio = pdf_relatorio.generate_pdf_for_atividades(
                                    atividades_por_servidor,
                                    get_week_label(wid), 
                                    st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada",
                                    st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada"
                                )
                                st.download_button(
                                    label="📝 Imprimir relatório de atividades",
                                    data=pdf_bytes_relatorio,
                                    file_name="relatorio_semana.pdf",
                                    mime="application/pdf",
                                    key=f"download_relatorio_{wid}_{idx}_rel"
                                )
                        st.markdown("---")
                  
                # ===================== IMPRESSÕES - Todas as Semanas =====================
                st.subheader("🖨️ Impressões - Todas as Semanas")
                col_global1, col_global2 = st.columns(2)
                st.markdown("---")

                with col_global1:
                    if st.button("📄 Gerar Programação (Todas as Semanas)"):
                        cards_list_all = []
                        for w_index, w_id in enumerate(st.session_state["week_order"]):
                            week_dates_all = st.session_state["semanas"][w_id]
                            cards_list_all.append({
                                "Dia": f"--- {get_week_label(w_id)} ---",
                                "Activities": []
                            })
                            filtered = build_cards_list(week_dates_all)
                            cards_list_all.extend(filtered)

                        all_weeks_label = "Programação de Todas as Semanas"
                        pdf_bytes_all_prog = generate_pdf_for_week(
                            cards_list_all,
                            all_weeks_label,
                            st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada",
                            st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada",
                            ""
                        )
                        st.download_button(
                            label="📥 Baixar Programação (Todas as Semanas)",
                            data=pdf_bytes_all_prog,
                            file_name="programacao_todas_semanas.pdf",
                            mime="application/pdf",
                            key="download_prog_all"
                        )

                with col_global2:
                    if st.button("📝 Gerar Relatório (Todas as Semanas)"):
                        atividades_por_servidor_all = {}
                        for w_index, w_id in enumerate(st.session_state["week_order"]):
                            week_dates_all = st.session_state["semanas"][w_id]
                            parcial = build_atividades_por_servidor(week_dates_all)
                            for servidor, lista_ativ in parcial.items():
                                if servidor not in atividades_por_servidor_all:
                                    atividades_por_servidor_all[servidor] = []
                                atividades_por_servidor_all[servidor].extend(lista_ativ)

                        all_weeks_label = "Relatório de Atividades (Todas as Semanas)"
                        pdf_bytes_all_rel = pdf_relatorio.generate_pdf_for_atividades(
                            atividades_por_servidor_all,
                            all_weeks_label,
                            st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada",
                            st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada"
                        )
                        st.download_button(
                            label="📥 Baixar Relatório (Todas as Semanas)",
                            data=pdf_bytes_all_rel,
                            file_name="relatorio_todas_semanas.pdf",
                            mime="application/pdf",
                            key="download_relatorio_all"
                        )

    # ===== Início da aba 3: Plantão =====
    with tab3:
                # Layout geral com colunas
        col_esq, col_centro, col_dir = st.columns([1, 1.5, 1])   
        # Parte centralizada
        with col_centro:
    # --- Parte: Carregamento dos dados dos servidores para o plantão ---
            unidade_id = st.session_state.get("selected_unidade_id", None)
            if unidade_id:
                res = supabase.table("servidores").select("nome, telefone").eq("escritorio_id", unidade_id).execute()
                if res.data:
                    st.session_state["plantao_itens"] = [(row["nome"], row["telefone"]) for row in res.data]
                else:
                    st.session_state["plantao_itens"] = []
            else:
                st.session_state["plantao_itens"] = []

            # --- Seleção dos servidores ---
            render_selecao_servidores()

            # --- Exibe tabela de servidores selecionados ---
            itens = st.session_state.get("plantao_itens", [])
            selected_names = st.session_state.get("selected_plantao_names", [])

            st.write("### 📊 Dados Carregados para o Plantão")
            with st.expander("Ver tabela selecionada"):
                col1, col2 = st.columns(2)
                col1.header("🧑 Nome")
                col2.header("📞 Telefone")
                for nome, telefone in itens:
                    if nome in selected_names:
                        col1.write(nome)
                        col2.write(telefone)

            st.divider()
        st.markdown("#### 🔄 Informe os servidores que estão de férias ou afastados e gere a escala)")
            # --- Indisponibilidades ---
        with st.expander("Indisponibilidades", expanded=False):
                render_indisponibilidades()

        st.divider()

            # --- Geração da Escala ---
        st.subheader("🗓️ Gerar Escala de Plantão (Sábado a Sexta)")
        render_cronograma_plantao()

    with tab4:
            col_esq, col_centro, col_dir = st.columns([1, 1.5, 1])   
            with col_centro:
               
                supabase = get_supabase_client()
                render_formulario_ferias(supabase)
                render_tabela_ferias()
                render_botao_gerar_pdf()
            
    with tab5: 
            col_esq, col_centro, col_dir = st.columns([1, 1.5, 1])   
            with col_centro:
                try:
                    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
                except locale.Error:
                    pass  # Caso o sistema não tenha pt_BR, ignora

                # ================================
                # CSS Global
                # ================================
                container_css = """
                <style>
                    /* Remove negrito dos itens do radio */
                    div[data-baseweb="radio"] label {
                        font-weight: normal !important;
                        font-family: inherit !important;
                        font-size: 1rem !important;
                    }
                    header {
                        visibility: hidden;
                    }

                    .parcelamento-container {
                        background-color: #ffffff;
                        border-radius: 0.5rem;
                        padding: 2rem;
                        margin-top: 2rem;
                        margin-bottom: 2rem;
                        max-width: 800px;
                        width: 100%;
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                        margin-left: auto;
                        margin-right: auto;
                    }

                    .parcelamento-container h1 {
                        text-align: center;
                    }

                    @media print {
                        .no-print, .print-button {
                            display: none !important;
                        }
                    }
                </style>
                """
                st.markdown(container_css, unsafe_allow_html=True)
                st.markdown("<div class='parcelamento-container'>", unsafe_allow_html=True)


                # ================================
                # Função para formatação de moeda
                # ================================
                def formatar_moeda_br(valor):
                    """Converte float para BRL formatado, ex: 1234.5 -> R$ 1.234,50"""
                    return format_currency(valor, 'BRL', locale='pt_BR')

                # ================================
                # Título e Abas
                # ================================
                st.title("Parcelar Auto de Infração")
                tabs = st.tabs(["Preencher Requerimento", "Tabela de Descontos"])

                # ================================
                # ABA 1: Preencher Requerimento
                # ================================
                with tabs[0]:
                    # -------------------------------------------------
                    # Expander para DADOS DO AUTO DE INFRAÇÃO
                    # -------------------------------------------------
                    with st.expander("Dados do Auto de Infração", expanded=True):
                        st.subheader("Dados do Auto de Infração")

                        col1, col2 = st.columns(2)
                        with col1:
                            # Data do Requerimento
                            data_requerimento = st.date_input("Data do requerimento", datetime.today())
                            st.session_state["data_requerimento"] = data_requerimento

                        with col2:
                            # Data do Auto de Infração
                            data_auto = st.date_input("Data do Auto de Infração", datetime.today())
                            st.session_state["data_auto"] = data_auto

                        # Número do Auto de Infração
                        if "N_auto" not in st.session_state:
                            st.session_state["N_auto"] = ""
                        N_auto = st.text_input("Número do Auto de Infração:", value=st.session_state["N_auto"])
                        st.session_state["N_auto"] = N_auto

                    # -------------------------------------------------
                    # Expander para DADOS DO AUTUADO
                    # -------------------------------------------------
                    with st.expander("Dados do Autuado", expanded=True):
                        st.subheader("Dados do Autuado")
                        with st.form("form_requerimento"):
                            # Garante chaves no session_state
                            for campo in ["nome_completo", "cpf", "endereco", "municipio"]:
                                if campo not in st.session_state:
                                    st.session_state[campo] = ""

                            nome_completo = st.text_input("Nome completo:", value=st.session_state["nome_completo"])
                            cpf = st.text_input("N° do CPF:", value=st.session_state["cpf"])
                            endereco = st.text_input("Endereço:", value=st.session_state["endereco"])
                            municipio = st.text_input("Município:", value=st.session_state["municipio"])

                            colA, colB, colC = st.columns(3)
                            with colA:
                                valor_upf = st.text_input("Valor da UPF:", value="119,14")
                            with colB:
                                # MUDOU AQUI
                                qtd_upf_por_animal = st.number_input("Qtd UPF por animal/Auto:", min_value=0.0, step=0.5, value=2.5)
                            with colC:
                                qtd_upf_por_parcela = st.number_input("Qtd mínima de UPF por parcela:", min_value=0.0, step=0.5, value=3.0)

                            # MUDOU AQUI
                            n_animais = st.number_input("Número de Animais/Auto de Infração:", min_value=0, step=1)

                            prazo_defesa_escolhido = st.radio(
                                "No prazo de defesa até 30 dias?",
                                ("Sim (Desconto de 20% pra uma parcela)", "Não (Desconto de 10% pra uma parcela)")
                            )

                            submit_form = st.form_submit_button("Aplicar / Atualizar")

                        if submit_form:
                            # Salva dados no session_state
                            st.session_state["nome_completo"] = nome_completo
                            st.session_state["cpf"] = cpf
                            st.session_state["endereco"] = endereco
                            st.session_state["municipio"] = municipio
                            st.session_state["prazo_defesa"] = prazo_defesa_escolhido

                            try:
                                valor_upf_float = float(valor_upf.replace(",", "."))
                            except ValueError:
                                st.error("Valor da UPF inválido, usando 0.")
                                valor_upf_float = 0.0

                            st.session_state["valor_upf_float"] = valor_upf_float
                            st.session_state["qtd_upf_por_animal"] = qtd_upf_por_animal
                            st.session_state["qtd_upf_por_parcela"] = qtd_upf_por_parcela
                            st.session_state["n_animais"] = n_animais

                    # --------------------------
                    # Cálculos de parcelas
                    # --------------------------
                    valor_upf_float = st.session_state.get("valor_upf_float", 0.0)
                    total_upf = st.session_state.get("n_animais", 0) * st.session_state.get("qtd_upf_por_animal", 0) * valor_upf_float

                    if total_upf > 0:
                        st.metric("Valor do Auto", formatar_moeda_br(total_upf))
                    else:
                        st.write("Valor do Auto: R$ 0,00")

                    if valor_upf_float > 0:
                        min_valor_parcela = st.session_state["qtd_upf_por_parcela"] * valor_upf_float
                    else:
                        min_valor_parcela = 0

                    if total_upf >= min_valor_parcela and min_valor_parcela > 0:
                        num_max_parcelas = int(total_upf // min_valor_parcela)
                    else:
                        num_max_parcelas = 0
                    num_max_parcelas = min(num_max_parcelas, 30)
                    

                    # ================================
                    # Mensagem de desconto
                    # ================================
                    if prazo_defesa_escolhido == "Sim (Desconto de 20% pra uma parcela)":
                        desconto_mensagem = "**Desconto aplicado para prazo dentro dos 30 dias**"
                        coluna_desconto = "Desconto Concedido (Integral)"
                    else:
                        desconto_mensagem = "**Desconto aplicado para prazo fora dos 30 dias**"
                        coluna_desconto = "Desconto Concedido (metade)"

                    # Exibir desconto antes da legenda
                    st.markdown(desconto_mensagem)



                    if num_max_parcelas > 0:
                        st.write(
                            f"É possível parcelar em até {num_max_parcelas} vezes, respeitando "
                            f"o valor mínimo de R$ {min_valor_parcela:.2f} por parcela."
                        )
                    else:
                        st.write(
                            f"O valor total é menor que o mínimo exigido para uma parcela: R$ {min_valor_parcela:.2f}."
                        )

                    global parcelas_selecionadas_df
                    parcelas_selecionadas_df = pd.DataFrame(columns=['Parcela','Valor da Parcela','Data de Vencimento']).set_index("Parcela")

                    if st.session_state.get("prazo_defesa") == "Sim (Desconto de 20% pra uma parcela)":
                        coluna_desconto = "Desconto Concedido (Integral)"
                    else:
                        coluna_desconto = "Desconto Concedido (metade)"

                    # Expander com tabela de possíveis descontos
                    if num_max_parcelas > 0:
                        with st.expander("Opções de Parcelamento", expanded=True):
                            data_dict = {
                                "Quantidade de Parcelas": list(range(1, 32)),
                                "Desconto Concedido (Integral)": [
                                    20, 12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8,
                                    7.5, 7, 6.5, 6, 5.5, 5, 4.5, 4, 3.5, 3,
                                    2.5, 2, 1.75, 1.5, 1.25, 1, 0.75, 0.5, 0.25, 0, 0
                                ],
                                "Desconto Concedido (metade)": [
                                    10, 6, 5.75, 5.5, 5.25, 5, 4.75, 4.5, 4.25, 4,
                                    3.75, 3.5, 3.25, 3, 2.75, 2.5, 2.25, 2, 1.75, 1.5,
                                    1.25, 1, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0, 0
                                ]
                            }

                            df_descontos = pd.DataFrame(data_dict)
                            df_descontos["Desconto (%)"] = df_descontos[coluna_desconto].apply(lambda x: f"{x}%")
                            df_descontos["Valor com Desconto"] = total_upf * (1 - df_descontos[coluna_desconto]/100)
                            df_descontos["Valor da Parcela"] = df_descontos["Valor com Desconto"] / df_descontos["Quantidade de Parcelas"]
                            df_descontos["Desconto Concedido"] = total_upf - df_descontos["Valor com Desconto"]

                            # Formata em R$
                            df_descontos["Valor com Desconto Formatado"] = df_descontos["Valor com Desconto"].apply(formatar_moeda_br)
                            for c in ["Valor com Desconto","Valor da Parcela","Desconto Concedido"]:
                                df_descontos[c] = df_descontos[c].apply(formatar_moeda_br)

                            df_parcelas = df_descontos.head(num_max_parcelas)

                            # Linha em branco no fim
                            linha_branco = pd.DataFrame([["" for _ in range(len(df_parcelas.columns))]], columns=df_parcelas.columns)
                            df_parcelas = pd.concat([df_parcelas, linha_branco], ignore_index=True)

                            df_parcelas = df_parcelas[
                                ["Quantidade de Parcelas","Desconto (%)","Desconto Concedido","Valor com Desconto","Valor da Parcela"]
                            ]

                            gb = GridOptionsBuilder.from_dataframe(df_parcelas)
                            gb.configure_default_column(groupable=True, value=True, enableRowGroup=True, aggFunc='sum', editable=True)
                            gb.configure_selection('single', use_checkbox=True, groupSelectsChildren=True)
                            grid_options = gb.build()

                            grid_response = AgGrid(
                                df_parcelas.reset_index(drop=True),
                                gridOptions=grid_options,
                                height=300,
                                width='100%',
                                data_return_mode='AS_INPUT',
                                update_mode='MODEL_CHANGED',
                                fit_columns_on_grid_load=False,
                                theme='streamlit',
                                allow_unsafe_jscode=True,
                            )

                            st.write("**Selecione a quantidade de parcelas** na primeira coluna para gerar o requerimento.")

                            selected = grid_response['selected_rows']
                            selected_df = pd.DataFrame(selected)

                            if not selected_df.empty:
                                num_parcelas_selecionadas = int(selected_df.iloc[0]["Quantidade de Parcelas"])
                                discount_row = df_descontos[df_descontos["Quantidade de Parcelas"] == num_parcelas_selecionadas].iloc[0]
                                discount_percentage = discount_row[coluna_desconto]

                                # Valor com desconto
                                valor_com_desconto = total_upf * (1 - discount_percentage / 100)
                                valor_parcela_final = valor_com_desconto / num_parcelas_selecionadas

                                # Cria dataframe de parcelas
                                dados_parcelas = []
                                for i in range(1, num_parcelas_selecionadas + 1):
                                    data_venc = data_requerimento + pd.DateOffset(months=i - 1)
                                    dados_parcelas.append({
                                        "Parcela": i,
                                        "Valor da Parcela": f"R$ {valor_parcela_final:,.2f}".replace(',', 'X').replace('.', ',').replace('X','.'),
                                        "Data de Vencimento": data_venc.strftime("%d/%m/%Y")
                                    })
                                parcelas_selecionadas_df = pd.DataFrame(dados_parcelas).set_index("Parcela")

                    # ================================
                    # Exibir Requerimento (HTML)
                    # ================================
                    if not parcelas_selecionadas_df.empty:
                        # Recupera dados
                        data_req_label = st.session_state["data_requerimento"].strftime('%d/%m/%Y')
                        data_auto_label = st.session_state["data_auto"].strftime('%d/%m/%Y')
                        N_auto = st.session_state.get("N_auto", "")
                        nome_completo = st.session_state.get("nome_completo", "")
                        cpf = st.session_state.get("cpf", "")
                        endereco = st.session_state.get("endereco", "")
                        municipio = st.session_state.get("municipio", "")

                        total_upf_float = st.session_state.get("valor_upf_float",0.0)
                        total_upf = st.session_state.get("n_animais",0) * st.session_state.get("qtd_upf_por_animal",0) * total_upf_float

                        discount_percentage = locals().get("discount_percentage", 0)
                        valor_com_desconto = locals().get("valor_com_desconto", 0)
                        valor_parcela_final = locals().get("valor_parcela_final", 0)
                        num_parcelas = parcelas_selecionadas_df.shape[0]

                        desconto_reais = total_upf - valor_com_desconto
                        if desconto_reais < 0:
                            desconto_reais = 0

                        # Texto principal do requerimento
                        texto_requerimento = f"""
                        Eu, {nome_completo}, brasileiro(a), portador(a) do CPF nº {cpf}, residente no endereço {endereco}, município de {municipio},
                        venho, por meio deste requerimento datado de {data_req_label}, solicitar o parcelamento do Auto de Infração nº {N_auto}, 
                        lavrado em {data_auto_label}, nos termos da legislação vigente.
                        """

                        if total_upf > 0 and num_parcelas > 0:
                            texto_parcelamento = (
                                f"O requerente solicitou o parcelamento em {num_parcelas} vezes, conforme a tabela de descontos, "
                                f"o que lhe confere o direito a um desconto de {discount_percentage}% "
                                f"(equivalente a {formatar_moeda_br(desconto_reais)}) "
                                f"sobre o valor inicial. Assim, o valor total, que originalmente era de "
                                f"{formatar_moeda_br(total_upf)}, passará a ser de {formatar_moeda_br(valor_com_desconto)}, "
                                f"distribuído em {num_parcelas} parcelas de {formatar_moeda_br(valor_parcela_final)} cada."
                            )
                        else:
                            texto_parcelamento = (
                                "Não é possível parcelar, pois o valor total é inferior ao mínimo exigido para uma parcela."
                            )

                        # HTML final
                        html = f"""
                        <!DOCTYPE html>
                        <html lang="pt-BR">
                        <head>
                            <meta charset="UTF-8">
                            <title>Requerimento de Parcelamento</title>
                            <style>
                                @page {{
                                    margin: 20mm;
                                    @bottom-center {{
                                        content: "Página " counter(page) " de " counter(pages);
                                        font-size: 10pt;
                                    }}
                                }}
                                body {{
                                    font-family: Arial, sans-serif;
                                    margin: 20px;
                                    padding: 20px;
                                }}
                                p {{
                                    text-indent: 2em;
                                }}
                                .container {{
                                    max-width: 800px;
                                    margin: auto;
                                    padding: 20px;
                                    border: 1px solid #ccc;
                                    border-radius: 10px;
                                }}
                                h2 {{
                                    text-align: center;
                                }}
                                .texto-requerimento {{
                                    margin-top: 20px;
                                    line-height: 1.5;
                                    text-align: justify;
                                }}
                                .texto-parcelamento {{
                                    margin-top: 20px;
                                    font-weight: bold;
                                    text-align: justify;
                                }}
                                table {{
                                    width: 100%;
                                    border-collapse: collapse;
                                    margin-top: 20px;
                                }}
                                th, td {{
                                    border: 1px solid #ddd;
                                    padding: 10px;
                                    text-align: center;
                                }}
                                th {{
                                    background-color: #f4f4f4;
                                }}
                                .signature {{
                                    margin-top: 40px;
                                    text-align: center;
                                }}
                                .signature p {{
                                    margin: 0;
                                    text-align: center;
                                }}
                                .print-button {{
                                    display: block;
                                    text-align: center;
                                    margin-top: 20px;
                                }}
                                @media print {{
                                    .no-print, .print-button {{
                                        display: none !important;
                                    }}
                                }}
                            </style>
                        </head>
                        <body>
                            <div class="container">
                                <h2>Requerimento para Parcelamento de Auto de Infração - Emitido pela Agência IDARON</h2>

                                <div class="texto-requerimento">
                                    <p>{texto_requerimento}</p>
                                </div>

                                <div class="texto-parcelamento">
                                    <p>{texto_parcelamento}</p>
                                </div>

                                <h3>Parcelas e Vencimentos</h3>
                                <table>
                                    <tr>
                                        <th>Parcela</th>
                                        <th>Valor da Parcela</th>
                                        <th>Data de Vencimento</th>
                                    </tr>
                        """
                        # Linhas da tabela
                        for index, row in parcelas_selecionadas_df.iterrows():
                            html += f"""
                                    <tr>
                                        <td>{index}</td>
                                        <td>{row['Valor da Parcela']}</td>
                                        <td>{row['Data de Vencimento']}</td>
                                    </tr>
                            """
                        # Assinatura (2 linhas de espaço + linha mais longa)
                        html += f"""
                                </table>

                                <div class="signature">
                                    <p>Segue assinado</p>
                                    <br><br>
                                    <p>________________________________________</p>
                                    <p>{nome_completo}</p>
                                    <p>{cpf}</p>
                                </div>

                                <div class="print-button no-print">
                                    <button onclick="window.print()">Imprimir Requerimento</button>
                                </div>
                            </div>
                        </body>
                        </html>
                        """

                        components.html(html, height=800, scrolling=True)
                st.markdown("</div>", unsafe_allow_html=True)

                # ================================
                # ABA 2: Tabela de Descontos
                # ================================
                with tabs[1]:
                    st.markdown("### Tabela de Descontos")
                    Dados = {
                        "Quantidade de Parcelas": range(1, 31),
                        "Desconto Concedido (Integral)": [
                            20, 12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8,
                            7.5, 7, 6.5, 6, 5.5, 5, 4.5, 4, 3.5, 3,
                            2.5, 2, 1.75, 1.5, 1.25, 1, 0.75, 0.5, 0.25, 0
                        ],
                        "Desconto Concedido (metade)": [
                            10, 6, 5.75, 5.5, 5.25, 5, 4.75, 4.5, 4.25, 4,
                            3.75, 3.5, 3.25, 3, 2.75, 2.5, 2.25, 2, 1.75, 1.5,
                            1.25, 1, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0
                        ]
                    }
                    df_desc = pd.DataFrame(Dados)
                    df_html = df_desc.to_html(index=False)
                    df_html_styled = f"<style>td, th {{text-align: center;}}</style>{df_html}"
                    st.markdown(df_html_styled, unsafe_allow_html=True)


if __name__ == "__main__":
    main_app()