import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

def generate_pdf_for_atividades(atividades_por_servidor, week_desc, ulsav_name, supervisao_name):
    """
    Gera o PDF do relatório de atividades por servidor, imprimindo uma página por servidor.
    Em cada página, o cabeçalho geral é repetido.
    - atividades_por_servidor: dicionário {servidor: [ { "Data":..., "Atividade":... }, ... ] }
    - Para cada servidor, gera um título e, para cada atividade, cria:
        * Tabela com Data, Atividade, Executada
        * 3 linhas sublinhadas para anotações (anteriormente 5)
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    elements = []
    styles = getSampleStyleSheet()
    style_heading = styles["Heading2"]
    style_subheading = styles["Heading3"]

    # Cabeçalho geral (será repetido em cada página)
    header_paragraph = Paragraph(
        f"<b>Relatório de Atividades</b><br/>{week_desc}<br/>"
        f"ULSAV: {ulsav_name} | Supervisão: {supervisao_name}",
        style_heading
    )

    servers = list(atividades_por_servidor.keys())
    for i, servidor in enumerate(servers):
        # Se não for a primeira página, insere PageBreak
        if i > 0:
            elements.append(PageBreak())
        # Adiciona o cabeçalho geral em cada página
        elements.append(header_paragraph)
        elements.append(Spacer(1, 12))
        
        # Título do funcionário
        servidor_paragraph = Paragraph(f"<b>{servidor}</b>", style_subheading)
        elements.append(servidor_paragraph)
        elements.append(Spacer(1, 8))

        atividades = atividades_por_servidor[servidor]
        for atividade in atividades:
            data = atividade.get("Data", "??/??/????")
            nome_atividade = atividade.get("Atividade", "")
            # Tabela da atividade: cabeçalho e linha de dados
            table_data = [
                ["Data", "Atividade | Observações", "Realizada"],
                [data, nome_atividade, "[   ] Sim   [   ] Não"]
            ]
            t = Table(table_data, colWidths=[80, 300, 100])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 12),
                ('BOTTOMPADDING', (0,0), (-1,0), 6),
                ('GRID', (0,0), (-1,-1), 0.25, colors.black),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 6))

            # 3 linhas em branco sublinhadas para anotações
            for _ in range(3):
                line_data = [[""]]
                line_table = Table(line_data, colWidths=[480])
                line_table.setStyle(TableStyle([
                    ('LINEBELOW', (0,0), (-1,0), 0.5, colors.lightgrey),
                    ('BOTTOMPADDING', (0,0), (-1,0), 8),
                ]))
                elements.append(line_table)

        elements.append(Spacer(1, 24))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
