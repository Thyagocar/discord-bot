import os
import json
import discord
from discord import app_commands, ui
from discord.ext import commands
from flask import Flask

# ================= MINI SERVIDOR WEB PARA O RENDER =================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot está online!"
# ===================================================================

TOKEN_DO_BOT = os.getenv("DISCORD_TOKEN")

CONFIG_FILE = "config.json"
PALPITES_FILE = "palpites.json"
RANKING_FILE = "ranking.json"
JOGO_ATIVO_FILE = "jogo_ativo.json"

intents = discord.Intents.default()
intents.members = True        
intents.message_content =  True   

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= SISTEMA DE DADOS MULTI-SERVIDOR =================
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


# ================= FUNÇÃO DE VERIFICAÇÃO DE PERMISSÃO =================
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


# ================= AUTOCOMPLETAR INTELIGENTE PARA CARGOS E CANAIS =================

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


# ================= MODAL DO BOTÃO DO PAINEL =================

class PainelConfigView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📋 Como Configurar o Servidor", style=discord.ButtonStyle.primary, custom_id="btn_ajuda_admin", row=0)
    async def ajuda_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🛠️ Painel de Ajuda - Administradores",
            description="Utilize os comandos de barra (`/`) abaixo para configurar o bolão:\n\n"
                        "⚙️ **`/configcargo`** — Define o cargo com permissão de adm.\n"
                        "💬 **`/configcanal`** — Define o canal onde a torcida envia palpites.\n"
                        "🏆 **`/configranking`** — Define o canal onde o ranking será postado.\n"
                        "👑 **`/configdestaque`** — Define o cargo automático para o 1º lugar.\n"
                        "🔔 **`/config-notificacao`** — Define canal e cargo de avisos automáticos.\n"
                        "📌 **`/setarjogo`** — Define o próximo confronto e avisa a torcida.\n"
                        "🔒 **`/fecharpalpites`** — Encerra as apostas do jogo atual e avisa no canal.\n"
                        "🏁 **`/placarfinal`** — Insere o placar, marcadores, atualiza o líder e gera o ranking.",
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_guild_join(guild):
    await garantir_canal_config(guild)

async def garantir_canal_config(guild):
    """Garante que o canal de configuração exista e envia o painel atualizado"""
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
        title="🤖 Painel de Configuração do Bolão - Cruzeiro",
        description="Este canal é **privado** e visível apenas para administradores.\n\n"
                    "Para configurar os cargos e canais, use os comandos:\n"
                    "• `/configcargo`\n"
                    "• `/configcanal`\n"
                    "• `/configranking`\n"
                    "• `/configdestaque`\n"
                    "• `/config-notificacao`",
        color=0x0033A0
    )
    
    try:
        async for mensagem in canal_existente.history(limit=10):
            if mensagem.author == bot.user:
                await mensagem.delete()
    except:
        pass

    await canal_existente.send(embed=embed, view=PainelConfigView())


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
            placeholder="Ex: 1",
            min_length=1,
            max_length=2,
            required=True
        )
        self.marcador = ui.TextInput(
            label="Quem fará gol na partida? (Opcional)",
            placeholder="Ex: Kaio Jorge, Dinenno",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=200
        )

        self.add_item(self.gols_mandante)
        self.add_item(self.gols_visitante)
        self.add_item(self.marcador)

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
        marcadores_usuario = self.marcador.value.strip() or "Nenhum citado"

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
                f"Seu palpite salvo: **{self.jogo['mandante']} {p_antigo['g_mand']} x {p_antigo['g_vis']} {self.jogo['visitante']}**\n"
                f"⚽ Marcador: *{p_antigo['marcador']}*", 
                ephemeral=True
            )
            return

        palpites_servidor[user_id] = {
            "nome": user_name,
            "g_mand": g_mandante,
            "g_vis": g_visitante,
            "marcador": marcadores_usuario
        }
        salvar_dados(PALPITES_FILE, palpites_geral)

        embed = discord.Embed(
            title="🎯 Palpite Registrado com Sucesso!",
            description=f"Partida: **{self.jogo['mandante']} {g_mandante} x {g_visitante} {self.jogo['visitante']}**\n"
                        f"⚽ Marcador Palpitado: *{marcadores_usuario}*\n\n"
                        f"🔒 Salvo com sucesso!",
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ================= EVENTO ON_READY =================

@bot.event
async def on_ready():
    bot.add_view(PainelConfigView())
    try:
        synced = await bot.tree.sync()
        print(f"🤖 Bot conectado como: {bot.user.name}")
        print(f"⚙️ Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")


# ================= COMANDOS DE CONFIGURAÇÃO =================

@bot.tree.command(name="configcargo", description="[Admin] Define o cargo com permissão para usar comandos administrativos.")
@app_commands.describe(cargo_id="Selecione ou digite o nome do cargo")
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

    role = interaction.guild.get_role(int(cargo_id))
    await interaction.response.send_message(f"✅ Cargo de Administrador configurado para: **{role.name if role else cargo_id}**", ephemeral=True)


@bot.tree.command(name="configcanal", description="[Admin] Define o canal onde a torcida usará /palpite.")
@app_commands.describe(canal_id="Selecione ou digite o canal de palpites")
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
    await interaction.response.send_message(f"✅ Canal de palpites configurado para: <#{canal_id}>", ephemeral=True)


@bot.tree.command(name="configranking", description="[Admin] Define o canal onde o ranking final será publicado.")
@app_commands.describe(canal_id="Selecione ou digite o canal de ranking")
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
    await interaction.response.send_message(f"✅ Canal de ranking configurado para: <#{canal_id}>", ephemeral=True)


@bot.tree.command(name="configdestaque", description="[Admin] Define o cargo automático que o 1º lugar do ranking vai receber.")
@app_commands.describe(cargo_id="Selecione ou digite o nome do cargo para o líder")
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

    role = interaction.guild.get_role(int(cargo_id))
    await interaction.response.send_message(f"✅ Cargo de Destaque do Líder configurado para: **{role.name if role else cargo_id}**", ephemeral=True)


@bot.tree.command(name="config-notificacao", description="[Admin] Define canal e cargo para avisos de novos jogos.")
@app_commands.describe(canal="Canal onde o aviso será enviado", cargo="Cargo a ser marcado (ex: @everyone ou cargo da torcida)")
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
    await interaction.response.send_message(f"✅ Notificações configuradas no canal {canal.mention} marcando o cargo {cargo.mention}.", ephemeral=True)


# ================= COMANDOS DO BOLÃO =================

@bot.tree.command(name="setarjogo", description="[Admin] Define o próximo jogo e avisa a torcida.")
async def setarjogo_cmd(interaction: discord.Interaction, mandante: str, visitante: str, horario: str, estadio: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    guild_id = str(interaction.guild_id)
    
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogos_geral[guild_id] = {
        "mandante": mandante,
        "visitante": visitante,
        "horario": horario,
        "estadio": estadio,
        "aberto": True
    }
    salvar_dados(JOGO_ATIVO_FILE, jogos_geral)

    palpites_geral = carregar_dados(PALPITES_FILE)
    palpites_geral[guild_id] = {}
    salvar_dados(PALPITES_FILE, palpites_geral)

    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    
    if "canal_notif" in config and "cargo_notif" in config:
        canal = interaction.guild.get_channel(int(config["canal_notif"]))
        cargo_id_str = config["cargo_notif"]
        canal_cmd_id = config.get("canal_comandos")
        
        if canal:
            canal_mencao = f"<#{canal_cmd_id}>" if canal_cmd_id else "no canal de palpites"
            embed_aviso = discord.Embed(
                title="📢 Novo Jogo Cadastrado no Bolão!",
                description=f"⚽ **{mandante} x {visitante}**\n📅 **Horário:** {horario}\n🏟️ **Estádio:** {estadio}\n\n"
                            f"O bolão está aberto! Vá até {canal_mencao} e use `/palpite` para registrar sua aposta.",
                color=0x0033A0
            )
            
            if cargo_id_str == str(interaction.guild.default_role.id):
                mencao_texto = "@everyone"
            else:
                role_obj = interaction.guild.get_role(int(cargo_id_str))
                mencao_texto = role_obj.mention if role_obj else ""

            await canal.send(content=mencao_texto, embed=embed_aviso)

    embed = discord.Embed(
        title="⚽ Jogo Definido com Sucesso!",
        description=f"**{mandante} x {visitante}** configurado e notificação disparada!",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="fecharpalpites", description="[Admin] Encerra as apostas para o jogo atual.")
async def fecharpalpites_cmd(interaction: discord.Interaction):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo no momento.", ephemeral=True)

    jogo["aberto"] = False
    salvar_dados(JOGO_ATIVO_FILE, jogos_geral)

    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    
    if "canal_notif" in config:
        canal = interaction.guild.get_channel(int(config["canal_notif"]))
        if canal:
            embed_fechamento = discord.Embed(
                title="🔒 Palpites Encerrados!",
                description=f"As apostas para o confronto **{jogo['mandante']} x {jogo['visitante']}** foram trancadas pela administração. Boa sorte a todos!",
                color=0xCC0000
            )
            await canal.send(embed=embed_fechamento)

    await interaction.response.send_message("🔒 Palpites encerrados com sucesso para este jogo e aviso enviado no canal de notificações!", ephemeral=True)


@bot.tree.command(name="proximojogo", description="Mostra os detalhes do próximo jogo do Cruzeiro.")
async def proximojogo_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_permitido = config.get("canal_comandos")
    
    if canal_permitido and str(interaction.channel_id) != canal_permitido:
        return await interaction.response.send_message(f"❌ Use os comandos no canal <#{canal_permitido}>.", ephemeral=True)

    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo configurado no momento.", ephemeral=True)

    esta_aberto = jogo.get("aberto", True)
    status_texto = "🟢 Aberto para Palpites" if esta_aberto else "🔴 Palpites encerrados"
    
    descricao = (
        f"⚽ **{jogo['mandante']} x {jogo['visitante']}**\n"
        f"📅 **Data / Horário:** {jogo['horario']}\n"
        f"🏟️ **Local:** {jogo['estadio']}\n"
        f"🟢 **Status:** {status_texto}\n\n"
    )

    if esta_aberto:
        descricao += "👇 Use `/palpite` para participar!"
    else:
        descricao += "🔒 *As apostas para esta partida já foram encerradas.*"

    embed = discord.Embed(
        title="🦊 Próximo Jogo do Cruzeiro",
        description=descricao,
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="palpite", description="Abre o painel para registrar seu palpite.")
async def palpite_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_permitido = config.get("canal_comandos")
    
    if canal_permitido and str(interaction.channel_id) != canal_permitido:
        return await interaction.response.send_message(f"❌ Use os comandos no canal <#{canal_permitido}>.", ephemeral=True)

    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo no momento.", ephemeral=True)
    
    if not jogo.get("aberto", True):
        return await interaction.response.send_message("❌ Os palpites para este jogo já foram encerrados pela administração!", ephemeral=True)

    await interaction.response.send_modal(PalpiteModal(jogo))


@bot.tree.command(name="perfil", description="Mostra suas estatísticas individuais no bolão.")
async def perfil_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    ranking_geral = carregar_dados(RANKING_FILE)
    ranking_servidor = ranking_geral.get(guild_id, {})
    
    user_id = str(interaction.user.id)
    
    if user_id not in ranking_servidor:
        return await interaction.response.send_message("❌ Você ainda não possui pontos ou palpites registrados no ranking.", ephemeral=True)

    dados = ranking_servidor[user_id]
    embed = discord.Embed(
        title=f"📊 Perfil de Estatísticas — {interaction.user.display_name}",
        description=f"🏆 **Pontuação Total:** `{dados.get('pontos', 0)} pts`\n"
                    f"🎯 **Placares Exatos (Cravadas):** `{dados.get('exatos', 0)}`\n"
                    f"⚽ **Marcadores Certos:** `{dados.get('marcadores', 0)}`",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="placarfinal", description="[Admin] Insere placar, marcadores, calcula pontos e gera ranking.")
@app_commands.describe(
    gols_mandante="Gols do mandante", 
    gols_visitante="Gols do visitante",
    marcadores_reais="Quem fez os gols na partida real (Ex: Kaio Jorge)"
)
async def placarfinal_cmd(interaction: discord.Interaction, gols_mandante: int, gols_visitante: int, marcadores_reais: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    guild_id = str(interaction.guild_id)
    
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo:
        return await interaction.response.send_message("❌ Não há nenhum jogo ativo salvo.", ephemeral=True)

    palpites_geral = carregar_dados(PALPITES_FILE)
    palpites = palpites_geral.get(guild_id, {})
    if not palpites:
        return await interaction.response.send_message("❌ Nenhum usuário enviou palpite.", ephemeral=True)

    ranking_geral = carregar_dados(RANKING_FILE)
    if guild_id not in ranking_geral:
        ranking_geral[guild_id] = {}
    ranking = ranking_geral[guild_id]

    resultados_parciais = ""
    vencedor_real = "mandante" if gols_mandante > gols_visitante else ("visitante" if gols_visitante > gols_mandante else "empate")

    for uid, dados in palpites.items():
        g_m = dados["g_mand"]
        g_v = dados["g_vis"]
        nome = dados["nome"]
        marc_palpite = dados["marcador"].lower()
        
        vencedor_palpite = "mandante" if g_m > g_v else ("visitante" if g_v > g_m else "empate")
        pontos_ganhos = 0
        status_texto = "❌ Errou"
        acertou_exato = False
        acertou_marcador = False
        
        if g_m == gols_mandante and g_v == gols_visitante:
            pontos_ganhos = 3
            status_texto = "🎯 Placar Exato! (+3 pts)"
            acertou_exato = True
        elif vencedor_palpite == vencedor_real:
            pontos_ganhos = 1
            status_texto = "✅ Acertou Vencedor! (+1 pt)"

        if any(m.strip().lower() in marc_palpite for m in marcadores_reais.lower().split(',')) and marc_palpite != "nenhum citado":
            pontos_ganhos += 2
            status_texto += " + ⚽ Acertou o Marcador (+2 pts)"
            acertou_marcador = True

        if uid not in ranking:
            ranking[uid] = {"nome": nome, "pontos": 0, "exatos": 0, "marcadores": 0}
        
        ranking[uid]["pontos"] += pontos_ganhos
        if acertou_exato:
            ranking[uid]["exatos"] += 1
        if acertou_marcador:
            ranking[uid]["marcadores"] += 1

        resultados_parciais += f"- <@{uid}> ({g_m}x{g_v}) — **{status_texto}**\n"

    salvar_dados(RANKING_FILE, ranking_geral)

    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    
    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    cargo_destaque_id = config.get("cargo_destaque")
    
    if cargo_destaque_id:
        role_destaque = interaction.guild.get_role(int(cargo_destaque_id))
        if role_destaque:
            novo_lider_uid = ranking_ordenado[0][0]
            
            for member in role_destaque.members:
                if str(member.id) != novo_lider_uid:
                    try:
                        await member.remove_roles(role_destaque)
                    except:
                        pass
            
            try:
                membro_lider = interaction.guild.get_member(int(novo_lider_uid))
                if not membro_lider:
                    membro_lider = await interaction.guild.fetch_member(int(novo_lider_uid))
                if membro_lider and role_destaque not in membro_lider.roles:
                    await membro_lider.add_roles(role_destaque)
            except Exception as e:
                print(f"Erro ao atribuir cargo de destaque: {e}")

    texto_ranking = ""
    for idx, (uid, info) in enumerate(ranking_ordenado, start=1):
        texto_ranking += f"**{idx}º** — {info['nome']} (`{info['pontos']} pts`)\n"

    embed = discord.Embed(
        title=f"🏁 Resultado Final: {jogo['mandante']} {gols_mandante} x {gols_visitante} {jogo['visitante']}",
        description=f"⚽ **Marcadores Oficiais:** {marcadores_reais}\n\n"
                    f"**Apuração:**\n{resultados_parciais}\n\n"
                    f"🏆 **Ranking Geral Atualizado:**\n{texto_ranking}",
        color=0x0033A0
    )

    canal_ranking_id = config.get("canal_ranking")
    if canal_ranking_id:
        canal_rank = interaction.guild.get_channel(int(canal_ranking_id))
        if canal_rank:
            await canal_rank.send(embed=embed)
            await interaction.response.send_message(f"✅ Placar apurado, cargo de destaque atualizado e ranking enviado para {canal_rank.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(embed=embed)

    if guild_id in jogos_geral:
        del jogos_geral[guild_id]
        salvar_dados(JOGO_ATIVO_FILE, jogos_geral)


@bot.tree.command(name="ranking", description="Mostra a classificação geral do Bolão.")
async def ranking_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    ranking_geral = carregar_dados(RANKING_FILE)
    ranking = ranking_geral.get(guild_id, {})
    
    if not ranking:
        return await interaction.response.send_message("🏆 O ranking do bolão está vazio.", ephemeral=True)

    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    embed = discord.Embed(title="🏆 Ranking Geral do Bolão Celeste", color=0x0033A0)
    
    texto = ""
    for idx, (uid, info) in enumerate(ranking_ordenado, start=1):
        texto += f"**{idx}º** {info['nome']} — `{info['pontos']} pts`\n"
        
    embed.description = texto
    await interaction.response.send_message(embed=embed)


# Inicialização segura exclusiva para o bot do Discord rodar de forma isolada
if __name__ == "__main__":
    bot.run(TOKEN_DO_BOT)
