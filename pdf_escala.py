from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
import datetime
import calendar
from collections import defaultdict

MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
}

def agrupar_intervalos_por_mes(intervalos):
    meses = defaultdict(list)
    for item in intervalos:
        inicio = item["data_inicial"]
        fim = item["data_final"]
        servidor = item["servidor"]
        ano = inicio.year
        mes = inicio.month

        while (ano < fim.year) or (ano == fim.year and mes <= fim.month):
            primeiro_dia = datetime.date(ano, mes, 1)
            ultimo_dia = datetime.date(ano, mes, calendar.monthrange(ano, mes)[1])
            efetivo_inicio = max(inicio, primeiro_dia)
            efetivo_fim = min(fim, ultimo_dia)
            meses[(ano, mes)].append({
                "servidor": servidor,
                "inicio": efetivo_inicio,
                "fim": efetivo_fim
            })
            if mes == 12:
                mes = 1
                ano += 1
            else:
                mes += 1
    return meses

def gerar_pdf_escala(intervalos, caminho_arquivo, ano_titulo=2025):
    meses = agrupar_intervalos_por_mes(intervalos)
    c = canvas.Canvas(caminho_arquivo, pagesize=landscape(A4))
    c.setTitle(f"Escala de Férias {ano_titulo}")

    width, height = landscape(A4)
    margem_esquerda = 120
    y_position = height - 40

    box_size = 15
    espaco_entre = 4
    altura_linha = box_size + 15  # altura que cada linha de servidor ocupa

    def nova_pagina():
        nonlocal y_position
        c.showPage()
        y_position = height - 40
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2, height - 25, f"ESCALA DE FÉRIAS {ano_titulo}")
        y_position -= 20

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 25, f"ESCALA DE FÉRIAS {ano_titulo}")

    for (ano, mes), registros in sorted(meses.items()):
        # Verifica se cabe o título do mês + pelo menos uma linha
        if y_position - (altura_linha * (len(registros) + 1)) < 60:
            nova_pagina()

        mes_nome = f"{MESES_PT[mes]} {ano}"
        c.setFont("Helvetica-Bold", 12)
        c.setFillGray(0)
        c.drawString(margem_esquerda, y_position, mes_nome)
        y_position -= 15

        for registro in registros:
            if y_position - altura_linha < 60:
                nova_pagina()

            servidor = registro["servidor"]
            inicio = registro["inicio"]
            fim = registro["fim"]

            c.setFont("Helvetica", 9)
            c.drawString(margem_esquerda, y_position, servidor)

            linha_y = y_position - box_size - 6
            total_dias = calendar.monthrange(ano, mes)[1]

            for dia in range(1, total_dias + 1):
                data_atual = datetime.date(ano, mes, dia)
                x = margem_esquerda + (dia - 1) * (box_size + espaco_entre)

                if inicio <= data_atual <= fim:
                    c.setFillGray(0)
                    c.rect(x, linha_y, box_size, box_size, fill=1)
                    c.setFillGray(1)
                else:
                    c.setFillGray(1)
                    c.rect(x, linha_y, box_size, box_size, fill=1)
                    c.setFillGray(0.3)

                c.setFont("Helvetica", 7)
                c.drawCentredString(x + box_size / 2, linha_y + 4, str(dia))

            y_position -= altura_linha

        # Linha separadora entre meses
        c.setStrokeGray(0.8)
        c.setLineWidth(0.5)
        c.line(margem_esquerda, y_position, width - margem_esquerda, y_position)
        y_position -= 10

    c.save()
    return caminho_arquivo