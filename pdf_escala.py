# from reportlab.pdfgen import canvas
# from reportlab.lib.pagesizes import A4, landscape
# import datetime
# import calendar
# from collections import defaultdict

# MESES_PT = {
#     1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
#     5: "maio", 6: "junho", 7: "julho", 8: "agosto",
#     9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
# }

# def agrupar_intervalos_por_mes(intervalos):
#     meses = defaultdict(list)
#     for item in intervalos:
#         inicio = item["data_inicial"]
#         fim = item["data_final"]
#         servidor = item["servidor"]
#         ano = inicio.year
#         mes = inicio.month

#         while (ano < fim.year) or (ano == fim.year and mes <= fim.month):
#             primeiro_dia = datetime.date(ano, mes, 1)
#             ultimo_dia = datetime.date(ano, mes, calendar.monthrange(ano, mes)[1])
#             efetivo_inicio = max(inicio, primeiro_dia)
#             efetivo_fim = min(fim, ultimo_dia)
#             meses[(ano, mes)].append({
#                 "servidor": servidor,
#                 "inicio": efetivo_inicio,
#                 "fim": efetivo_fim
#             })
#             if mes == 12:
#                 mes = 1
#                 ano += 1
#             else:
#                 mes += 1
#     return meses

# def gerar_pdf_escala(intervalos, caminho_arquivo, ano_titulo=2025):
#     meses = agrupar_intervalos_por_mes(intervalos)
#     c = canvas.Canvas(caminho_arquivo, pagesize=landscape(A4))
#     c.setTitle(f"Escala de Férias {ano_titulo}")

#     width, height = landscape(A4)
#     margem_esquerda = 80
#     margem_topo = 40
#     y_position = height - margem_topo

#     box_size = 15
#     espaco_entre = 4
#     altura_linha = box_size + 15  # altura que cada linha de servidor ocupa

#     def nova_pagina():
#         nonlocal y_position
#         c.showPage()
#         y_position = height - margem_topo
#         desenhar_titulo()

#     def desenhar_titulo():
#         c.setFont("Helvetica-Bold", 16)
#         c.drawCentredString(width / 2, height - 25, f"ESCALA DE FÉRIAS {ano_titulo}")

#     desenhar_titulo()

#     for (ano, mes), registros in sorted(meses.items()):
#         registros.sort(key=lambda r: r["servidor"])  # ordena servidores

#         if y_position - ((len(registros) + 1) * altura_linha) < 60:
#             nova_pagina()

#         # Salva posição superior para o quadro
#         y_topo_mes = y_position

#         # Título do mês
#         mes_nome = f"{MESES_PT[mes]} {ano}"
#         c.setFont("Helvetica-Bold", 12)
#         c.setFillGray(0)
#         c.drawCentredString(width / 2, y_position-7, mes_nome)
#         y_position -= 15

#         total_dias = calendar.monthrange(ano, mes)[1]

#         for registro in registros:
#             if y_position - altura_linha < 60:
#                 nova_pagina()
#                 y_topo_mes = y_position  # novo topo após quebra de página

#                 c.setFont("Helvetica-Bold", 12)
#                 c.drawString(margem_esquerda, y_position, mes_nome)
#                 y_position -= 15

#             servidor = registro["servidor"]
#             inicio = registro["inicio"]
#             fim = registro["fim"]

#             c.setFont("Helvetica", 9)
#             c.setFillGray(0)
#             c.drawString(30, y_position, servidor)

#             linha_y = y_position - box_size - 6

#             for dia in range(1, total_dias + 1):
#                 data_atual = datetime.date(ano, mes, dia)
#                 x = margem_esquerda + (dia - 1) * (box_size + espaco_entre)

#                 if inicio <= data_atual <= fim:
#                     c.setFillGray(0)
#                     c.rect(x, linha_y, box_size, box_size, fill=1)
#                     c.setFillGray(1)
#                 else:
#                     c.setFillGray(1)
#                     c.rect(x, linha_y, box_size, box_size, fill=1)
#                     c.setFillGray(0.3)

#                 c.setFont("Helvetica", 7)
#                 c.drawCentredString(x + box_size / 2, linha_y + 4, str(dia))

#             y_position -= altura_linha + 5

#         # Desenhar borda ao redor do mês
#         altura_mes = y_topo_mes - y_position + 10  # +10 para compensar margem extra
#         c.setStrokeGray(0.5)
#         c.setLineWidth(0.8)
#         c.rect(20, y_position, width - 40, altura_mes, stroke=1, fill=0)

#         y_position -= 10

#         # Legenda (opcional)
#         if y_position < 60:
#            nova_pagina()

#     c.setFont("Helvetica-Oblique", 8)
#     c.setFillGray(0)
#     c.drawString(30, y_position - 5, "Legenda: Dias em preto indicam o período de férias do servidor.")

#     c.save()
#     return caminho_arquivo
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
    margem_topo = 40
    y_position = height - margem_topo

    box_size = 15
    espaco_entre = 4
    altura_linha = box_size + 15

    def nova_pagina():
        nonlocal y_position
        c.showPage()
        y_position = height - margem_topo
        desenhar_titulo()

    def desenhar_titulo():
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2, height - 25, f"ESCALA DE FÉRIAS {ano_titulo}")

    desenhar_titulo()

    for (ano, mes), registros in sorted(meses.items()):
        registros.sort(key=lambda r: r["servidor"])

        if y_position - ((len(registros) + 1) * altura_linha) < 60:
            nova_pagina()

        y_topo_mes = y_position

        total_dias = calendar.monthrange(ano, mes)[1]
        largura_dias = total_dias * (box_size + espaco_entre)
        x_inicio = (width - largura_dias) / 2

        # Nome do mês centralizado
        mes_nome = f"{MESES_PT[mes]} {ano}"
        c.setFont("Helvetica-Bold", 12)
        c.setFillGray(0)
        c.drawCentredString(width / 2, y_position - 10, mes_nome)
        y_position -= 15

        for registro in registros:
            if y_position - altura_linha < 60:
                nova_pagina()
                y_topo_mes = y_position
                c.setFont("Helvetica-Bold", 12)
                c.drawCentredString(width /2, y_position, mes_nome)
                y_position -= 25

            servidor = registro["servidor"]
            inicio = registro["inicio"]
            fim = registro["fim"]

            c.setFont("Helvetica", 9)
            c.setFillGray(0)
     
            c.drawString(x_inicio, y_position, servidor)
            linha_y = y_position - box_size - 6

            for dia in range(1, total_dias + 1):
                data_atual = datetime.date(ano, mes, dia)
                x = x_inicio + (dia - 1) * (box_size + espaco_entre)

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

            y_position -= altura_linha + 5

        # Desenhar borda ao redor do mês
        altura_mes = y_topo_mes - y_position + 10
        c.setStrokeGray(0.5)
        c.setLineWidth(0.8)
        c.rect(30, y_position, width - 60, altura_mes, stroke=1, fill=0)
        y_position -= 10

    # Legenda no rodapé
    if y_position < 60:
        nova_pagina()

    c.setFont("Helvetica-Oblique", 8)
    c.setFillGray(0)
    c.drawString(30, y_position - 5, "Legenda: Dias em preto indicam o período de férias do servidor.")

    c.save()
    return caminho_arquivo
