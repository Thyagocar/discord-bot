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

def obter_elenco_servidor(guild_id_str):
    elenco_geral = carregar_dados(ELENCO_FILE)
    if guild_id_str in elenco_geral:
        return elenco_geral[guild_id_str]
    if "elenco_inicial" in elenco_geral:
        lista_inicial = elenco_geral["elenco_inicial"]
        elenco_geral[guild_id_str] = lista_inicial
        salvar_dados(ELENCO_FILE, elenco_geral)
        return lista_inicial
    return []

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

async def autocomplete_jogadores(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild_id)
    jogadores = obter_elenco_servidor(guild_id)
    return [
        app_commands.Choice(name=jogador, value=jogador)
        for jogador in jogadores if current.lower() in jogador.lower()
    ][:25]

# --- PAINEL E MENUS DE CONFIGURAÇÃO ---

class SetupSelectCanalRanking(ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o canal do Ranking", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        config_geral = carregar_dados(CONFIG_FILE)
        if guild_id not in config_geral: config_geral[guild_id] = {}
        config_geral[guild_id]["canal_ranking"] = str(self.values[0].id)
        salvar_dados(CONFIG_FILE, config_geral)
        await interaction.response.send_message(f"✅ Canal de Ranking definido para {self.values[0].mention}!", ephemeral=True)

class SetupSelectCanalComandos(ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o canal para /palpite", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, row=1)

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        config_geral = carregar_dados(CONFIG_FILE)
        if guild_id not in config_geral: config_geral[guild_id] = {}
        config_geral[guild_id]["canal_comandos"] = str(self.values[0].id)
        salvar_dados(CONFIG_FILE, config_geral)
        await interaction.response.send_message(f"✅ Canal de comandos definido para {self.values[0].mention}!", ephemeral=True)

class SetupSelectCanalAvisos(ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o canal de Avisos de Jogos", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, row=2)

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        config_geral = carregar_dados(CONFIG_FILE)
        if guild_id not in config_geral: config_geral[guild_id] = {}
        config_geral[guild_id]["canal_avisos"] = str(self.values[0].id)
        salvar_dados(CONFIG_FILE, config_geral)
        await interaction.response.send_message(f"✅ Canal de avisos definido para {self.values[0].mention}!", ephemeral=True)

class SetupSelectCargoAdm(ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o Cargo de ADM do Bot", min_values=1, max_values=1, row=3)

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        config_geral = carregar_dados(CONFIG_FILE)
        if guild_id not in config_geral: config_geral[guild_id] = {}
        config_geral[guild_id]["cargos_adm"] = [str(self.values[0].id)]
        salvar_dados(CONFIG_FILE, config_geral)
        await interaction.response.send_message(f"✅ Cargo de ADM definido para {self.values[0].mention}!", ephemeral=True)

class SetupSelectCargoMarcacao(ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o Cargo a ser marcado nos avisos", min_values=1, max_values=1, row=4)

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        config_geral = carregar_dados(CONFIG_FILE)
        if guild_id not in config_geral: config_geral[guild_id] = {}
        config_geral[guild_id]["cargo_marcacao"] = str(self.values[0].id)
        salvar_dados(CONFIG_FILE, config_geral)
        await interaction.response.send_message(f"✅ Cargo de marcação definido para {self.values[0].mention}!", ephemeral=True)

class SetupSelectCargoTop1(ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o Cargo para o TOP 1 do Ranking", min_values=1, max_values=1, row=4)

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        config_geral = carregar_dados(CONFIG_FILE)
        if guild_id not in config_geral: config_geral[guild_id] = {}
        config_geral[guild_id]["cargo_top1"] = str(self.values[0].id)
        salvar_dados(CONFIG_FILE, config_geral)
        await interaction.response.send_message(f"✅ Cargo de TOP 1 definido para {self.values[0].mention}!", ephemeral=True)

class SetupView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SetupSelectCanalRanking())
        self.add_item(SetupSelectCanalComandos())
        self.add_item(SetupSelectCanalAvisos())
        self.add_item(SetupSelectCargoAdm())
        self.add_item(SetupSelectCargoTop1())

    @ui.button(label="📖 Ver Comandos e Ajuda", style=discord.ButtonStyle.blurple, row=4)
    async def ver_ajuda(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📚 Guia de Comandos do Bot",
            description="Aqui estão todos os comandos disponíveis e para que servem:",
            color=0x0033A0
        )
        embed.add_field(name="/palpite", value="Abre o painel para registrar sua aposta (gols, marcadores e assistentes).", inline=False)
        embed.add_field(name="/proximojogo", value="Mostra as informações da partida ativa no momento.", inline=False)
        embed.add_field(name="/ranking", value="Exibe a tabela atualizada de pontuação do servidor.", inline=False)
        embed.add_field(name="/setarjogo", value="[Admin] Define um novo confronto e avisa no canal configurado.", inline=False)
        embed.add_field(name="/fecharpalpite", value="[Admin] Encerra imediatamente o recebimento de palpites.", inline=False)
        embed.add_field(name="/placarfinal", value="[Admin] Insere o placar real, pontua todo mundo, atualiza o ranking e o cargo de TOP 1.", inline=False)
        embed.add_field(name="/adicionarjogador", value="[Admin] Adiciona um jogador ao elenco do servidor.", inline=False)
        embed.add_field(name="/removerjogador", value="[Admin] Remove um jogador do elenco do servidor.", inline=False)
        embed.add_field(name="/setup", value="[Admin] Recria este painel de configuração.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- MODAIS DE PALPITES ---

class PalpiteModal(ui.Modal):
    def __init__(self, jogo):
        mandante = jogo["mandante"]
        visitante = jogo["visitante"]
        super().__init__(title=f"Palpite: {mandante} x {visitante}")
        self.jogo = jogo
        self.gols_mandante = ui.TextInput(label=f"Gols do {mandante}", placeholder="Ex: 2", min_length=1, max_length=2, required=True)
        self.gols_visitante = ui.TextInput(label=f"Gols do {visitante}", placeholder="Ex: 1", min_length=1, max_length=2, required=True)
        self.marcadores = ui.TextInput(label="Marcador(es) do Gol", placeholder="Ex: Jogador A, Jogador B (ou Nenhum)", required=True)
        self.assistentes = ui.TextInput(label="Assistente(s) do Gol", placeholder="Ex: Jogador C (ou Nenhum)", required=True)
        
        self.add_item(self.gols_mandante)
        self.add_item(self.gols_visitante)
        self.add_item(self.marcadores)
        self.add_item(self.assistentes)

    async def on_submit(self, interaction: discord.Interaction):
        if not (self.gols_mandante.value.isdigit() and self.gols_visitante.value.isdigit()):
            await interaction.response.send_message("❌ Insira apenas números válidos para o placar!", ephemeral=True)
            return
        
        g_mand = int(self.gols_mandante.value)
        g_vis = int(self.gols_visitante.value)
        marc = self.marcadores.value.strip()
        asst = self.assistentes.value.strip()

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        
        palpites_geral = carregar_dados(PALPITES_FILE)
        if guild_id not in palpites_geral:
            palpites_geral[guild_id] = {}
        
        palpites_servidor = palpites_geral[guild_id]
        if user_id in palpites_servidor:
            await interaction.response.send_message(f"❌ Você já enviou seu palpite para este jogo!", ephemeral=True)
            return

        palpites_servidor[user_id] = {
            "nome": user_name,
            "g_mand": g_mand,
            "g_vis": g_vis,
            "marcador": marc,
            "assistente": asst
        }
        salvar_dados(PALPITES_FILE, palpites_geral)

        embed = discord.Embed(
            title="🎯 Palpite Registrado com Sucesso!", 
            description=f"Partida: **{self.jogo['mandante']} {g_mand} x {g_vis} {self.jogo['visitante']}**\n⚽ **Marcador(es):** {marc}\n👟 **Assistente(s):** {asst}", 
            color=0x0033A0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"🤖 Bot conectado como: {bot.user.name}")
        print(f"⚙️ Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    canal = await guild.create_text_channel("config-bot-palpites", overwrites=overwrites)
    embed = discord.Embed(
        title="⚙️ Painel de Configuração do Bot",
        description="Bem-vindo! Use os menus e botões abaixo para configurar rapidamente o bot no seu servidor:",
        color=0x0033A0
    )
    await canal.send(embed=embed, view=SetupView())

@bot.tree.command(name="setup", description="[Admin] Cria o painel de configuração privado.")
async def setup_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)
    
    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    canal = await guild.create_text_channel("config-bot-palpites", overwrites=overwrites)
    embed = discord.Embed(
        title="⚙️ Painel de Configuração do Bot",
        description="Configure abaixo as opções do bot:",
        color=0x0033A0
    )
    await canal.send(embed=embed, view=SetupView())
    await interaction.response.send_message(f"✅ Canal de configuração criado: {canal.mention}", ephemeral=True)

@bot.tree.command(name="adicionarjogador", description="[Admin] Adiciona um jogador ao elenco.")
async def adicionarjogador_cmd(interaction: discord.Interaction, nome: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    guild_id = str(interaction.guild_id)
    elenco_geral = carregar_dados(ELENCO_FILE)
    if guild_id not in elenco_geral:
        elenco_geral[guild_id] = obter_elenco_servidor(guild_id)
    nome_formatado = nome.strip()
    if nome_formatado in elenco_geral[guild_id]:
        return await interaction.response.send_message(f"❌ Jogador já cadastrado!", ephemeral=True)
    elenco_geral[guild_id].append(nome_formatado)
    elenco_geral[guild_id].sort()
    salvar_dados(ELENCO_FILE, elenco_geral)
    await interaction.response.send_message(f"✅ Jogador **{nome_formatado}** adicionado!", ephemeral=True)

@bot.tree.command(name="removerjogador", description="[Admin] Remove um jogador do elenco.")
@app_commands.autocomplete(nome=autocomplete_jogadores)
async def removerjogador_cmd(interaction: discord.Interaction, nome: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    guild_id = str(interaction.guild_id)
    elenco_geral = carregar_dados(ELENCO_FILE)
    if guild_id not in elenco_geral:
        elenco_geral[guild_id] = obter_elenco_servidor(guild_id)
    if nome not in elenco_geral[guild_id]:
        return await interaction.response.send_message(f"❌ Jogador não encontrado.", ephemeral=True)
    elenco_geral[guild_id].remove(nome)
    salvar_dados(ELENCO_FILE, elenco_geral)
    await interaction.response.send_message(f"🗑️ Jogador **{nome}** removido!", ephemeral=True)

@bot.tree.command(name="setarjogo", description="[Admin] Define o próximo jogo.")
async def setarjogo_cmd(interaction: discord.Interaction, mandante: str, visitante: str, horario: str, estadio: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogos_geral[guild_id] = {
        "mandante": mandante, "visitante": visitante, "horario": horario, "estadio": estadio, "aberto": True, "guild_id": guild_id
    }
    salvar_dados(JOGO_ATIVO_FILE, jogos_geral)
    
    palpites_geral = carregar_dados(PALPITES_FILE)
    palpites_geral[guild_id] = {}
    salvar_dados(PALPITES_FILE, palpites_geral)

    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_avisos_id = config.get("canal_avisos")
    cargo_marcacao_id = config.get("cargo_marcacao")
    canal_comandos_id = config.get("canal_comandos")
    
    canal_cmd_mencao = f"<#{canal_comandos_id}>" if canal_comandos_id else "o canal de comandos"

    await interaction.response.send_message(f"⚽ Jogo **{mandante} x {visitante}** definido com sucesso!", ephemeral=True)

    if canal_avisos_id:
        canal_avisos = interaction.guild.get_channel(int(canal_avisos_id))
        if canal_avisos:
            texto_marcacao = f"<@&{cargo_marcacao_id}>" if cargo_marcacao_id else ""
            embed = discord.Embed(
                title="🚨 Novo Jogo Cadastrado no Bolão!",
                description=f"Partida: **{mandante} x {visitante}**\n🕒 Horário: `{horario}`\n🏟️ Estádio: `{estadio}`\n\nO bolão está aberto! Vá até {canal_cmd_mencao} e use `/palpite` para registrar sua aposta.",
                color=0x0033A0
            )
            await canal_avisos.send(content=texto_marcacao, embed=embed)

@bot.tree.command(name="proximojogo", description="Mostra os detalhes do jogo ativo.")
async def proximojogo_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo no momento.", ephemeral=True)
    
    status = "🟢 Aberto para palpites" if jogo.get("aberto", True) else "🔴 Fechado para palpites"
    embed = discord.Embed(
        title=f"⚽ Próximo Jogo: {jogo['mandante']} x {jogo['visitante']}",
        description=f"🕒 Horário: `{jogo['horario']}`\n🏟️ Estádio: `{jogo['estadio']}`\nStatus: **{status}**",
        color=0x0033A0
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fecharpalpite", description="[Admin] Fecha o recebimento de palpites.")
async def fecharpalpite_cmd(interaction: discord.Interaction):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    if guild_id not in jogos_geral:
        return await interaction.response.send_message("❌ Nenhum jogo ativo para fechar.", ephemeral=True)
    
    jogo = jogos_geral[guild_id]
    jogo["aberto"] = False
    salvar_dados(JOGO_ATIVO_FILE, jogos_geral)
    
    await interaction.response.send_message("🔒 Os palpites para este jogo foram **encerrados** com sucesso!", ephemeral=True)

    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_avisos_id = config.get("canal_avisos")
    if canal_avisos_id:
        canal_avisos = interaction.guild.get_channel(int(canal_avisos_id))
        if canal_avisos:
            embed = discord.Embed(
                title="🔒 Palpites Encerrados!",
                description=f"As apostas para o confronto **{jogo['mandante']} x {jogo['visitante']}** foram trancadas pela administração. Boa sorte a todos!",
                color=0xD32F2F
            )
            await canal_avisos.send(embed=embed)

@bot.tree.command(name="palpite", description="Abre o painel para registrar palpite.")
async def palpite_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_permitido = config.get("canal_comandos")
    if canal_permitido and str(interaction.channel_id) != canal_permitido:
        return await interaction.response.send_message(f"❌ Use este comando no canal <#{canal_permitido}>.", ephemeral=True)
    
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo no momento.", ephemeral=True)
    
    if not jogo.get("aberto", True):
        return await interaction.response.send_message("❌ Os palpites para esta partida já foram encerrados!", ephemeral=True)

    await interaction.response.send_modal(PalpiteModal(jogo))

@bot.tree.command(name="placarfinal", description="[Admin] Insere placar real e pontua.")
async def placarfinal_cmd(interaction: discord.Interaction, gols_mandante: int, gols_visitante: int, marcadores_reais: str, assistentes_reais: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo.", ephemeral=True)
    
    palpites_geral = carregar_dados(PALPITES_FILE)
    palpites = palpites_geral.get(guild_id, {})
    
    ranking_geral = carregar_dados(RANKING_FILE)
    if guild_id not in ranking_geral:
        ranking_geral[guild_id] = {}
    ranking = ranking_geral[guild_id]
    
    vencedor_real = "mandante" if gols_mandante > gols_visitante else ("visitante" if gols_visitante > gols_mandante else "empate")
    apuracao_texto = ""
    
    lista_marcadores_reais = [m.strip().lower() for m in marcadores_reais.split(',')]
    lista_assistentes_reais = [a.strip().lower() for a in assistentes_reais.split(',')]

    for uid, dados in palpites.items():
        g_m, g_v, nome = dados["g_mand"], dados["g_vis"], dados["nome"]
        marc_palpite = dados["marcador"]
        asst_palpite = dados["assistente"]
        
        vencedor_palpite = "mandante" if g_m > g_v else ("visitante" if g_v > g_m else "empate")
        
        pontos = 0
        acertos_detalhes = []
        
        if g_m == gols_mandante and g_v == gols_visitante:
            pontos += 3
            acertos_detalhes.append("🎯 Placar Exato (+3 pts)")
        elif vencedor_palpite == vencedor_real:
            pontos += 1
            acertos_detalhes.append("✅ Vencedor (+1 pt)")
        else:
            acertos_detalhes.append("❌ Errou Placar/Vencedor")

        marcadores_usuario = [m.strip().lower() for m in marc_palpite.split(',')]
        acertou_marcador = any(any(mr in mu for mr in lista_marcadores_reais) for mu in marcadores_usuario) if marc_palpite.lower() != "nenhum" else False
        if acertou_marcador:
            pontos += 2
            acertos_detalhes.append("⚽ Acertou Marcador (+2 pts)")
        else:
            acertos_detalhes.append("❌ Errou Marcador")

        assistentes_usuario = [a.strip().lower() for a in asst_palpite.split(',')]
        acertou_assistente = any(any(ar in au for ar in lista_assistentes_reais) for au in assistentes_usuario) if asst_palpite.lower() != "nenhum" else False
        if acertou_assistente:
            pontos += 1
            acertos_detalhes.append("👟 Acertou Assistente (+1 pt)")
        else:
            acertos_detalhes.append("❌ Errou Assistente")

        if uid not in ranking:
            ranking[uid] = {"nome": nome, "pontos": 0}
        ranking[uid]["pontos"] += pontos
        
        detalhes_str = " | ".join(acertos_detalhes)
        apuracao_texto += f"- <@{uid}> (`{g_m}x{g_v}`): **+{pontos} pts** ({detalhes_str})\n"

    salvar_dados(RANKING_FILE, ranking_geral)
    
    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    
    # Gerenciamento de Cargo do TOP 1
    config = carregar_dados(CONFIG_FILE).get(guild_id, {})
    cargo_top1_id = config.get("cargo_top1")
    if cargo_top1_id and ranking_ordenado:
        top1_uid = ranking_ordenado[0][0]
        cargo_top1 = interaction.guild.get_role(int(cargo_top1_id))
        if cargo_top1:
            for member in interaction.guild.members:
                if str(member.id) == top1_uid:
                    if cargo_top1 not in member.roles:
                        await member.add_roles(cargo_top1)
                else:
                    if cargo_top1 in member.roles:
                        await member.remove_roles(cargo_top1)

    texto_ranking = "".join([f"**{i}º** {inf['nome']} (`{inf['pontos']} pts`)\n" for i, (u, inf) in enumerate(ranking_ordenado, 1)])
    
    embed = discord.Embed(
        title=f"🏁 Resultado Final: {jogo['mandante']} {gols_mandante} x {gols_visitante} {jogo['visitante']}", 
        description=f"⚽ **Marcadores Oficiais:** {marcadores_reais}\n👟 **Assistentes Oficiais:** {assistentes_reais}\n\n**Apuração:**\n{apuracao_texto}\n🏆 **Ranking Geral Atualizado:**\n{texto_ranking}", 
        color=0x0033A0
    )
    
    canal_ranking_id = config.get("canal_ranking")
    if canal_ranking_id:
        canal_rank = interaction.guild.get_channel(int(canal_ranking_id))
        if canal_rank:
            await canal_rank.send(embed=embed)
            await interaction.response.send_message("✅ Placar computado e enviado para o canal de ranking!", ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(embed=embed)

    if guild_id in jogos_geral:
        del jogos_geral[guild_id]
        salvar_dados(JOGO_ATIVO_FILE, jogos_geral)

@bot.tree.command(name="ranking", description="Mostra o ranking geral.")
async def ranking_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    ranking_geral = carregar_dados(RANKING_FILE)
    ranking = ranking_geral.get(guild_id, {})
    if not ranking:
        return await interaction.response.send_message("🏆 Ranking vazio.", ephemeral=True)
    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    texto = "".join([f"**{i}º** {inf['nome']} — `{inf['pontos']} pts`\n" for i, (u, inf) in enumerate(ranking_ordenado, 1)])
    await interaction.response.send_message(embed=discord.Embed(title="🏆 Ranking Geral", description=texto, color=0x0033A0))

if __name__ == "__main__":
    bot.run(TOKEN_DO_BOT)
