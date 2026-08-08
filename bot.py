import os
import json
import threading
import discord
from discord import app_commands, ui
from discord.ext import commands
from flask import Flask

# ================= CONFIGURAÇÃO DO BOT =================
app = Flask(__name__)
@app.route('/')
def home(): return "Bot está online!"

def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

TOKEN_DO_BOT = os.getenv("DISCORD_TOKEN")
CONFIG_FILE = "config.json"
PALPITES_FILE = "palpites.json"
RANKING_FILE = "ranking.json"
JOGO_ATIVO_FILE = "jogo_ativo.json"

intents = discord.Intents.default()
intents.members = True          
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

def carregar_dados(arquivo):
    if os.path.exists(arquivo):
        with open(arquivo, "r", encoding="utf-8") as f: return json.load(f)
    return {} if "ranking" in arquivo or "config" in arquivo else {}

def salvar_dados(arquivo, dados):
    with open(arquivo, "w", encoding="utf-8") as f: json.dump(dados, f, indent=4, ensure_ascii=False)

# ================= NOVOS COMANDOS DE CONFIGURAÇÃO =================
@bot.tree.command(name="config-notificacao", description="[Admin] Define canal e cargo para notificações.")
@app.app_commands.describe(canal="Canal de avisos", cargo="Cargo a ser marcado (ex: @everyone)")
async def config_notif(interaction: discord.Interaction, canal: discord.TextChannel, cargo: discord.Role):
    if not interaction.user.guild_permissions.administrator: return await interaction.response.send_message("Acesso negado.", ephemeral=True)
    config = carregar_dados(CONFIG_FILE)
    config["canal_notif"] = str(canal.id)
    config["cargo_notif"] = str(cargo.id)
    salvar_dados(CONFIG_FILE, config)
    await interaction.response.send_message(f"✅ Notificações configuradas para {canal.mention} marcando {cargo.mention}.", ephemeral=True)

# ================= COMANDOS DO BOLÃO =================

@bot.tree.command(name="setarjogo", description="[Admin] Define jogo e avisa a torcida.")
async def setarjogo_cmd(interaction: discord.Interaction, mandante: str, visitante: str, horario: str, estadio: str):
    config = carregar_dados(CONFIG_FILE)
    jogo = {"mandante": mandante, "visitante": visitante, "horario": horario, "estadio": estadio, "aberto": True}
    salvar_dados(JOGO_ATIVO_FILE, jogo)
    salvar_dados(PALPITES_FILE, {})

    if "canal_notif" in config:
        canal = interaction.guild.get_channel(int(config["canal_notif"]))
        cargo = interaction.guild.get_role(int(config["cargo_notif"]))
        if canal:
            await canal.send(f"{cargo.mention} 📢 **Novo Jogo no Bolão!**\n**{mandante} x {visitante}**\nUse `/palpite` para apostar!")
    
    await interaction.response.send_message("Jogo configurado e aviso enviado!", ephemeral=True)

@bot.tree.command(name="fecharpalpites", description="[Admin] Encerra as apostas.")
async def fecharpalpites_cmd(interaction: discord.Interaction):
    jogo = carregar_dados(JOGO_ATIVO_FILE)
    jogo["aberto"] = False
    salvar_dados(JOGO_ATIVO_FILE, jogo)
    await interaction.response.send_message("🔒 Palpites encerrados para este jogo!", ephemeral=True)

@bot.tree.command(name="perfil", description="Ver suas estatísticas no bolão.")
async def perfil_cmd(interaction: discord.Interaction):
    ranking = carregar_dados(RANKING_FILE)
    user_id = str(interaction.user.id)
    if user_id not in ranking: return await interaction.response.send_message("Você ainda não tem palpites registrados.", ephemeral=True)
    
    u = ranking[user_id]
    await interaction.response.send_message(f"📊 **Perfil de {interaction.user.display_name}**\nPontos: {u['pontos']}\nPlacares exatos: {u.get('exatos', 0)}\nMarcadores cravados: {u.get('marcadores', 0)}", ephemeral=True)

# ================= LÓGICA DE ATUALIZAÇÃO DE RANKING =================
# (Adicione esta lógica dentro do seu placarfinal_cmd)
def atualizar_ranking(uid, nome, pontos, exato, marcou):
    ranking = carregar_dados(RANKING_FILE)
    if uid not in ranking: ranking[uid] = {"nome": nome, "pontos": 0, "exatos": 0, "marcadores": 0}
    ranking[uid]["pontos"] += pontos
    if exato: ranking[uid]["exatos"] += 1
    if marcou: ranking[uid]["marcadores"] += 1
    
    # Lógica de Cargo de Destaque
    try:
        guild = bot.guilds[0] # Simplificação, ideal usar o ID da guild
        lider_id = max(ranking, key=lambda x: ranking[x]['pontos'])
        # Aqui você adicionaria o código para dar cargo ao lider_id...
    except: pass
    salvar_dados(RANKING_FILE, ranking)

# ... (restante do código)

threading.Thread(target=run_web).start()
bot.run(TOKEN_DO_BOT)
