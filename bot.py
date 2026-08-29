import os
import json
import asyncio
import unicodedata
from typing import Dict, Any, Optional
import discord
from discord import app_commands, ui
from discord.ext import commands

TOKEN_DO_BOT = os.getenv("DISCORD_TOKEN")

CONFIG_FILE = "config.json"
PALPITES_FILE = "palpites.json"
RANKING_FILE = "ranking.json"
JOGO_ATIVO_FILE = "jogo_ativo.json"
HISTORICO_FILE = "historico_palpites.json"

file_lock = asyncio.Lock()

# Cache em memória para evitar leituras de disco repetitivas
CACHE: Dict[str, Dict[str, Any]] = {
    CONFIG_FILE: {},
    PALPITES_FILE: {},
    RANKING_FILE: {},
    JOGO_ATIVO_FILE: {},
    HISTORICO_FILE: {}
}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- GERENCIAMENTO DE DADOS (CACHE + PERSISTÊNCIA SEGURA) ---

def normalizar_texto(texto: str) -> str:
    """Remove acentos e converte para minúsculas."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    ).lower().strip()

def carregar_dados_disco(arquivo: str) -> Dict[str, Any]:
    if os.path.exists(arquivo):
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def salvar_dados_disco_atomico(arquivo: str, dados: Dict[str, Any]) -> None:
    """Escreve dados em um arquivo temporário antes de substituir o original para evitar corrupção."""
    temp_file = f"{arquivo}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        os.replace(temp_file, arquivo)
    except OSError as e:
        print(f"Erro crítico ao salvar arquivo {arquivo}: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

async def obter_dados(arquivo: str) -> Dict[str, Any]:
    """Retorna os dados salvos em cache."""
    return CACHE.get(arquivo, {})

async def atualizar_dados(arquivo: str, novos_dados: Dict[str, Any]) -> None:
    """Atualiza o cache e grava no disco de forma assíncrona e atômica."""
    async with file_lock:
        CACHE[arquivo] = novos_dados
        await asyncio.to_thread(salvar_dados_disco_atomico, arquivo, novos_dados)

def inicializar_cache():
    for arq in CACHE.keys():
        CACHE[arq] = carregar_dados_disco(arq)

# --- FUNÇÃO DE VALIDAÇÃO DE PERMISSÃO ---

def verificar_permissao_adm(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild:
        return True
    
    guild_id = str(interaction.guild_id)
    config_geral = CACHE.get(CONFIG_FILE, {})
    config_servidor = config_geral.get(guild_id, {})
    cargos_permitidos = config_servidor.get("cargos_adm", [])
    
    return any(str(role.id) in cargos_permitidos for role in interaction.user.roles)

# --- PAINEL E MENUS DE CONFIGURAÇÃO ---

class SetupSelectBase(ui.ChannelSelect):
    def __init__(self, custom_id: str, placeholder: str, config_key: str, row: int):
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            channel_types=[discord.ChannelType.text],
            min_values=1, max_values=1, row=row
        )
        self.config_key = config_key

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        config_geral = await obter_dados(CONFIG_FILE)
        
        if guild_id not in config_geral:
            config_geral[guild_id] = {}
            
        config_geral[guild_id][self.config_key] = str(self.values[0].id)
        await atualizar_dados(CONFIG_FILE, config_geral)
        await interaction.response.send_message(f"✅ Configuração atualizada: {self.values[0].mention}!", ephemeral=True)

class SetupSelectRoleBase(ui.RoleSelect):
    def __init__(self, custom_id: str, placeholder: str, config_key: str, is_list: bool, row: int):
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=1, max_values=1, row=row
        )
        self.config_key = config_key
        self.is_list = is_list

    async def callback(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        config_geral = await obter_dados(CONFIG_FILE)
        
        if guild_id not in config_geral:
            config_geral[guild_id] = {}
            
        valor = [str(self.values[0].id)] if self.is_list else str(self.values[0].id)
        config_geral[guild_id][self.config_key] = valor
        
        await atualizar_dados(CONFIG_FILE, config_geral)
        await interaction.response.send_message(f"✅ Cargo configurado: {self.values[0].mention}!", ephemeral=True)

class SetupView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SetupSelectBase("setup_select_canal_ranking", "Selecione o canal do Ranking", "canal_ranking", 0))
        self.add_item(SetupSelectBase("setup_select_canal_comandos", "Selecione o canal para /palpite", "canal_comandos", 1))
        self.add_item(SetupSelectBase("setup_select_canal_avisos", "Selecione o canal de Avisos de Jogos", "canal_avisos", 2))
        self.add_item(SetupSelectRoleBase("setup_select_cargo_marcacao", "Selecione o Cargo para marcar nos avisos", "cargo_marcacao", False, 3))
        self.add_item(SetupSelectRoleBase("setup_select_cargo_adm", "Selecione o Cargo de ADM do Bot", "cargos_adm", True, 4))

# --- MODAL DE PALPITES ---

class PalpiteModal(ui.Modal):
    def __init__(self, jogo: dict, palpite_existente: Optional[dict] = None):
        mandante, visitante = jogo["mandante"], jogo["visitante"]
        super().__init__(title=f"Palpite: {mandante} x {visitante}")
        self.jogo = jogo

        g_m_default = str(palpite_existente["g_mand"]) if palpite_existente else ""
        g_v_default = str(palpite_existente["g_vis"]) if palpite_existente else ""
        marc_default = palpite_existente.get("marcador", "") if palpite_existente else ""
        asst_default = palpite_existente.get("assistente", "") if palpite_existente else ""

        self.gols_mandante = ui.TextInput(label=f"Gols do {mandante}", default=g_m_default, placeholder="Ex: 2", min_length=1, max_length=2, required=True)
        self.gols_visitante = ui.TextInput(label=f"Gols do {visitante}", default=g_v_default, placeholder="Ex: 1", min_length=1, max_length=2, required=True)
        self.marcadores = ui.TextInput(label="Marcador(es) do Gol", default=marc_default, placeholder="Ex: Jogador A (ou Nenhum)", required=True)
        self.assistentes = ui.TextInput(label="Assistente(s) do Gol", default=asst_default, placeholder="Ex: Jogador C (ou Nenhum)", required=True)
        
        self.add_item(self.gols_mandante)
        self.add_item(self.gols_visitante)
        self.add_item(self.marcadores)
        self.add_item(self.assistentes)

    async def on_submit(self, interaction: discord.Interaction):
        if not (self.gols_mandante.value.isdigit() and self.gols_visitante.value.isdigit()):
            return await interaction.response.send_message("❌ Insira apenas números inteiros válidos nos placares!", ephemeral=True)
        
        g_mand = int(self.gols_mandante.value)
        g_vis = int(self.gols_visitante.value)
        marc = self.marcadores.value.strip()
        asst = self.assistentes.value.strip()

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        
        palpites_geral = await obter_dados(PALPITES_FILE)
        if guild_id not in palpites_geral:
            palpites_geral[guild_id] = {}
        
        editando = user_id in palpites_geral[guild_id]

        palpites_geral[guild_id][user_id] = {
            "nome": interaction.user.display_name,
            "g_mand": g_mand,
            "g_vis": g_vis,
            "marcador": marc,
            "assistente": asst
        }
        await atualizar_dados(PALPITES_FILE, palpites_geral)

        status_msg = "✏️ Palpite Atualizado!" if editando else "🎯 Palpite Registrado!"
        embed = discord.Embed(
            title=status_msg,
            description=f"Partida: **{self.jogo['mandante']} {g_mand} x {g_vis} {self.jogo['visitante']}**\n⚽ **Marcador(es):** {marc}\n👟 **Assistente(s):** {asst}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- EVENTOS ---

@bot.event
async def on_ready():
    inicializar_cache()
    bot.add_view(SetupView())
    print(f"🤖 Bot online como {bot.user.name} | Cache Carregado.")

# --- COMANDOS COM PREFIXO (ADMIN) ---

@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync_comandos(ctx: commands.Context, guild_only: bool = False):
    msg = await ctx.send("🔄 Sincronizando comandos slash...")
    try:
        if guild_only:
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
            await msg.edit(content=f"✅ **{len(synced)}** comandos sincronizados para este servidor.")
        else:
            synced = await bot.tree.sync()
            await msg.edit(content=f"✅ **{len(synced)}** comandos sincronizados globalmente.")
    except Exception as e:
        await msg.edit(content=f"❌ Erro ao sincronizar: `{e}`")

# --- COMANDOS SLASH ---

@bot.tree.command(name="setup", description="[Admin] Cria o painel de configuração privado.")
async def setup_cmd(interaction: discord.Interaction):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    try:
        canal = await guild.create_text_channel("config-bot-palpites", overwrites=overwrites)
        embed = discord.Embed(
            title="⚙️ Painel de Configuração",
            description="Defina abaixo as configurações do bot:",
            color=discord.Color.blue()
        )
        await canal.send(embed=embed, view=SetupView())
        await interaction.followup.send(f"✅ Canal criado: {canal.mention}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao criar canal: `{e}`", ephemeral=True)

@bot.tree.command(name="setarjogo", description="[Admin] Define a próxima partida.")
async def setarjogo_cmd(interaction: discord.Interaction, mandante: str, visitante: str, horario: str, estadio: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    
    jogos_geral = await obter_dados(JOGO_ATIVO_FILE)
    jogos_geral[guild_id] = {
        "mandante": mandante, "visitante": visitante, "horario": horario, "estadio": estadio, "aberto": True
    }
    await atualizar_dados(JOGO_ATIVO_FILE, jogos_geral)
    
    # Reseta apenas os palpites ativos do servidor atual
    palpites_geral = await obter_dados(PALPITES_FILE)
    palpites_geral[guild_id] = {}
    await atualizar_dados(PALPITES_FILE, palpites_geral)

    config_geral = await obter_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_avisos_id = config.get("canal_avisos")
    cargo_marcacao_id = config.get("cargo_marcacao")
    canal_comandos_id = config.get("canal_comandos")
    
    canal_mencao = f"<#{canal_comandos_id}>" if canal_comandos_id else "o canal de comandos"
    await interaction.response.send_message(f"⚽ Jogo **{mandante} x {visitante}** configurado!", ephemeral=True)

    if canal_avisos_id:
        canal_avisos = interaction.guild.get_channel(int(canal_avisos_id))
        if canal_avisos:
            texto_marcacao = f"<@&{cargo_marcacao_id}>" if cargo_marcacao_id else ""
            embed = discord.Embed(
                title="🚨 Novo Jogo Cadastrado!",
                description=f"Partida: **{mandante} x {visitante}**\n🕒 Horário: `{horario}`\n🏟️ Estádio: `{estadio}`\n\nUse `/palpite` em {canal_mencao} para dar o seu palpite.",
                color=discord.Color.blue()
            )
            await canal_avisos.send(content=texto_marcacao, embed=embed)

@bot.tree.command(name="proximojogo", description="Mostra detalhes da partida ativa.")
async def proximojogo_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    jogos_geral = await obter_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo no momento.", ephemeral=True)
    
    status = "🟢 Palpites Abertos" if jogo.get("aberto", True) else "🔴 Palpites Encerrados"
    embed = discord.Embed(
        title=f"⚽ Próxima Partida: {jogo['mandante']} x {jogo['visitante']}",
        description=f"🕒 Horário: `{jogo['horario']}`\n🏟️ Estádio: `{jogo['estadio']}`\nStatus: **{status}**",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fecharpalpite", description="[Admin] Encerra o recebimento de palpites.")
async def fecharpalpite_cmd(interaction: discord.Interaction):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    guild_id = str(interaction.guild_id)
    jogos_geral = await obter_dados(JOGO_ATIVO_FILE)
    
    if guild_id not in jogos_geral:
        return await interaction.response.send_message("❌ Nenhum jogo ativo encontrado.", ephemeral=True)
    
    jogos_geral[guild_id]["aberto"] = False
    await atualizar_dados(JOGO_ATIVO_FILE, jogos_geral)
    await interaction.response.send_message("🔒 Palpites encerrados com sucesso!", ephemeral=True)

@bot.tree.command(name="palpite", description="Registra ou altera o seu palpite.")
async def palpite_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    config_geral = await obter_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_permitido = config.get("canal_comandos")
    
    if canal_permitido and str(interaction.channel_id) != canal_permitido:
        return await interaction.response.send_message(f"❌ Utilize o comando no canal <#{canal_permitido}>.", ephemeral=True)
    
    jogos_geral = await obter_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo.", ephemeral=True)
    if not jogo.get("aberto", True):
        return await interaction.response.send_message("❌ Os palpites estão encerrados!", ephemeral=True)

    palpites_geral = await obter_dados(PALPITES_FILE)
    palpite_existente = palpites_geral.get(guild_id, {}).get(str(interaction.user.id))

    await interaction.response.send_modal(PalpiteModal(jogo, palpite_existente))

@bot.tree.command(name="cancelarpalpite", description="Cancela seu palpite ativo.")
async def cancelarpalpite_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)

    jogos_geral = await obter_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo or not jogo.get("aberto", True):
        return await interaction.response.send_message("❌ Não há apostas abertas para cancelar.", ephemeral=True)

    palpites_geral = await obter_dados(PALPITES_FILE)
    if guild_id not in palpites_geral or user_id not in palpites_geral[guild_id]:
        return await interaction.response.send_message("❌ Você não possui palpite cadastrado.", ephemeral=True)

    del palpites_geral[guild_id][user_id]
    await atualizar_dados(PALPITES_FILE, palpites_geral)
    await interaction.response.send_message("🗑️ Palpite removido com sucesso!", ephemeral=True)

@bot.tree.command(name="meuspalpites", description="Exibe o seu histórico de palpites.")
async def meuspalpites_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild_id, user_id = str(interaction.guild_id), str(interaction.user.id)

    historico_geral = await obter_dados(HISTORICO_FILE)
    historico_servidor = historico_geral.get(guild_id, [])

    palpites_usuario = []
    total_pontos = 0
    jogos_participados = 0
    placar_exato_cnt = 0
    vencedor_cnt = 0

    for partida in reversed(historico_servidor):
        if user_id in partida.get("palpites", {}):
            p = partida["palpites"][user_id]
            jogos_participados += 1
            pts = p.get("pontos_ganhos", 0)
            total_pontos += pts

            detalhes = p.get("detalhes", [])
            if any("Placar Exato" in d for d in detalhes):
                placar_exato_cnt += 1
            elif any("Vencedor" in d for d in detalhes):
                vencedor_cnt += 1

            if len(palpites_usuario) < 5:
                palpites_usuario.append(
                    f"• **{partida['partida']}** (`{partida['placar_real']}`)\n"
                    f"  Palpite: `{p['g_mand']}x{p['g_vis']}` | **+{pts} pts**"
                )

    palpites_geral = await obter_dados(PALPITES_FILE)
    palpite_atual = palpites_geral.get(guild_id, {}).get(user_id)
    info_atual = ""
    if palpite_atual:
        jogos_geral = await obter_dados(JOGO_ATIVO_FILE)
        j_atual = jogos_geral.get(guild_id)
        if j_atual:
            info_atual = f"\n\n📌 **Palpite Ativo ({j_atual['mandante']} x {j_atual['visitante']}):**\n`{palpite_atual['g_mand']}x{palpite_atual['g_vis']}` | Marcador: {palpite_atual['marcador']}"

    if jogos_participados == 0 and not palpite_atual:
        return await interaction.followup.send("❌ Você não possui nenhum histórico registrado.", ephemeral=True)

    taxa_vencedor = (vencedor_cnt / jogos_participados) * 100 if jogos_participados else 0
    taxa_placar = (placar_exato_cnt / jogos_participados) * 100 if jogos_participados else 0

    embed = discord.Embed(title=f"📊 Retrospecto de {interaction.user.display_name}", color=discord.Color.blue())
    embed.add_field(name="📈 Pontuação e Jogos", value=f"• Pontos no Histórico: **{total_pontos} pts**\n• Partidas: **{jogos_participados}**", inline=False)
    
    if jogos_participados > 0:
        embed.add_field(name="🎯 Taxa de Acertos", value=f"• Placar Exato: **{taxa_placar:.1f}%** ({placar_exato_cnt})\n• Vencedor/Empate: **{taxa_vencedor:.1f}%** ({vencedor_cnt})", inline=False)
    
    texto_historico = "\n".join(palpites_usuario) if palpites_usuario else "Nenhuma partida finalizada."
    embed.add_field(name="📜 Últimos Palpites", value=texto_historico + info_atual, inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="registro", description="Estatísticas gerais das partidas do servidor.")
async def registro_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_id = str(interaction.guild_id)

    jogos_geral = await obter_dados(JOGO_ATIVO_FILE)
    palpites_geral = await obter_dados(PALPITES_FILE)
    jogo_atual = jogos_geral.get(guild_id)
    
    palpites_jogo_atual = palpites_geral.get(guild_id, {})
    qtd_palpites_atual = len(palpites_jogo_atual)

    historico_geral = await obter_dados(HISTORICO_FILE)
    historico_servidor = historico_geral.get(guild_id, [])
    ranking_geral = await obter_dados(RANKING_FILE)
    ranking = ranking_geral.get(guild_id, {})

    contagem_usuarios = {}
    for partida in historico_servidor:
        for uid in partida.get("palpites", {}).keys():
            contagem_usuarios[uid] = contagem_usuarios.get(uid, 0) + 1

    usuarios_ordenados = sorted(contagem_usuarios.items(), key=lambda x: x[1], reverse=True)[:10]
    linhas_usuarios = [f"`#{i+1:02d}` <@{u_id}> — **{qtd}** partida(s)" for i, (u_id, qtd) in enumerate(usuarios_ordenados)]
    texto_usuarios = "\n".join(linhas_usuarios) if linhas_usuarios else "Nenhum histórico disponível."

    embed = discord.Embed(title="📊 Registros Gerais do Bolão", color=discord.Color.blue())
    info_jogo = f"Partida: **{jogo_atual['mandante']} x {jogo_atual['visitante']}**\nPalpites nesta partida: **{qtd_palpites_atual}**" if jogo_atual else "Nenhum jogo ativo."
    
    embed.add_field(name="⚽ Partida Atual", value=info_jogo, inline=False)
    embed.add_field(name="📈 Histórico do Servidor", value=f"• Partidas Encerradas: **{len(historico_servidor)}**", inline=False)
    embed.add_field(name="🏆 Assiduidade (Top 10)", value=texto_usuarios, inline=False)
    embed.set_footer(text=f"Total de participantes registrados: {len(ranking)}")

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="placarfinal", description="[Admin] Lança o placar real e calcula as pontuações.")
async def placarfinal_cmd(interaction: discord.Interaction, gols_mandante: int, gols_visitante: int, marcadores_reais: str, assistentes_reais: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    await interaction.response.defer()
    guild_id = str(interaction.guild_id)

    jogos_geral = await obter_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo:
        return await interaction.followup.send("❌ Nenhum jogo ativo registrado.")
    
    palpites_geral = await obter_dados(PALPITES_FILE)
    palpites = palpites_geral.get(guild_id, {})

    ranking_geral = await obter_dados(RANKING_FILE)
    if guild_id not in ranking_geral:
        ranking_geral[guild_id] = {}
    ranking = ranking_geral[guild_id]
    
    vencedor_real = "mandante" if gols_mandante > gols_visitante else ("visitante" if gols_visitante > gols_mandante else "empate")
    
    # Processa strings normalizadas
    lista_marcadores_reais = [normalizar_texto(m) for m in marcadores_reais.split(',') if m.strip()]
    lista_assistentes_reais = [normalizar_texto(a) for a in assistentes_reais.split(',') if a.strip()]

    apuracao_linhas = []
    registro_partida = {
        "partida": f"{jogo['mandante']} x {jogo['visitante']}",
        "placar_real": f"{gols_mandante}x{gols_visitante}",
        "palpites": {}
    }

    for uid, dados in palpites.items():
        g_m, g_v, nome = dados["g_mand"], dados["g_vis"], dados["nome"]
        marc_palpite = normalizar_texto(dados.get("marcador", ""))
        asst_palpite = normalizar_texto(dados.get("assistente", ""))
        
        vencedor_palpite = "mandante" if g_m > g_v else ("visitante" if g_v > g_m else "empate")
        
        pontos = 0
        acertos_detalhes = []
        
        # Regras de Pontuação do Placar
        if g_m == gols_mandante and g_v == gols_visitante:
            pontos += 3
            acertos_detalhes.append("🎯 Placar Exato (+3 pts)")
        elif vencedor_palpite == vencedor_real:
            pontos += 1
            acertos_detalhes.append("✅ Vencedor (+1 pt)")
        else:
            acertos_detalhes.append("❌ Errou Placar")

        # Regras para Marcadores
        if marc_palpite and marc_palpite != "nenhum":
            marcadores_usuario = [m.strip() for m in marc_palpite.split(',') if m.strip()]
            if any(mr in mu for mr in lista_marcadores_reais for mu in marcadores_usuario if mu):
                pontos += 2
                acertos_detalhes.append("⚽ Marcador (+2 pts)")

        # Regras para Assistentes
        if asst_palpite and asst_palpite != "nenhum":
            assistentes_usuario = [a.strip() for a in asst_palpite.split(',') if a.strip()]
            if any(ar in au for ar in lista_assistentes_reais for au in assistentes_usuario if au):
                pontos += 1
                acertos_detalhes.append("👟 Assistente (+1 pt)")

        if uid not in ranking:
            ranking[uid] = {"nome": nome, "pontos": 0}
        ranking[uid]["pontos"] += pontos
        ranking[uid]["nome"] = nome # Atualiza nome caso tenha mudado
        
        detalhes_str = " | ".join(acertos_detalhes)
        apuracao_linhas.append(f"• <@{uid}> (`{g_m}x{g_v}`): **+{pontos} pts** ({detalhes_str})")

        registro_partida["palpites"][uid] = {
            "g_mand": g_m, "g_vis": g_v, "pontos_ganhos": pontos, "detalhes": acertos_detalhes
        }

    # Salva Histórico
    historico_geral = await obter_dados(HISTORICO_FILE)
    if guild_id not in historico_geral:
        historico_geral[guild_id] = []
    historico_geral[guild_id].append(registro_partida)
    
    await atualizar_dados(HISTORICO_FILE, historico_geral)
    await atualizar_dados(RANKING_FILE, ranking_geral)
    
    # Limpa estados ativos
    palpites_geral[guild_id] = {}
    await atualizar_dados(PALPITES_FILE, palpites_geral)
    
    if guild_id in jogos_geral:
        del jogos_geral[guild_id]
        await atualizar_dados(JOGO_ATIVO_FILE, jogos_geral)

    # Monta e Envia o Resultado
    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    texto_ranking = "".join([f"**{i}º** {inf['nome']} — `{inf['pontos']} pts`\n" for i, (u, inf) in enumerate(ranking_ordenado[:15], 1)])
    texto_apuracao = "\n".join(apuracao_linhas) if apuracao_linhas else "Nenhum palpite foi feito nesta partida."

    embed = discord.Embed(
        title=f"🏁 Placar Final: {jogo['mandante']} {gols_mandante} x {gols_visitante} {jogo['visitante']}",
        description=f"⚽ **Marcadores:** {marcadores_reais}\n👟 **Assistentes:** {assistentes_reais}\n\n**Apuração:**\n{texto_apuracao}\n\n🏆 **Top Ranking Geral:**\n{texto_ranking}",
        color=discord.Color.blue()
    )

    config_geral = await obter_dados(CONFIG_FILE)
    canal_ranking_id = config_geral.get(guild_id, {}).get("canal_ranking")
    
    if canal_ranking_id and (canal_rank := interaction.guild.get_channel(int(canal_ranking_id))):
        await canal_rank.send(embed=embed)
        await interaction.followup.send("✅ Placar computado e publicado no canal do ranking!")
    else:
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="ranking", description="Exibe a tabela do ranking geral.")
async def ranking_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    ranking_geral = await obter_dados(RANKING_FILE)
    ranking = ranking_geral.get(guild_id, {})
    
    if not ranking:
        return await interaction.response.send_message("🏆 Ranking sem participantes no momento.", ephemeral=True)
        
    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    texto = "".join([f"**{i}º** {inf['nome']} — `{inf['pontos']} pts`\n" for i, (u, inf) in enumerate(ranking_ordenado[:25], 1)])
    
    await interaction.response.send_message(embed=discord.Embed(title="🏆 Ranking Geral", description=texto, color=discord.Color.blue()))

# --- EXECUÇÃO ---

if __name__ == "__main__":
    if TOKEN_DO_BOT:
        bot.run(TOKEN_DO_BOT)
    else:
        print("❌ ERRO: A variável de ambiente DISCORD_TOKEN não foi configurada.")
