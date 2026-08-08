import os
import json
import threading
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


# ================= FUNÇÃO DE VERIFICAÇÃO DE PERMISSÃO =================
def verificar_permissao_adm(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    
    config = carregar_dados(CONFIG_FILE)
    cargos_permitidos = config.get("cargos_adm", [])
    
    for role in interaction.user.roles:
        if str(role.id) in cargos_permitidos:
            return True
            
    return False


# ================= MODAL DE CONFIGURAÇÃO MANUAL =================

class ConfigModal(ui.Modal, title="⚙️ Configuração Geral do Bot"):
    cargos_adm = ui.TextInput(
        label="ID ou Nome exato do Cargo Admin",
        placeholder="Ex: @Moderador ou ID numérico",
        required=True,
        max_length=100
    )
    canal_comandos = ui.TextInput(
        label="Nome exato do Canal de Palpites",
        placeholder="Ex: comandos-bots",
        required=True,
        max_length=100
    )
    canal_ranking = ui.TextInput(
        label="Nome exato do Canal de Ranking",
        placeholder="Ex: ranking",
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas administradores podem configurar o bot.", ephemeral=True)
            return

        guild = interaction.guild
        
        cargo_input = self.cargos_adm.value.strip()
        cargo_id = None
        for role in guild.roles:
            if cargo_input.lower() in role.name.lower() or cargo_input == str(role.id):
                cargo_id = str(role.id)
                break

        cmd_input = self.canal_comandos.value.strip().replace("#", "")
        canal_cmd_id = None
        for channel in guild.text_channels:
            if cmd_input.lower() in channel.name.lower() or cmd_input == str(channel.id):
                canal_cmd_id = str(channel.id)
                break

        rank_input = self.canal_ranking.value.strip().replace("#", "")
        canal_rank_id = None
        for channel in guild.text_channels:
            if rank_input.lower() in channel.name.lower() or rank_input == str(channel.id):
                canal_rank_id = str(channel.id)
                break

        config = carregar_dados(CONFIG_FILE)
        if cargo_id:
            config["cargos_adm"] = [cargo_id]
        if canal_cmd_id:
            config["canal_comandos"] = canal_cmd_id
        if canal_rank_id:
            config["canal_ranking"] = canal_rank_id

        salvar_dados(CONFIG_FILE, config)

        await interaction.response.send_message(
            f"✅ Configurações salvas com sucesso!\n"
            f"• **Cargo Admin ID:** {cargo_id or 'Não encontrado'}\n"
            f"• **Canal de Palpites:** <#{canal_cmd_id}>" if canal_cmd_id else "✅ Configurado!",
            ephemeral=True
        )


class PainelConfigView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="⚙️ Configurar Servidor", style=discord.ButtonStyle.success, custom_id="btn_abrir_config")
    async def abrir_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfigModal())

    @ui.button(label="📋 Comandos Admin & Ajuda", style=discord.ButtonStyle.primary, custom_id="btn_ajuda_admin")
    async def ajuda_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🛠️ Painel de Ajuda - Administradores",
            description="Aqui estão os comandos exclusivos para gerenciar o Bolão:\n\n"
                        "📌 **`/setarjogo`** — Define o próximo confronto, horário e estádio.\n"
                        "🏁 **`/placarfinal`** — Insere o resultado, artilheiros reais, calcula pontos e gera o ranking.\n\n"
                        "💡 *Dica:* Clique no botão verde **Configurar Servidor** para definir canais e cargos!",
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_guild_join(guild):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    canal = await guild.create_text_channel("⚙️│config-bot", overwrites=overwrites)
    
    embed = discord.Embed(
        title="🤖 Painel de Configuração do Bolão - Cruzeiro",
        description="Este canal é **privado** e visível apenas para administradores.\n\n"
                    "Clique no botão abaixo para abrir o painel de configuração e digitar os nomes dos canais e cargos desejados.",
        color=0x0033A0
    )
    
    await canal.send(embed=embed, view=PainelConfigView())


# ================= MODAL DE PALPITE (COM GOLS E ARTILHEIROS) =================

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
            placeholder="Ex: 1",
            min_length=1,
            max_length=2,
            required=True
        )
        self.artilheiros = ui.TextInput(
            label="Quem fará os gols? (Opcional)",
            placeholder="Ex: Kaio Jorge, Dinenno",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=200
        )

        self.add_item(self.gols_mandante)
        self.add_item(self.gols_visitante)
        self.add_item(self.artilheiros)

    async def on_submit(self, interaction: discord.Interaction):
        if not (self.gols_mandante.value.isdigit() and self.gols_visitante.value.isdigit()):
            await interaction.response.send_message("❌ Insira apenas números válidos para o placar!", ephemeral=True)
            return

        g_mandante = int(self.gols_mandante.value)
        g_visitante = int(self.gols_visitante.value)
        autores = self.artilheiros.value.strip() or "Nenhum citado"

        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name

        palpites = carregar_dados(PALPITES_FILE)
        
        if user_id in palpites:
            p_antigo = palpites[user_id]
            await interaction.response.send_message(
                f"❌ Você já enviou seu palpite para este jogo e ele está trancado!\n"
                f"Seu palpite salvo: **{self.jogo['mandante']} {p_antigo['g_mand']} x {p_antigo['g_vis']} {self.jogo['visitante']}**\n"
                f"⚽ Artilheiros: *{p_antigo['artilheiros']}*", 
                ephemeral=True
            )
            return

        palpites[user_id] = {
            "nome": user_name,
            "g_mand": g_mandante,
            "g_vis": g_visitante,
            "artilheiros": autores
        }
        salvar_dados(PALPITES_FILE, palpites)

        embed = discord.Embed(
            title="🎯 Palpite Registrado com Sucesso!",
            description=f"Partida: **{self.jogo['mandante']} {g_mandante} x {g_visitante} {self.jogo['visitante']}**\n"
                        f"⚽ Artilheiros Palpitados: *{autores}*\n\n"
                        f"🔒 Salvo com sucesso! Você só poderá enviar novo palpite após o adm setar outra partida.",
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
@app_commands.describe(mandante="Nome do time mandante", visitante="Nome do time visitante", horario="Data e horário do jogo", estadio="Local da partida")
async def setarjogo_cmd(interaction: discord.Interaction, mandante: str, visitante: str, horario: str, estadio: str):
    if not verificar_permissao_adm(interaction):
        await interaction.response.send_message("❌ Você não tem permissão para usar este comando administrativo.", ephemeral=True)
        return

    jogo = {
        "mandante": mandante,
        "visitante": visitante,
        "horario": horario,
        "estadio": estadio
    }
    salvar_dados(JOGO_ATIVO_FILE, jogo)
    salvar_dados(PALPITES_FILE, {}) 

    embed = discord.Embed(
        title="⚽ Novo Jogo Configurado!",
        description=f"**{mandante} x {visitante}**\n📅 **Data / Horário:** {horario}\n🏟️ **Estádio:** {estadio}\n\n*Os palpites anteriores foram limpos. O bolão está aberto!*",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="proximojogo", description="Mostra os detalhes do próximo jogo do Cruzeiro.")
async def proximojogo_cmd(interaction: discord.Interaction):
    config = carregar_dados(CONFIG_FILE)
    canal_permitido = config.get("canal_comandos")
    
    if canal_permitido and str(interaction.channel_id) != canal_permitido:
        await interaction.response.send_message(f"❌ Os comandos do bolão devem ser usados no canal <#{canal_permitido}>.", ephemeral=True)
        return

    jogo = carregar_dados(JOGO_ATIVO_FILE)
    if not jogo:
        await interaction.response.send_message("❌ Nenhum jogo foi configurado no momento pela administração.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🦊 Próximo Jogo do Cruzeiro",
        description=f"⚽ **{jogo['mandante']} x {jogo['visitante']}**\n"
                    f"📅 **Data / Horário:** {jogo['horario']}\n"
                    f"🏟️ **Local:** {jogo['estadio']}\n\n"
                    f"👇 *Deixe seu palpite oficial usando o comando* `/palpite`!",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="palpite", description="Abre o painel para registrar seu palpite de placar e artilheiros.")
async def palpite_cmd(interaction: discord.Interaction):
    config = carregar_dados(CONFIG_FILE)
    canal_permitido = config.get("canal_comandos")
    
    if canal_permitido and str(interaction.channel_id) != canal_permitido:
        await interaction.response.send_message(f"❌ Os comandos do bolão devem ser usados no canal <#{canal_permitido}>.", ephemeral=True)
        return

    jogo = carregar_dados(JOGO_ATIVO_FILE)
    if not jogo:
        await interaction.response.send_message("❌ Nenhum jogo ativo no momento para palpites.", ephemeral=True)
        return

    await interaction.response.send_modal(PalpiteModal(jogo))


@bot.tree.command(name="placarfinal", description="[Admin] Insere o placar final, artilheiros, calcula pontos e gera o ranking.")
@app_commands.describe(
    gols_mandante="Gols do mandante", 
    gols_visitante="Gols do visitante",
    artilheiros_reais="Quem fez os gols na partida real (Ex: Kaio Jorge)"
)
async def placarfinal_cmd(interaction: discord.Interaction, gols_mandante: int, gols_visitante: int, artilheiros_reais: str):
    if not verificar_permissao_adm(interaction):
        await interaction.response.send_message("❌ Você não tem permissão para usar este comando administrativo.", ephemeral=True)
        return

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
    vencedor_real = "mandante" if gols_mandante > gols_visitante else ("visitante" if gols_visitante > gols_mandante else "empate")

    for uid, dados in palpites.items():
        g_m = dados["g_mand"]
        g_v = dados["g_vis"]
        nome = dados["nome"]
        art_palpite = dados["artilheiros"].lower()
        
        vencedor_palpite = "mandante" if g_m > g_v else ("visitante" if g_v > g_m else "empate")
        pontos_ganhos = 0
        status_texto = "❌ Errou"
        
        # Pontuação: 3 pontos para placar exato, 1 ponto para vencedor correto
        if g_m == gols_mandante and g_v == gols_visitante:
            pontos_ganhos = 3
            status_texto = "🎯 Placar Exato! (+3 pts)"
        elif vencedor_palpite == vencedor_real:
            pontos_ganhos = 1
            status_texto = "✅ Acertou Vencedor! (+1 pt)"

        # Bônus extra opcional se acertar parte dos artilheiros citados
        if any(art.strip() in art_palpite for art in artilheiros_reais.lower().split(',')) and art_palpite != "nenhum citado":
            pontos_ganhos += 1
            status_texto += " + ⚽ Artilheiro (+1 pt)"

        if uid not in ranking:
            ranking[uid] = {"nome": nome, "pontos": 0}
        
        ranking[uid]["pontos"] += pontos_ganhos
        resultados_parciais += f"- <@{uid}> ({g_m}x{g_v}) — **{status_texto}**\n"

    salvar_dados(RANKING_FILE, ranking)

    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    texto_ranking = ""
    for idx, (uid, info) in enumerate(ranking_ordenado, start=1):
        texto_ranking += f"**{idx}º** — {info['nome']} (`{info['pontos']} pts`)\n"

    embed = discord.Embed(
        title=f"🏁 Resultado Final: {jogo['mandante']} {gols_mandante} x {gols_visitante} {jogo['visitante']}",
        description=f"⚽ **Artilheiros Oficiais:** {artilheiros_reais}\n\n"
                    f"**Apuração dos Palpites:**\n{resultados_parciais}\n\n"
                    f"🏆 **Ranking Geral Atualizado:**\n{texto_ranking}",
        color=0x0033A0
    )

    config = carregar_dados(CONFIG_FILE)
    canal_ranking_id = config.get("canal_ranking")
    
    if canal_ranking_id:
        canal_rank = interaction.guild.get_channel(int(canal_ranking_id))
        if canal_rank:
            await canal_rank.send(embed=embed)
            await interaction.response.send_message(f"✅ Placar apurado com sucesso! O ranking foi enviado para o canal {canal_rank.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(embed=embed)

    if os.path.exists(JOGO_ATIVO_FILE):
        os.remove(JOGO_ATIVO_FILE)


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
