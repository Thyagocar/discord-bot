import os
import json
import discord
from discord import app_commands, ui
from discord.ext import commands

TOKEN_DO_BOT = os.getenv("DISCORD_TOKEN")

CONFIG_FILE = "config.json"
PALPITES_FILE = "palpites.json"
RANKING_FILE = "ranking.json"
JOGO_ATIVO_FILE = "jogo_ativo.json"
ELENCO_FILE = "elenco.json"

intents = discord.Intents.default()
intents.members = True        
intents.message_content = True  

bot = commands.Bot(command_prefix="!", intents=intents)

ELENCO_PADRAO = [
    "Cássio", "Léo Aragão", "Otávio Costa",
    "Fabrício Bruno", "Jonathan Jesus", "João Marcelo", "Lucas Villalba", "William", "Fagner", "Kauã Moraes", "Gabriel Rojas", "Kauã Prates",
    "Gerson", "Matheus Pereira", "Matheus Henrique", "Lucas Romero", "Lucas Silva", "Fabrizio Peralta", "Ian Luccas", "Zé Lucas",
    "Kaio Jorge", "Luis Sinisterra", "Gabriel Pec", "Keny Arroyo", "Luciano Rodríguez", "Néiser Villarreal", "Chico da Costa", "Wanderson", "Marquinhos", "Kaique Kenji", "Bruno Rodrigues"
]

def carregar_dados(arquivo):
    if os.path.exists(arquivo):
        with open(arquivo, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def salvar_dados(arquivo, dados):
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def verificar_permissao_adm(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    config_geral = carregar_dados(CONFIG_FILE)
    config_servidor = config_geral.get(str(interaction.guild_id), {})
    cargos_permitidos = config_servidor.get("cargos_adm", [])
    for role in interaction.user.roles:
        if str(role.id) in cargos_permitidos:
            return True
    return False

async def autocomplete_cargos(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=role.name, value=str(role.id))
        for role in interaction.guild.roles if current.lower() in role.name.lower()
    ][:25]

async def autocomplete_canais(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=f"#{channel.name}", value=str(channel.id))
        for channel in interaction.guild.text_channels if current.lower() in channel.name.lower()
    ][:25]

async def autocomplete_jogadores(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild_id)
    elenco_geral = carregar_dados(ELENCO_FILE)
    jogadores = elenco_geral.get(guild_id, ELENCO_PADRAO)
    return [
        app_commands.Choice(name=jogador, value=jogador)
        for jogador in jogadores if current.lower() in jogador.lower()
    ][:25]

class PainelConfigView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📋 Como Configurar o Servidor", style=discord.ButtonStyle.primary, custom_id="btn_ajuda_admin", row=0)
    async def ajuda_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🛠️ Painel de Ajuda - Administradores",
            description="Utilize os comandos de barra (`/`) abaixo:\n\n"
                        "⚙️ **`/configcargo`** — Define o cargo com permissão de adm.\n"
                        "💬 **`/configcanal`** — Define o canal onde a torcida envia palpites.\n"
                        "🏆 **`/configranking`** — Define o canal onde o ranking será postado.\n"
                        "👑 **`/configdestaque`** — Define o cargo automático para o 1º lugar.\n"
                        "⚽ **`/adicionarjogador`** — Adiciona um jogador à lista do elenco.\n"
                        "❌ **`/removerjogador`** — Remove um jogador da lista do elenco.\n"
                        "📌 **`/setarjogo`** — Define o próximo confronto e avisa a torcida.\n"
                        "🔒 **`/fecharpalpites`** — Encerra as apostas do jogo atual.\n"
                        "🏁 **`/placarfinal`** — Insere o placar, marcadores, assistências e atualiza o ranking.",
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_guild_join(guild):
    await criar_canal_config(guild)

async def criar_canal_config(guild):
    canal_existente = discord.utils.get(guild.text_channels, name="⚙️│config-bot")
    if not canal_existente:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        canal_existente = await guild.create_text_channel("⚙️│config-bot", overwrites=overwrites)

    embed = discord.Embed(
        title="🤖 Painel de Configuração do Bolão",
        description="Este canal é **privado** e visível apenas para administradores.\n\n"
                    "Clique no botão abaixo para ver como configurar o bot no seu servidor.",
        color=0x0033A0
    )
    try:
        async for mensagem in canal_existente.history(limit=10):
            if mensagem.author == bot.user:
                await mensagem.delete()
    except:
        pass
    await canal_existente.send(embed=embed, view=PainelConfigView())

class PalpiteModal(ui.Modal):
    def __init__(self, jogo):
        mandante = jogo["mandante"]
        visitante = jogo["visitante"]
        super().__init__(title=f"Palpite: {mandante} x {visitante}")
        self.jogo = jogo

        self.gols_mandante = ui.TextInput(label=f"Gols do {mandante}", placeholder="Ex: 2", min_length=1, max_length=2, required=True)
        self.gols_visitante = ui.TextInput(label=f"Gols do {visitante}", placeholder="Ex: 1", min_length=1, max_length=2, required=True)
        self.marcador = ui.TextInput(label="Quem fará gol? (Nome do jogador)", placeholder="Ex: Kaio Jorge", required=True, max_length=100)
        self.assistencia = ui.TextInput(label="Quem dará assistência? (Opcional)", placeholder="Ex: Matheus Pereira", required=False, max_length=100)

        self.add_item(self.gols_mandante)
        self.add_item(self.gols_visitante)
        self.add_item(self.marcador)
        self.add_item(self.assistencia)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
        jogo_atual = jogos_geral.get(guild_id)

        if not jogo_atual or not jogo_atual.get("aberto", True):
            await interaction.response.send_message("❌ Os palpites para este jogo já foram encerrados!", ephemeral=True)
            return

        if not (self.gols_mandante.value.isdigit() and self.gols_visitante.value.isdigit()):
            await interaction.response.send_message("❌ Insira apenas números válidos para o placar!", ephemeral=True)
            return

        g_mandante = int(self.gols_mandante.value)
        g_visitante = int(self.gols_visitante.value)
        marcador_usuario = self.marcador.value.strip()
        assistencia_usuario = self.assistencia.value.strip() or "Nenhuma"

        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name

        palpites_geral = carregar_dados(PALPITES_FILE)
        if guild_id not in palpites_geral:
            palpites_geral[guild_id] = {}
        
        palpites_servidor = palpites_geral[guild_id]
        if user_id in palpites_servidor:
            p_antigo = palpites_servidor[user_id]
            await interaction.response.send_message(
                f"❌ Você já enviou seu palpite para este jogo e ele está trancado!\n"
                f"Seu palpite salvo: **{self.jogo['mandante']} {p_antigo['g_mand']} x {p_antigo['g_vis']} {self.jogo['visitante']}**", 
                ephemeral=True
            )
            return

        palpites_servidor[user_id] = {
            "nome": user_name,
            "g_mand": g_mandante,
            "g_vis": g_visitante,
            "marcador": marcador_usuario,
            "assistencia": assistencia_usuario
        }
        salvar_dados(PALPITES_FILE, palpites_geral)

        embed = discord.Embed(
            title="🎯 Palpite Registrado com Sucesso!",
            description=f"Partida: **{self.jogo['mandante']} {g_mandante} x {g_visitante} {self.jogo['visitante']}**\n"
                        f"⚽ Gol: *{marcador_usuario}*\n🎯 Assistência: *{assistension_usuario if 'assistension_usuario' in locals() else assistencia_usuario}*",
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(PainelConfigView())
    try:
        synced = await bot.tree.sync()
        print(f"🤖 Bot conectado como: {bot.user.name}")
        print(f"⚙️ Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

@bot.tree.command(name="adicionarjogador", description="[Admin] Adiciona um jogador à lista de opções do servidor.")
async def adicionarjogador_cmd(interaction: discord.Interaction, nome_jogador: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    guild_id = str(interaction.guild_id)
    elenco_geral = carregar_dados(ELENCO_FILE)
    if guild_id not in elenco_geral:
        elenco_geral[guild_id] = list(ELENCO_PADRAO)
    if nome_jogador in elenco_geral[guild_id]:
        return await interaction.response.send_message(f"⚠️ O jogador **{nome_jogador}** já está cadastrado.", ephemeral=True)
    elenco_geral[guild_id].append(nome_jogador)
    salvar_dados(ELENCO_FILE, elenco_geral)
    await interaction.response.send_message(f"✅ Jogador **{nome_jogador}** adicionado com sucesso!", ephemeral=True)

@bot.tree.command(name="removerjogador", description="[Admin] Remove um jogador da lista de opções do servidor.")
@app_commands.autocomplete(nome_jogador=autocomplete_jogadores)
async def removerjogador_cmd(interaction: discord.Interaction, nome_jogador: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    guild_id = str(interaction.guild_id)
    elenco_geral = carregar_dados(ELENCO_FILE)
    if guild_id not in elenco_geral:
        elenco_geral[guild_id] = list(ELENCO_PADRAO)
    if nome_jogador not in elenco_geral[guild_id]:
        return await interaction.response.send_message(f"❌ Jogador não encontrado.", ephemeral=True)
    elenco_geral[guild_id].remove(nome_jogador)
    salvar_dados(ELENCO_FILE, elenco_geral)
    await interaction.response.send_message(f"🗑️ Jogador **{nome_jogador}** removido!", ephemeral=True)

@bot.tree.command(name="configcargo", description="[Admin] Define o cargo administrativo.")
@app_commands.autocomplete(cargo_id=autocomplete_cargos)
async def configcargo_cmd(interaction: discord.Interaction, cargo_id: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)
    config_geral = carregar_dados(CONFIG_FILE)
    guild_id = str(interaction.guild_id)
    if guild_id not in config_geral:
        config_geral[guild_id] = {}
    config_geral[guild_id]["cargos_adm"] = [cargo_id]
    salvar_dados(CONFIG_FILE, config_geral)
    await interaction.response.send_message("✅ Cargo de administrador configurado com sucesso!", ephemeral=True)

@bot.tree.command(name="configcanal", description="[Admin] Define o canal de palpites.")
@app_commands.autocomplete(canal_id=autocomplete_canais)
async def configcanal_cmd(interaction: discord.Interaction, canal_id: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)
    config_geral = carregar_dados(CONFIG_FILE)
    guild_id = str(interaction.guild_id)
    if guild_id not in config_geral:
        config_geral[guild_id] = {}
    config_geral[guild_id]["canal_comandos"] = canal_id
    salvar_dados(CONFIG_FILE, config_geral)
    await interaction.response.send_message(f"✅ Canal de palpites configurado para <#{canal_id}>", ephemeral=True)

@bot.tree.command(name="configranking", description="[Admin] Define o canal de ranking.")
@app_commands.autocomplete(canal_id=autocomplete_canais)
async def configranking_cmd(interaction: discord.Interaction, canal_id: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)
    config_geral = carregar_dados(CONFIG_FILE)
    guild_id = str(interaction.guild_id)
    if guild_id not in config_geral:
        config_geral[guild_id] = {}
    config_geral[guild_id]["canal_ranking"] = canal_id
    salvar_dados(CONFIG_FILE, config_geral)
    await interaction.response.send_message(f"✅ Canal de ranking configurado para <#{canal_id}>", ephemeral=True)

@bot.tree.command(name="configdestaque", description="[Admin] Define o cargo para o 1º lugar.")
@app_commands.autocomplete(cargo_id=autocomplete_cargos)
async def configdestaque_cmd(interaction: discord.Interaction, cargo_id: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    config_geral = carregar_dados(CONFIG_FILE)
    guild_id = str(interaction.guild_id)
    if guild_id not in config_geral:
        config_geral[guild_id] = {}
    config_geral[guild_id]["cargo_destaque"] = cargo_id
    salvar_dados(CONFIG_FILE, config_geral)
    await interaction.response.send_message("✅ Cargo de destaque configurado!", ephemeral=True)

@bot.tree.command(name="config-notificacao", description="[Admin] Define canal e cargo para avisos de jogos.")
async def config_notif_cmd(interaction: discord.Interaction, canal: discord.TextChannel, cargo: discord.Role):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    config_geral = carregar_dados(CONFIG_FILE)
    guild_id = str(interaction.guild_id)
    if guild_id not in config_geral:
        config_geral[guild_id] = {}
    config_geral[guild_id]["canal_notif"] = str(canal.id)
    config_geral[guild_id]["cargo_notif"] = str(cargo.id)
    salvar_dados(CONFIG_FILE, config_geral)
    await interaction.response.send_message("✅ Notificações configuradas com sucesso!", ephemeral=True)

@bot.tree.command(name="setarjogo", description="[Admin] Define o próximo jogo.")
async def setarjogo_cmd(interaction: discord.Interaction, mandante: str, visitante: str, horario: str, estadio: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogos_geral[guild_id] = {"mandante": mandante, "visitante": visitante, "horario": horario, "estadio": estadio, "aberto": True}
    salvar_dados(JOGO_ATIVO_FILE, jogos_geral)
    palpites_geral = carregar_dados(PALPITES_FILE)
    palpites_geral[guild_id] = {}
    salvar_dados(PALPITES_FILE, palpites_geral)
    await interaction.response.send_message(f"⚽ Jogo **{mandante} x {visitante}** definido!", ephemeral=True)

@bot.tree.command(name="fecharpalpites", description="[Admin] Encerra as apostas.")
async def fecharpalpites_cmd(interaction: discord.Interaction):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo.", ephemeral=True)
    jogo["aberto"] = False
    salvar_dados(JOGO_ATIVO_FILE, jogos_geral)
    await interaction.response.send_message("🔒 Palpites encerrados com sucesso!", ephemeral=True)

@bot.tree.command(name="proximojogo", description="Mostra o próximo jogo.")
async def proximojogo_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo configurado.", ephemeral=True)
    embed = discord.Embed(title="🦊 Próximo Jogo", description=f"**{jogo['mandante']} x {jogo['visitante']}**\n📅 {jogo['horario']}\n🏟️ {jogo['estadio']}", color=0x0033A0)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="palpite", description="Abre o painel para registrar seu palpite.")
async def palpite_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo or not jogo.get("aberto", True):
        return await interaction.response.send_message("❌ Não há jogos abertos para palpite no momento.", ephemeral=True)
    await interaction.response.send_modal(PalpiteModal(jogo))

@bot.tree.command(name="ranking", description="Mostra o ranking do Bolão.")
async def ranking_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    ranking_geral = carregar_dados(RANKING_FILE)
    ranking = ranking_geral.get(guild_id, {})
    if not ranking:
        return await interaction.response.send_message("🏆 O ranking está vazio.", ephemeral=True)
    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    texto = "\n".join([f"**{idx}º** {info['nome']} — `{info['pontos']} pts`" for idx, (uid, info) in enumerate(ranking_ordenado, start=1)])
    embed = discord.Embed(title="🏆 Ranking Geral", description=texto, color=0x0033A0)
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    if not TOKEN_DO_BOT:
        print("❌ ERRO: DISCORD_TOKEN não encontrado nas variáveis de ambiente!")
    else:
        bot.run(TOKEN_DO_BOT)
