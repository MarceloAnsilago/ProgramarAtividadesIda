from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A4
from supabase import create_client, Client
import os
import io

# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wlbvahpkcaksqkzdhnbv.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndsYnZhaHBrY2Frc3FremRobmJ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDMyODMxMTUsImV4cCI6MjA1ODg1OTExNX0.Cph86UhT8Q67-1x2oVfTFyELgQqWRgJ3yump1JpHSc8")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def generate_pdf_for_atividades(atividades_por_servidor, week_desc, ulsav_name, supervisao_name):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    elements = []
    styles = getSampleStyleSheet()
    style_heading = styles["Heading2"]
    style_normal = styles["Normal"]

    # Cabeçalho comum
    header_paragraph = Paragraph(
        f"<b>Diário de Atividades</b><br/>{week_desc}<br/>"
        f"ULSAV: {ulsav_name} | Supervisão: {supervisao_name}",
        style_heading
    )

    # Consulta os dados de todos os servidores uma vez
    servidores_data = supabase.table("servidores").select("*").execute().data or []
    dados_servidores = {s["nome"]: s for s in servidores_data}

    for i, nome_servidor in enumerate(atividades_por_servidor.keys()):
        if i > 0:
            elements.append(PageBreak())

        elements.append(header_paragraph)
        elements.append(Spacer(1, 12))

        servidor_info = dados_servidores.get(nome_servidor)

        if servidor_info:
            dados = (
                f"<b>Nome:</b> {servidor_info['nome']}<br/>"
                f"<b>Matrícula:</b> {servidor_info['matricula']}<br/>"
                f"<b>Cargo:</b> {servidor_info['cargo']}"
            )
        else:
            dados = f"<b>Nome:</b> {nome_servidor} (dados não encontrados)"

        elements.append(Paragraph(dados, style_normal))
        elements.append(Spacer(1, 8))

        atividades = atividades_por_servidor[nome_servidor]
        for atividade in atividades:
            data = atividade.get("Data", "??/??/????")
            nome_atividade = atividade.get("Atividade", "")

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

            for _ in range(3):
                line_table = Table([[""]], colWidths=[480])
                line_table.setStyle(TableStyle([
                    ('LINEBELOW', (0,0), (-1,0), 0.5, colors.lightgrey),
                    ('BOTTOMPADDING', (0,0), (-1,0), 8),
                ]))
                elements.append(line_table)

        # ➕ Adiciona espaço e linha de assinatura no final
        elements.append(Spacer(1, 36))
        elements.append(Paragraph(
            "<i>Assinatura do Servidor: ____________________________________________</i>",
            style_normal
        ))
        elements.append(Spacer(1, 24))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
