import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

def make_on_page_footer(plantao):
    """
    Cria uma função de rodapé que "captura" a variável plantao no escopo.
    Será chamada em todas as páginas (onPage).
    """
    def on_page_footer(canvas, doc):
        canvas.saveState()
        # Se tiver um nome de plantonista, exibimos o texto; caso contrário, deixamos vazio
        if plantao:
            footer_text = f"➤ Plantão para recebimento de vacinas, agrotóxicos e produtos biológicos: {plantao}"
        else:
            footer_text = ""
        
        # Ajuste de fonte e posição do rodapé
        canvas.setFont("Helvetica", 10)
        # Exemplo: desenhar 20 pontos acima da margem inferior
        x = doc.leftMargin
        y = doc.bottomMargin - 20
        canvas.drawString(x, y, footer_text)
        canvas.restoreState()
    return on_page_footer


class MyDocTemplate(BaseDocTemplate):
    """
    Documento customizado que permite usar PageTemplates e a função on_page_footer.
    """
    def __init__(self, filename, plantao=None, **kwargs):
        super().__init__(filename, **kwargs)
        
        # Cria um Frame ocupando a área de texto (excluindo margens).
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id='main_frame'
        )
        
        # Cria um PageTemplate que usa esse frame e chama a função de rodapé
        template = PageTemplate(
            id='main_template',
            frames=[frame],
            onPage=make_on_page_footer(plantao)  # Passamos plantao para a função
        )
        
        # Adiciona esse template à lista de templates
        self.addPageTemplates([template])


def generate_pdf_header(width, week_desc, ulsav_name, supervisao_name):
    """
    Cabeçalho do relatório em forma de Table.
    """
    header_data = [
        ["Programação de Atividades"],
        [f"ULSAV de {ulsav_name} | Supervisão de {supervisao_name}"],
        [week_desc]
    ]
    header_table = Table(header_data, colWidths=[width])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4c2930")),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#666666")),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor("#999999")),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 16),
        ('FONTSIZE', (0, 1), (-1, 1), 12),
        ('FONTSIZE', (0, 2), (-1, 2), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ]))
    return header_table


def generate_pdf_for_week(cards, week_desc, ulsav_name, supervisao_name, plantao=None):
    """
    Gera o PDF com:
      - Cabeçalho (exibido só no começo, mas poderia ser repetido com onPage se desejado).
      - Para cada dia, um bloco (KeepTogether) com título e tabelas de atividades.
      - Somente 3 colunas: [Atividade (nome + servidores), Veículo, Realizada].
      - Rodapé aparecendo em TODAS as páginas, usando a info de 'plantao'.
    """
    buffer = io.BytesIO()
    doc = MyDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        plantao=plantao
    )

    styles = getSampleStyleSheet()
    style_normal = styles["BodyText"]
    style_normal.fontName = "Helvetica"
    style_normal.fontSize = 8
    style_normal.leading = 12

    elements = []

    # 1) Cabeçalho (apenas na primeira página, pois é adicionado uma vez).
    header_table = generate_pdf_header(doc.width, week_desc, ulsav_name, supervisao_name)
    elements.append(header_table)
    elements.append(Spacer(1, 12))

    # 2) Conteúdo dos dias
    for idx, day_info in enumerate(cards):
        day_flowables = []

        # Título do dia (ex.: "Segunda-feira (03/03/2025)")
        dia_label = day_info["Dia"]
        title_data = [[dia_label]]
        title_table = Table(title_data, colWidths=[doc.width])
        title_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4c2930")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ]))
        day_flowables.append(title_table)
        day_flowables.append(Spacer(1, 6))

        # Atividades do dia
        day_activities = day_info["Activities"]
        for act in day_activities:
            atividade_nome = act["atividade"]
            servidores_str = ", ".join(s.split()[0] for s in act["servidores"]) if act["servidores"] else "Nenhum"
            realizada_str = "[   ] Sim   [   ] Não"

            # Cabeçalho de 3 colunas
            colunas = [atividade_nome, "Veículo", "Realizada"]

            # Uma linha de dados com servidores, veículo, etc.
            data_rows = [[
                Paragraph(servidores_str, style_normal),
                "" if act["veiculo"] == "Nenhum" else act["veiculo"],
                realizada_str
            ]]

            # Ajuste de larguras
            veiculo_col = 60
            realizada_col = 90
            atividade_col = doc.width - (veiculo_col + realizada_col)

            data_table = [colunas] + data_rows
            t = Table(
                data_table,
                colWidths=[atividade_col, veiculo_col, realizada_col],
                repeatRows=1  # repete o cabeçalho se quebrar a página
            )
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            day_flowables.append(t)
            day_flowables.append(Spacer(1, 4))

        # Agrupa o dia inteiro em um bloco KeepTogether
        elements.append(KeepTogether(day_flowables))
        elements.append(Spacer(1, 12))
    doc.title = week_desc or "Programação de Atividades"
    # Monta o PDF
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()
    return pdf