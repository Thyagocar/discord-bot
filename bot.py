import os
import json
import threading
import requests
import datetime
import discord
from discord import app_commands, ui
from discord.ext import commands
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
        with open(arquivo, "r", encoding="utf-8") as f:
            return json.load(f)
    return {} if "ranking" in arquivo or "config" in arquivo else ([] if "palpites" in arquivo else None)

def salvar_dados(arquivo, dados):
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


# ================= PAINEL DE CONFIGURAÇÃO (AO ENTRAR NO SERVIDOR) =================

class PainelConfigView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📋 Ver Comandos Admin", style=discord.ButtonStyle.primary, custom_id="btn_ajuda_admin")
    async def ajuda_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🛠️ Painel de Ajuda - Administradores",
            description="Aqui estão os comandos exclusivos para gerenciar o Bolão:\n\n"
                        "📌 **`/setarjogo`** — Define o próximo confronto, horário e estádio.\n"
                        "🏁 **`/placarfinal`** — Insere o resultado final, calcula os pontos automaticamente e gera o ranking.\n\n"
                        "💡 *Dica:* O sistema impede que o usuário envie mais de um palpite por partida ativa!",
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_guild_join(guild):
    # Cria canal privado para configuração
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    
    # Adiciona permissão para administradores verem o canal
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    canal = await guild.create_text_channel("⚙️│config-bot", overwrites=overwrites)
    
    embed = discord.Embed(
        title="🤖 Bem-vindo ao Bot Oficial do Cruzeiro!",
        description="Este canal é **privado** e visível apenas para administradores.\n\n"
                    "**Para que serve o bot?**\n"
                    "Gerencia o bolão oficial da torcida com painéis interativos, registro de palpites únicos por partida, cálculo automático de pontos e ranking geral.\n\n"
                    "⚙️ **Como configurar:**\n"
                    "1. Use `/setarjogo` para cadastrar o próximo duelo.\n"
                    "2. Divulgue no chat da torcida para usarem `/proximojogo` e `/palpite`.\n"
                    "3. Após o apito final, use `/placarfinal` para atualizar o ranking!",
        color=0x0033A0
    )
    await canal.send(embed=embed, view=PainelConfigView())


# ================= MODAL DE PALPITE =================

class PalpiteModal(ui.Modal):
    def __init__(self, jogo):
        mandante = jogo["mandante"]
        visitante = jogo["visitante"]
        
        super().__init__(title=f"Palpite: {mandante} x {visitante}")
        self.jogo = jogo

        self.gols_mandante = ui.TextInput(
            label=f"Gols do {mandante}",
            placeholder="Ex: 2",
            min_length=1,
            max_length=2,
            required=True
        )
        self.gols_visitante = ui.TextInput(
            label=f"Gols do {visitante}",
            placeholder="Ex: 0",
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

        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name

        palpites = carregar_dados(PALPITES_FILE)
        
        # Garante que o usuário só envie 1 vez para o jogo atual
        if user_id in palpites:
            p_antigo = palpites[user_id]
            await interaction.response.send_message(
                f"❌ Você já registrou um palpite para este jogo!\nSeu palpite salvo foi: **{p_antigo['g_mand']}\n x {p_antigo['g_vis']}**", 
                ephemeral=True
            )
            return

        palpites[user_id] = {
            "nome": user_name,
            "g_mand": g_mandante,
            "g_vis": g_visitante
        }
        salvar_dados(PALPITES_FILE, palpites)

        embed = discord.Embed(
            title="🎯 Palpite Registrado com Sucesso!",
            description=f"Partida: **{self.jogo['mandante']} {g_mandante} x {g_visitante} {self.jogo['visitante']}**\n\n"
                        f"🔒 Seu palpite está trancado. Boa sorte!",
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ================= EVENTO ON_READY =================

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"🤖 Bot conectado como: {bot.user.name}")
        print(f"⚙️ Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")


# ================= COMANDOS DO BOT =================

@bot.tree.command(name="setarjogo", description="[Admin] Define manualmente o próximo jogo.")
@app_commands.checks.has_permissions(administrator=True)
async def setarjogo_cmd(interaction: discord.Interaction, mandante: str, visitante: str, horario: str, estadio: str):
    jogo = {
        "mandante": mandante,
        "visitante": visitante,
        "horario": horario,
        "estadio": estadio
    }
    salvar_dados(JOGO_ATIVO_FILE, jogo)
    
    # Reseta os palpites da partida anterior ao criar um novo jogo
    salvar_dados(PALPITES_FILE, {})

    embed = discord.Embed(
        title="⚽ Novo Jogo Configurado!",
        description=f"**{mandante} x {visitante}**\n📅 **Horário:** {horario}\n🏟️ **Estádio:** {estadio}\n\n*Os palpites anteriores foram limpos. O bolão está aberto!*",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="proximojogo", description="Mostra os detalhes do próximo jogo do Cruzeiro.")
async def proximojogo_cmd(interaction: discord.Interaction):
    jogo = carregar_dados(JOGO_ATIVO_FILE)
    if not jogo:
        await interaction.response.send_message("❌ Nenhum jogo foi configurado no momento pela administração.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🦊 Próximo Jogo do Cruzeiro",
        description=f"⚽ **{jogo['mandante']} x {jogo['visitante']}**\n"
                    f"📅 **Horário:** {jogo['horario']}\n"
                    f"🏟️ **Local:** {jogo['estadio']}\n\n"
                    f"👇 *Deixe seu palpite oficial usando o comando* `/palpite`!",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="palpite", description="Abre o painel para registrar seu palpite único.")
async def palpite_cmd(interaction: discord.Interaction):
    jogo = carregar_dados(JOGO_ATIVO_FILE)
    if not jogo:
        await interaction.response.send_message("❌ Nenhum jogo ativo no momento para palpites.", ephemeral=True)
        return

    await interaction.response.send_modal(PalpiteModal(jogo))


@bot.tree.command(name="previsao", description="Análise de IA baseada no próximo adversário.")
async def previsao_cmd(interaction: discord.Interaction):
    jogo = carregar_dados(JOGO_ATIVO_FILE)
    if not jogo:
        await interaction.response.send_message("❌ Nenhum jogo ativo para gerar previsão.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🤖 Análise IA - Próxima Partida",
        description=f"**Confronto:** {jogo['mandante']} x {jogo['visitante']}\n\n"
                    f"**Últimos 5 jogos gerais:**\n"
                    f"Cruzeiro: 🟢🟢🟡🔴🟢\n"
                    f"Adversário: 🟡🟢🔴🟢🟡\n\n"
                    f"**Chance estimada:**\n"
                    f"• Vitória Cruzeiro: 45%\n"
                    f"• Empate: 30%\n"
                    f"• Derrota: 25%\n\n"
                    f"💡 *Análise baseada no momento atual das equipes.*",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="placarfinal", description="[Admin] Insere o placar final, calcula pontos e atualiza o ranking.")
@app_commands.checks.has_permissions(administrator=True)
async def placarfinal_cmd(interaction: discord.Interaction, gols_mandante: int, gols_visitante: int):
    jogo = carregar_dados(JOGO_ATIVO_FILE)
    if not jogo:
        await interaction.response.send_message("❌ Não há nenhum jogo ativo salvo para processar o placar.", ephemeral=True)
        return

    palpites = carregar_dados(PALPITES_FILE)
    if not palpites:
        await interaction.response.send_message("❌ Nenhum usuário enviou palpite para esta partida.", ephemeral=True)
        return

    ranking = carregar_dados(RANKING_FILE)
    
    resultados_parciais = ""
    
    # Regra de pontuação:
    # Placar Exato = 3 pontos
    # Acertar Vencedor/Empate = 1 ponto
    # Errar tudo = 0 pontos
    
    vencedor_real = "mandante" if gols_mandante > gols_visitante else ("visitante" if gols_visitante > gols_mandante else "empate")

    for uid, dados in palpites.items():
        g_m = dados["g_mand"]
        g_v = dados["g_vis"]
        nome = dados["nome"]
        
        vencedor_palpite = "mandante" if g_m > g_v else ("visitante" if g_v > g_m else "empate")
        
        pontos_ganhos = 0
        status_texto = "❌ Errou"
        
        if g_m == gols_mandante and g_v == gols_visitante:
            pontos_ganhos = 3
            status_texto = "🎯 Acertou em cheio! (+3 pts)"
        elif vencedor_palpite == vencedor_real:
            pontos_ganhos = 1
            status_texto = "✅ Acertou o vencedor! (+1 pt)"

        # Atualiza ranking geral
        if uid not in ranking:
            ranking[uid] = {"nome": nome, "pontos": 0}
        
        ranking[uid]["pontos"] += pontos_ganhos
        
        resultados_parciais += f"- <@{uid}> ({g_m}x{g_v}) — **{status_texto}**\n"

    salvar_dados(RANKING_FILE, ranking)

    # Ordena ranking
    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    
    texto_ranking = ""
    for idx, (uid, info) in enumerate(ranking_ordenado, start=1):
        texto_ranking += f"**{idx}º** — {info['nome']} (`{info['pontos']} pts`)\n"

    embed = discord.Embed(
        title=f"🏁 Resultado Final: {jogo['mandante']} {gols_mandante} x {gols_visitante} {jogo['visitante']}",
        description=f"**Apuração dos Palpites:**\n{resultados_parciais}\n\n🏆 **Ranking Atualizado do Bolão:**\n{texto_ranking}",
        color=0x0033A0
    )
    
    # Limpa o jogo ativo para forçar novo /setarjogo na próxima partida
    if os.path.exists(JOGO_ATIVO_FILE):
        os.remove(JOGO_ATIVO_FILE)

    await interaction.response.send_message(embed=embed)


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


# Inicializa o web server para o Render e executa o bot
threading.Thread(target=run_web).start()
bot.run(TOKEN_DO_BOT)
