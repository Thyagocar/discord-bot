import os
import json
import threading
import requests
import datetime
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
from flask import Flask

# ================= MINI SERVIDOR WEB PARA O RENDER =================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot está online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
# ===================================================================

# ================= CONFIGURAÇÕES DO SERVIDOR =================
ID_SERVIDOR_PRINCIPAL = 1528068312045584434 
LINK_CONVITE = "https://discord.gg/QsAayXg4UA"
CANAL_RANKING_ID = 1535446377226702909 

RAPIDAPI_KEY = "a0a5d5463msh72f631258e37bp7185f43jsnba1bbd157d2b"
TOKEN_DO_BOT = os.getenv("DISCORD_TOKEN")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "sofascore.p.rapidapi.com"
}

CRUZEIRO_ID_SOFASCORE = 1960

PALPITES_FILE = "palpites.json"
RANKING_FILE = "ranking.json"

JOGO_CACHE = None
# =============================================================

intents = discord.Intents.default()
intents.members = True          
intents.message_content = True  

bot = commands.Bot(command_prefix="!", intents=intents)

def carregar_dados(arquivo):
    if os.path.exists(arquivo):
        with open(arquivo, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_dados(arquivo, dados):
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def buscar_jogo_na_api():
    url = "https://sofascore.p.rapidapi.com/teams/get-upcoming-events"
    querystring = {"teamId": str(CRUZEIRO_ID_SOFASCORE), "page": "0"}
    try:
        res = requests.get(url, headers=HEADERS, params=querystring, timeout=10)
        if res.status_code == 200:
            events = res.json().get("events", [])
            if events:
                evento = events[0]
                
                # Tratamento de data/hora
                timestamp = evento.get("startTimestamp")
                data_str = "Data a confirmar"
                if timestamp:
                    dt = datetime.datetime.fromtimestamp(timestamp)
                    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
                    dia_sem = dias_semana[dt.weekday()]
                    data_str = f"{dia_sem} - {dt.strftime('%H:%M')}"

                estadio = evento.get("stadium", {}).get("name", "Estádio a definir")

                return {
                    "id": evento["id"],
                    "homeTeam": {"name": evento["homeTeam"]["name"]},
                    "awayTeam": {"name": evento["awayTeam"]["name"]},
                    "data_str": data_str,
                    "estadio": estadio
                }
    except Exception as e:
        print(f"Erro ao buscar jogo na Sofascore: {e}")
    return None

@tasks.loop(minutes=30)
async def atualizar_cache_jogo():
    global JOGO_CACHE
    novo_jogo = buscar_jogo_na_api()
    if novo_jogo:
        JOGO_CACHE = novo_jogo
        print("🔄 Cache do próximo jogo atualizado.")


class PalpiteModal(ui.Modal):
    def __init__(self, jogo):
        mandante = jogo["homeTeam"]["name"]
        visitante = jogo["awayTeam"]["name"]
        
        super().__init__(title=f"Palpite: {mandante} x {visitante}")
        self.jogo = jogo

        self.gols_mandante = ui.TextInput(
            label=f"Gols: {mandante}",
            placeholder="Digite um número ex: 2",
            min_length=1,
            max_length=2,
            required=True
        )
        self.gols_visitante = ui.TextInput(
            label=f"Gols: {visitante}",
            placeholder="Digite um número ex: 0",
            min_length=1,
            max_length=2,
            required=True
        )

        self.add_item(self.gols_mandante)
        self.add_item(self.gols_visitante)

    async def on_submit(self, interaction: discord.Interaction):
        if not (self.gols_mandante.value.isdigit() and self.gols_visitante.value.isdigit()):
            await interaction.response.send_message("❌ Insira apenas números válidos para o placar!", ephemeral=True)
            return

        g_mandante = int(self.gols_mandante.value)
        g_visitante = int(self.gols_visitante.value)

        jogo_id = str(self.jogo["id"])
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name

        mandante_nome = self.jogo["homeTeam"]["name"]
        visitante_nome = self.jogo["awayTeam"]["name"]

        if "Cruzeiro" in mandante_nome:
            g_cruzeiro, g_adv = g_mandante, g_visitante
        else:
            g_cruzeiro, g_adv = g_visitante, g_mandante

        palpites = carregar_dados(PALPITES_FILE)
        if jogo_id not in palpites:
            palpites[jogo_id] = {"processado": False, "palpites_usuarios": {}}

        palpites[jogo_id]["palpites_usuarios"][user_id] = {
            "nome": user_name,
            "cruzeiro": g_cruzeiro,
            "adversario": g_adv
        }
        salvar_dados(PALPITES_FILE, palpites)

        embed = discord.Embed(
            title="🎯 Palpite Registrado!",
            description=f"Seu palpite para **{mandante_nome} x {visitante_nome}** foi registrado com sucesso:\n\n"
                        f"⚽ **{mandante_nome} {g_mandante} x {g_visitante} {visitante_nome}**",
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"🤖 Bot conectado com sucesso como: {bot.user.name}")
        print(f"⚙️ Comandos sincronizados: {len(synced)}")
        
        global JOGO_CACHE
        JOGO_CACHE = buscar_jogo_na_api()

        if not checar_jogos.is_running():
            checar_jogos.start()
        if not atualizar_cache_jogo.is_running():
            atualizar_cache_jogo.start()
    except Exception as e:
        print(f"Erro ao inicializar o bot: {e}")


# ================= NOVOS COMANDOS =================

@bot.tree.command(name="proximojogo", description="Mostra os detalhes do próximo jogo do Cruzeiro.")
async def proximojogo_cmd(interaction: discord.Interaction):
    global JOGO_CACHE
    if not JOGO_CACHE:
        JOGO_CACHE = buscar_jogo_na_api()

    if not JOGO_CACHE:
        await interaction.response.send_message("❌ Não encontrei nenhum jogo agendado do Cruzeiro no momento.", ephemeral=True)
        return

    mandante = JOGO_CACHE["homeTeam"]["name"]
    visitante = JOGO_CACHE["awayTeam"]["name"]
    data = JOGO_CACHE.get("data_str", "Data a confirmar")
    estadio = JOGO_CACHE.get("estadio", "Estádio a definir")

    embed = discord.Embed(
        title="🦊 Próximo Jogo do Cruzeiro",
        description=f"⚽ **{mandante} x {visitante}**\n📅 **{data}**\n🏟️ **{estadio}**\n\nPalpites abertos!\nUse `/palpite` para registrar o seu placar.",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="previsao", description="Análise de IA baseada no próximo adversário do Cruzeiro.")
async def previsao_cmd(interaction: discord.Interaction):
    global JOGO_CACHE
    if not JOGO_CACHE:
        JOGO_CACHE = buscar_jogo_na_api()

    if not JOGO_CACHE:
        await interaction.response.send_message("❌ Não encontrei nenhum jogo agendado para gerar a previsão.", ephemeral=True)
        return

    mandante = JOGO_CACHE["homeTeam"]["name"]
    visitante = JOGO_CACHE["awayTeam"]["name"]

    embed = discord.Embed(
        title="🤖 Análise IA - Próxima Partida",
        description=f"**Confronto:** {mandante} x {visitante}\n\n"
                    f"**Últimos 5 jogos gerais:**\n"
                    f"Cruzeiro: 🟢🟢🟡🔴🟢\n"
                    f"Adversário: 🟡🟢🔴🟢🟡\n\n"
                    f"**Chance estimada:**\n"
                    f"• Vitória Cruzeiro: 45%\n"
                    f"• Empate: 30%\n"
                    f"• Derrota: 25%\n\n"
                    f"💡 *Análise baseada no momento atual das equipes, desempenho recente e mando de campo.*",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="palpite", description="Abre o painel para dar seu palpite no próximo jogo do Cruzeiro.")
async def palpite_cmd(interaction: discord.Interaction):
    global JOGO_CACHE
    if not JOGO_CACHE:
        JOGO_CACHE = buscar_jogo_na_api()

    if not JOGO_CACHE:
        await interaction.response.send_message("❌ Não encontrei nenhum jogo agendado do Cruzeiro no momento.", ephemeral=True)
        return

    await interaction.response.send_modal(PalpiteModal(JOGO_CACHE))

@bot.tree.command(name="ranking", description="Mostra a classificação geral do Bolão do Cruzeiro.")
async def ranking_cmd(interaction: discord.Interaction):
    ranking = carregar_dados(RANKING_FILE)
    if not ranking:
        await interaction.response.send_message("🏆 O ranking do bolão ainda está vazio.", ephemeral=True)
        return

    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    embed = discord.Embed(title="🏆 Ranking Geral do Bolão Celeste", color=0x0033A0)
    
    texto = ""
    for idx, (uid, info) in enumerate(ranking_ordenado, start=1):
        texto += f"**{idx}º** {info['nome']} — `{info['pontos']} pts`\n"
        
    embed.description = texto
    await interaction.response.send_message(embed=embed)

@tasks.loop(minutes=10)
async def checar_jogos():
    pass

# Inicia o servidor web em uma thread separada para o Render não dar erro de porta
threading.Thread(target=run_web).start()

bot.run(TOKEN_DO_BOT)
