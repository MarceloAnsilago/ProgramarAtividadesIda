import streamlit as st
from datetime import date, timedelta
from io import BytesIO
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

NOME_MESES = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }



# [REFATORADO] Classe auxiliar para encapsular interações com atividades da semana
class SemanaManager:
    def __init__(self):
        self.dados = st.session_state.setdefault("atividades_dia", {})

    def get_dia(self, data_str):
        return self.dados.setdefault(data_str, [])

    def add_atividade(self, data_str, atividade, servidores, veiculo):
        self.get_dia(data_str).append({
            "atividade": atividade,
            "servidores": servidores,
            "veiculo": veiculo
        })

    def remover_atividade(self, data_str, idx):
        atividade = self.dados.get(data_str, [])[idx]
        for s in atividade["servidores"]:
            self.adicionar_no_expediente(data_str, s)
        del self.dados[data_str][idx]

    def remover_servidor(self, data_str, idx, servidor):
        atividade = self.dados.get(data_str, [])[idx]
        if atividade["atividade"] != "Expediente Administrativo":
            if servidor in atividade["servidores"]:
                atividade["servidores"].remove(servidor)
                self.adicionar_no_expediente(data_str, servidor)

    def adicionar_no_expediente(self, data_str, servidor):
        for atividade in self.dados.get(data_str, []):
            if atividade["atividade"] == "Expediente Administrativo":
                if servidor not in atividade["servidores"]:
                    atividade["servidores"].append(servidor)
                return


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


# [REFATORADO] Gerenciador leve de checkboxes
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
                        st.rerun()
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
dias_semana = {
    "Monday": "Segunda-feira",
    "Tuesday": "Terça-feira",
    "Wednesday": "Quarta-feira",
    "Thursday": "Quinta-feira",
    "Friday": "Sexta-feira",
    "Saturday": "Sábado",
    "Sunday": "Domingo"
}


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
    if wid not in st.session_state["semanas"]:
        st.session_state["semanas"][wid] = get_week_dates(ref_date, include_saturday, include_sunday)
        st.session_state["week_order"].append(wid)

        # Garante que "servidores" está disponível antes de usar
        servidores = st.session_state.get("servidores", [])
        for day_date in st.session_state["semanas"][wid]:
            add_activity_to_date(
                day_date,
                atividade="Expediente Administrativo",
                servidores=servidores,
                veiculo="Nenhum"
            )


# [REFATORADO]
def add_activity_to_date(activity_date, atividade, servidores, veiculo):
    date_str = activity_date.strftime("%d/%m/%Y")
    SemanaManager().add_atividade(date_str, atividade, servidores, veiculo)



def add_server_to_expediente(date_str, server):
    for act in st.session_state["atividades_dia"].get(date_str, []):
        if act["atividade"] == "Expediente Administrativo":
            if server not in act["servidores"]:
                act["servidores"].append(server)
            return

# [REFATORADO]
def remove_server_from_card(date_str, card_index, server):
    SemanaManager().remover_servidor(date_str, card_index, server)

# [REFATORADO]
def remove_activity_card(date_str, card_index):
    SemanaManager().remover_atividade(date_str, card_index)




def remove_week(week_id):
    if week_id in st.session_state["semanas"]:
        for day_date in st.session_state["semanas"][week_id]:
            date_str = day_date.strftime("%d/%m/%Y")
            if date_str in st.session_state["atividades_dia"]:
                del st.session_state["atividades_dia"][date_str]
        del st.session_state["semanas"][week_id]
    if week_id in st.session_state["week_order"]:
        st.session_state["week_order"].remove(week_id)

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
        day_acts = st.session_state["atividades_dia"].get(date_str, [])
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
        day_name_en = day_date.strftime("%A")
        day_label = f"{dias_semana.get(day_name_en, day_name_en)} ({date_str})"
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

def main_app():
  
    # ------------------------------------------------------------------------------
    # Layout com Abas
    # ------------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dados (Informações Gerais)", 
        "🗓️ Programação (Gerar programação de atividades)", 
        "📦 Programação para recebimento",
        "📅 Gerar Escala de Férias"
    ])
    # ------------------------------------------------------------------------------
    # Aba 1: Dados
    # ------------------------------------------------------------------------------
    with tab1:
        # Configurações do Supabase
        SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wlbvahpkcaksqkzdhnbv.supabase.co")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndsYnZhaHBrY2Frc3FremRobmJ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDMyODMxMTUsImV4cCI6MjA1ODg1OTExNX0.Cph86UhT8Q67-1x2oVfTFyELgQqWRgJ3yump1JpHSc8")
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
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
                novo_nome = st.text_input("Nome do Servidor", key="novo_nome_servidor")
                novo_telefone = st.text_input("Telefone", key="novo_telefone_servidor")
                nova_matricula = st.text_input("Matrícula", key="nova_matricula_servidor")
                novo_cargo = st.text_input("Cargo", key="novo_cargo_servidor")
                status_servidor = st.checkbox("Ativo?", value=True, key="status_servidor_cadastro")
                submit_cadastro_serv = st.form_submit_button("➕ Cadastrar Servidor")
            if submit_cadastro_serv:
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
                    st.rerun()
                else:
                    st.error("❌ Erro ao cadastrar o servidor. {insert_res.error}")
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
                            st.rerun()
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
                desc_atividade = st.text_input("Descrição", key="desc_atividade")
                data_atividade = st.date_input("Data", key="data_atividade")
                status_atividade = st.checkbox("Ativo?", value=True, key="status_atividade_cadastro")
                submit_cadastro_ativ = st.form_submit_button("Cadastrar Atividade")
            if submit_cadastro_ativ:
                status_val = "Ativo" if status_atividade else "Inativo"
                insert_res = supabase.table("atividades").insert({
                    "descricao": desc_atividade,
                    "data": data_atividade.isoformat(),
                    "status": status_val,
                    "escritorio_id": chosen_esc_ativ
                }).execute()
                if insert_res.data:
                    st.success("Atividade cadastrada com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro ao cadastrar a atividade: {insert_res.error}")
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
                            st.rerun()
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
                nome_veic = st.text_input("Nome do Veículo", key="nome_veiculo")
                status_veic = st.checkbox("Ativo?", value=True, key="status_veiculo_cadastro")
                submit_cadastro_veic = st.form_submit_button("Cadastrar Veículo")
            if submit_cadastro_veic:
                status_val = "Ativo" if status_veic else "Inativo"
                insert_veic = supabase.table("veiculos").insert({
                    "veiculo": nome_veic,
                    "status": status_val,
                    "escritorio_id": chosen_esc_veic
                }).execute()
                if insert_veic.data:
                    st.success("Veículo cadastrado com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro ao cadastrar o veículo: {insert_veic.error}")
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
                            st.rerun()
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
        """
        Monta a lista de cards (dia a dia) para a impressão,
        filtrando as atividades e servidores com base no estado dos checkboxes.
        """
        cards_list = []
        for day_date in week_dates:
            date_str = day_date.strftime("%d/%m/%Y")
            day_name_en = day_date.strftime("%A")
            day_label = f"{dias_semana.get(day_name_en, day_name_en)} ({date_str})"
            
            day_acts = st.session_state["atividades_dia"].get(date_str, [])
            filtered_acts = []
            for act_idx, act in enumerate(day_acts):
                # Para atividades diferentes de "Expediente Administrativo",
                # verificamos se o checkbox da atividade está marcado.
                if act["atividade"] != "Expediente Administrativo":
                    act_key = f"checkbox_atividade_{date_str}_{act_idx}"
                    if not st.session_state.get(act_key, True):
                        continue  # ignora atividade desmarcada
                
                # Filtra servidores: inclui apenas os que estiverem marcados.
                filtered_servers = []
                for s in act["servidores"]:
                    server_key = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                    if st.session_state.get(server_key, True):
                        filtered_servers.append(s)
                # Se não for Expediente e não houver servidores, ignora a atividade
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
            day_acts = st.session_state["atividades_dia"].get(date_str, [])
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

        st.header("📋 Programação de Atividades")
        if (not st.session_state["servidores"]) or (not st.session_state["atividades"]) or (not st.session_state["veiculos"]):
            st.warning("Carregue e selecione Servidores, Atividades e Veículos na aba 'Dados'.")
        else:
            # Atualiza os cartões de "Expediente Administrativo" (mantém apenas os servidores ativos)
            for ds, atividades in st.session_state.get("atividades_dia", {}).items():
                for atividade in atividades:
                    if atividade["atividade"] == "Expediente Administrativo":
                        atividade["servidores"] = [s for s in atividade["servidores"] if s in st.session_state["servidores"]]

            st.write("📅 Selecione uma data para criar (ou visualizar) a semana correspondente:")

            selected_date = st.date_input("Data para a semana:", value=date.today())

            colA, colB = st.columns(2)
            with colA:
                include_saturday = st.checkbox("Incluir Sábado", value=False)
            with colB:
                include_sunday = st.checkbox("Incluir Domingo", value=False)

            if st.button("🗓️Adicionar Semana"):
                add_week_if_not_exists(selected_date, include_saturday, include_sunday)
                st.session_state["recarregar"] = True
                st.rerun()

            st.markdown("---")

            if st.session_state["week_order"]:
                # Gera os rótulos das semanas
                labels = []
                if st.session_state["week_order"]:
                    for wid in st.session_state["week_order"]:
                        week_dates = st.session_state["semanas"].get(wid, [])
                        if not week_dates:
                            labels.append("Semana vazia")
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
                        month_name_pt = [month]
                        labels.append(f"{ordinal_name} semana do mês de {month_name_pt}")

                weeks_tabs = st.tabs(labels)

                for idx, wid in enumerate(st.session_state["week_order"]):
                    with weeks_tabs[idx]:
                        st.markdown(f"##### {labels[idx]}")
                        # Linha superior: Excluir Semana | Formulário para adicionar atividade | Resumo visual
                        top_col1, top_col2, top_col3 = st.columns([1,1,1])

                        with top_col1:
                            if st.button("🗑️Excluir Semana", key=f"excluir_{wid}"):
                                remove_week(wid)
                                st.warning(f"Semana {wid} excluída!")
                                st.rerun()

                        week_dates = st.session_state["semanas"][wid]
                        day_options = [f"{dias_semana[d.strftime('%A')]} - {d.strftime('%d/%m/%Y')}" for d in week_dates]
                        option_to_date = {option: d for option, d in zip(day_options, week_dates)}

                        with top_col2:
                            chosen_day = st.selectbox("Selecione o dia", day_options, key=f"dia_select_{wid}")
                            chosen_date = option_to_date[chosen_day]
                            st.write(f"#### ➕ Adicionar Nova Atividade ({chosen_day})")

                            # Função para obter os servidores já alocados no dia (exceto Expediente)
                            def get_alocados_no_dia(chosen_date):
                                ds = chosen_date.strftime("%d/%m/%Y")
                                alocados = set()
                                if ds in st.session_state["atividades_dia"]:
                                    for act in st.session_state["atividades_dia"][ds]:
                                        if act["atividade"] != "Expediente Administrativo":
                                            for s in act["servidores"]:
                                                alocados.add(s)
                                return alocados

                            alocados_hoje = get_alocados_no_dia(chosen_date)
                            _, servers_summary, _ = get_summary_details_for_week(wid)

                            def format_server_name(server: str) -> str:
                                count = servers_summary.get(server, 0)
                                if server in alocados_hoje:
                                    return f"{server} (já alocado, {count})"
                                else:
                                    return f"{server} ({count})"

                            with st.form(key=f"form_nova_atividade_{wid}"):
                                atividade_escolhida = st.selectbox("Atividade", st.session_state["atividades"])
                                available_servers = st.session_state["servidores"]
                                servidores_escolhidos = st.multiselect(
                                    "Servidores (semana atual: contagem de alocações)",
                                    options=available_servers,
                                    default=[],
                                    format_func=format_server_name,
                                    placeholder="Selecione um ou mais servidores..."
                                )
                                veiculo_escolhido = st.selectbox("Veículo", st.session_state["veiculos"])
                                if st.form_submit_button("➕Adicionar Atividade"):
                                    ds = chosen_date.strftime("%d/%m/%Y")
                                    if ds in st.session_state["atividades_dia"]:
                                        for a_idx, act in enumerate(st.session_state["atividades_dia"][ds]):
                                            if act["atividade"] == "Expediente Administrativo":
                                                act["servidores"] = [s for s in act["servidores"] if s not in servidores_escolhidos]
                                                break
                                    add_activity_to_date(chosen_date, atividade_escolhida, servidores_escolhidos, veiculo_escolhido)
                                    st.rerun()

                        # with top_col3:
                        with top_col3:
                       # Resumo visual da semana
                            dias_com_atividades = []
                            for d in week_dates:
                                ds = d.strftime("%d/%m/%Y")
                                day_name_pt = dias_semana.get(d.strftime("%A"), d.strftime("%A"))
                                acts = st.session_state["atividades_dia"].get(ds, [])
                                if any(act["atividade"] != "Expediente Administrativo" for act in acts):
                                    dias_com_atividades.append(day_name_pt)
                            dias_label = "<br>".join(dias_com_atividades) if dias_com_atividades else "Nenhum"

                            activities_summary, servers_summary, vehicles_summary = get_summary_details_for_week(wid)

                            # CSS customizado do card
                            st.markdown(
                                """
                                <style>
                                .summary-card {
                                    border: 1px solid #ccc;
                                    padding: 10px;
                                    border-radius: 5px;
                                    margin-bottom: 10px;
                                    background: #f9f9f9;
                                }
                                .summary-flex {
                                    display: flex;
                                    flex-direction: row;
                                    justify-content: space-between;
                                }
                                .summary-column {
                                    flex: 1;
                                    padding: 5px;
                                    margin-right: 10px;
                                }
                                .summary-column:last-child {
                                    margin-right: 0;
                                }
                                </style>
                                """,
                                unsafe_allow_html=True
                            )

                            # Monta o HTML do card com 4 colunas
                            summary_html = f"""
                            <div class="summary-card">
                            <strong>📊 Resumo da Semana</strong>
                            <div class="summary-flex">
                                <div class="summary-column">
                                <u>📅 Dia:</u><br>{dias_label}
                                </div>
                                <div class="summary-column">
                                <u>🗂️ Atividades:</u><br>"""
                            if activities_summary:
                                for act, count in activities_summary.items():
                                    summary_html += f"{act}: {count}<br>"
                            else:
                                summary_html += "Nenhuma<br>"

                            summary_html += """</div>
                                <div class="summary-column">
                                <u>👥Servidores:</u><br>"""
                            if servers_summary:
                                for serv, count in servers_summary.items():
                                    primeiro_nome = serv.split()[0]
                                    summary_html += f"{primeiro_nome}: {count}<br>"
                            else:
                                summary_html += "Nenhum<br>"

                            summary_html += """</div>
                                <div class="summary-column">
                                <u>🚗Veículos:</u><br>"""
                            if vehicles_summary:
                                for veic, count in vehicles_summary.items():
                                    summary_html += f"{veic}: {count}<br>"
                            else:
                                summary_html += "Nenhum<br>"

                            summary_html += """</div>
                            </div>
                            </div>"""

                            # Exibe o card de resumo
                            st.markdown(summary_html, unsafe_allow_html=True)

                        st.markdown("---")

                        # =========== Listagem das atividades (um bloco por dia) ===========
                        cols = st.columns(len(week_dates))
                        for j, current_date in enumerate(week_dates):
                            with cols[j]:
                                ds = current_date.strftime("%d/%m/%Y")
                                day_name_en = current_date.strftime("%A")
                                day_name_pt = dias_semana.get(day_name_en, day_name_en)

                                # Exibe o título do dia
                                st.markdown(f"##### {day_name_pt} - {ds}")

                                day_acts = st.session_state["atividades_dia"].get(ds, [])
                                if day_acts:
                                    for act_idx, atividade in enumerate(day_acts):
                                        st.markdown(f"##### Atividade: {atividade['atividade']}")
                                        if atividade["atividade"] != "Expediente Administrativo":

                                            # [REFATORADO]
                                            activity_checked = st.checkbox(
                                                f"Marcar atividade: {atividade['atividade']}",
                                                value=is_checkbox_checked(ds, "atividade", act_idx),
                                                key=f"checkbox_atividade_{ds}_{act_idx}",
                                                on_change=set_checkbox_unchecked,
                                                args=(ds, "atividade", act_idx)
                                            )
                                            if not activity_checked:
                                                remove_activity_card(ds, act_idx)
                                                st.rerun()

                                            st.write("👥 Servidores: (❌ desmarque para remover da atividade e retornar para 🗂️ Expediente Administrativo)")

                                            for s in atividade["servidores"][:]:
                                                key_server = f"checkbox_servidor_{ds}_{act_idx}_{s}"

                                                # [REFATORADO]
                                                server_checked = st.checkbox(
                                                    s,
                                                    value=is_checkbox_checked(ds, "servidor", act_idx, s),
                                                    key=key_server,
                                                    on_change=set_checkbox_unchecked,
                                                    args=(ds, "servidor", act_idx, s)
                                                )
                                                if not server_checked:
                                                    remove_server_from_card(ds, act_idx, s)
                                                    st.rerun()
                                        else:
                                            st.write("👥 Servidores: (❌ desmarque para não incluir na 🖨️ impressão)")
                                            for s in atividade["servidores"]:
                                                key_server = f"checkbox_servidor_{ds}_{act_idx}_{s}"
                                                st.checkbox(
                                                    s,
                                                    value=True,
                                                    key=key_server,
                                                    help="Desmarque para não incluir este servidor na impressão."
                                                )

                                        st.write(f"**🚗 Veículo:** {atividade['veiculo']}")
                                        st.markdown("---")
                                else:
                                    st.write("📭 Nenhuma atividade para este dia.")

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
                                    labels[idx],
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
                                    labels[idx],
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
                                "Dia": f"--- {labels[w_index]} ---",
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

            # --- Indisponibilidades ---
            with st.expander("Indisponibilidades", expanded=False):
                render_indisponibilidades()

            st.divider()

            # --- Geração da Escala ---
            st.subheader("🗓️ Gerar Escala de Plantão (Sábado a Sexta)")
            render_cronograma_plantao()

    with tab4:
       
        # --- Supabase Config ---
       SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wlbvahpkcaksqkzdhnbv.supabase.co")
       SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndsYnZhaHBrY2Frc3FremRobmJ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDMyODMxMTUsImV4cCI6MjA1ODg1OTExNX0.Cph86UhT8Q67-1x2oVfTFyELgQqWRgJ3yump1JpHSc8")
       supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
       # Layout centralizado
       col_esq, col_meio, col_dir = st.columns([1, 3.5, 1])
        
       with col_meio:
            st.title("📅 Cadastro de Escala de Férias")

            ano_escala = st.number_input(
                "Ano da escala",
                value=dt.date.today().year,
                step=1,
                format="%d",
                key="ano_escala_input"
            )

            # --- Carregar servidores da unidade ---
            unidade_id = 3
            try:
                response = supabase.table("servidores").select("*").eq("escritorio_id", unidade_id).execute()
                servidores = [s["nome"] for s in response.data] if response.data else []
            except Exception as e:
                st.error(f"Erro ao carregar servidores: {e}")
                servidores = []

            if "intervalos" not in st.session_state:
                st.session_state.intervalos = []

            if servidores:
                servidor = st.selectbox("Selecione o servidor", servidores)
            else:
                st.warning("Nenhum servidor encontrado para o escritório.")
                servidor = None

            col_data1, col_data2 = st.columns(2)
            with col_data1:
                data_inicial = st.date_input("Data Inicial", value=dt.date.today())
            with col_data2:
                data_final = st.date_input("Data Final", value=dt.date.today())

            if st.button("➕ Adicionar Intervalo", key="add_intervalo"):
                if not servidor:
                    st.warning("Selecione um servidor.")
                elif data_final < data_inicial:
                    st.error("A data final não pode ser anterior à data inicial.")
                else:
                    st.session_state.intervalos.append({
                        "servidor": servidor,
                        "data_inicial": data_inicial,
                        "data_final": data_final
                    })
                    st.rerun()

            st.subheader("📋 Intervalos Inseridos")
            if st.session_state.intervalos:
                for i, item in enumerate(st.session_state.intervalos):
                    col_l, col_r = st.columns([6, 1])
                    with col_l:
                        st.markdown(f"**{i+1}. {item['servidor']}**: {item['data_inicial']} a {item['data_final']}")
                    with col_r:
                        if st.button("❌ Remover", key=f"remove_{i}"):
                            st.session_state.intervalos.pop(i)
                            st.rerun()
            else:
                st.info("Nenhum intervalo cadastrado.")

            st.markdown("---")
            if st.button("📥 Gerar Escala em PDF"):
                if st.session_state.intervalos:
                    caminho_pdf = "escala_de_ferias.pdf"
                    gerar_pdf_escala(
                        st.session_state.intervalos,
                        caminho_pdf,
                        ano_titulo=ano_escala
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


if __name__ == "__main__":
    main_app()
