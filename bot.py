import os
import json
import requests
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

# ================= CONFIGURAÇÕES DO SERVIDOR =================
ID_SERVIDOR_PRINCIPAL = 1528068312045584434 
LINK_CONVITE = "https://discord.gg/QsAayXg4UA"
CANAL_RANKING_ID = 1535446377226702909 

# Configurações da Sofascore (RapidAPI)
RAPIDAPI_KEY = "a0a5d5463msh72f631258e37bp7185f43jsnba1bbd157d2b"
TOKEN_DO_BOT = os.getenv("DISCORD_TOKEN")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "sofascore.p.rapidapi.com"
}

# ID do Cruzeiro na Sofascore (1960 é o ID oficial do Cruzeiro na Sofascore)
CRUZEIRO_ID_SOFASCORE = 1960

# Arquivos locais
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
    # Endpoint da Sofascore para pegar as próximas partidas (events) de um time
    url = f"https://sofascore.p.rapidapi.com/teams/get-upcoming-events"
    querystring = {"teamId": str(CRUZEIRO_ID_SOFASCORE), "page": "0"}
    
    try:
        res = requests.get(url, headers=HEADERS, params=querystring)
        if res.status_code == 200:
            events = res.json().get("events", [])
            if events:
                evento = events[0]
                return {
                    "id": evento["id"],
                    "homeTeam": {"name": evento["homeTeam"]["name"]},
                    "awayTeam": {"name": evento["awayTeam"]["name"]}
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
        print("🔄 Cache do próximo jogo atualizado (Sofascore).")


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

        # Descobre quem é o Cruzeiro pelo nome na partida
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
        print(f"⚙️ Comandos de barra (/) sincronizados: {len(synced)}")
        
        global JOGO_CACHE
        JOGO_CACHE = buscar_jogo_na_api()

        if not checar_jogos.is_running():
            checar_jogos.start()
        if not atualizar_cache_jogo.is_running():
            atualizar_cache_jogo.start()
    except Exception as e:
        print(f"Erro ao inicializar o bot: {e}")

@bot.event
async def on_member_join(member):
    if member.guild.id == ID_SERVIDOR_PRINCIPAL:
        return

    servidor_principal = bot.get_guild(ID_SERVIDOR_PRINCIPAL)
    if servidor_principal:
        membro_no_principal = servidor_principal.get_member(member.id)
        if not membro_no_principal:
            embed = discord.Embed(
                title="❌ Acesso Negado ao Servidor Secundário",
                description=(
                    f"Olá, {member.mention}!\n\n"
                    f"Você foi removido do servidor **{member.guild.name}** porque ele é exclusivo para membros do nosso servidor principal.\n\n"
                    f"👉 **Para liberar o seu acesso, entre no servidor principal primeiro:**\n"
                    f"{LINK_CONVITE}\n\n"
                    f"Após entrar no servidor principal, você poderá entrar no servidor secundário normalmente! 🔵⚪"
                ),
                color=0x0033A0
            )
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                pass
            try:
                await member.kick(reason="Não está no servidor principal.")
            except discord.Forbidden:
                pass


@bot.tree.command(name="palpite", description="Abre o painel para dar seu palpite no próximo jogo do Cruzeiro.")
async def palpite_cmd(interaction: discord.Interaction):
    global JOGO_CACHE
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
    palpites = carregar_dados(PALPITES_FILE)
    if not palpites:
        return

    for jogo_id, dados_jogo in list(palpites.items()):
        if dados_jogo.get("processado"):
            continue

        url = f"https://sofascore.p.rapidapi.com/events/get-details"
        querystring = {"eventId": str(jogo_id)}
        
        try:
            res = requests.get(url, headers=HEADERS, params=querystring)
            if res.status_code != 200:
                continue

            event_data = res.json().get("event", {})
            status_type = event_data.get("status", {}).get("type")
            
            if status_type == "finished":
                home_score = event_data.get("homeScore", {}).get("current", 0)
                away_score = event_data.get("awayScore", {}).get("current", 0)

                mandante_nome = event_data["homeTeam"]["name"]
                visitante_nome = event_data["awayTeam"]["name"]

                if "Cruzeiro" in mandante_nome:
                    gols_cru_real, gols_adv_real = home_score, away_score
                else:
                    gols_cru_real, gols_adv_real = away_score, home_score

                placar_texto = f"{mandante_nome} {home_score} x {away_score} {visitante_nome}"
                ranking = carregar_dados(RANKING_FILE)
                ganhadores = []

                for uid, p in dados_jogo["palpites_usuarios"].items():
                    if p["cruzeiro"] == gols_cru_real and p["adversario"] == gols_adv_real:
                        if uid not in ranking:
                            ranking[uid] = {"nome": p["nome"], "pontos": 0}
                        ranking[uid]["pontos"] += 1
                        ranking[uid]["nome"] = p["nome"]
                        ganhadores.append(p["nome"])

                palpites[jogo_id]["processado"] = True
                salvar_dados(PALPITES_FILE, palpites)
                salvar_dados(RANKING_FILE, ranking)

                canal = bot.get_channel(CANAL_RANKING_ID)
                if canal:
                    embed = discord.Embed(
                        title="🏁 Fim de Jogo! Resultados do Bolão",
                        description=f"**Placar Final:** {placar_texto}\n\n",
                        color=0x0033A0
                    )
                    
                    if ganhadores:
                        embed.description += "🎉 **Acertaram o placar exato (+1 ponto):**\n" + "\n".join([f"• {g}" for g in ganhadores])
                    else:
                        embed.description += "❌ Ninguém acertou o placar exato desta partida."

                    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
                    texto_rank = ""
                    for idx, (uid, info) in enumerate(ranking_ordenado[:10], start=1):
                        texto_rank += f"**{idx}º** {info['nome']} — `{info['pontos']} pts`\n"
                    
                    embed.add_field(name="🏆 Ranking Atualizado", value=texto_rank or "Sem pontuações", inline=False)
                    await canal.send(embed=embed)

        except Exception as e:
            print(f"Erro ao checar resultado na Sofascore: {e}")

bot.run(TOKEN_DO_BOT)
