import os
import json
import discord
from discord import app_commands, ui
from discord.ext import commands

# Token puxado de forma segura pelas variáveis de ambiente da Discloud
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
    jogadores = obter_elenco_servidor(guild_id)
    return [
        app_commands.Choice(name=jogador, value=jogador)
        for jogador in jogadores if current.lower() in jogador.lower()
    ][:25]

class PalpiteModal(ui.Modal):
    def __init__(self, jogo):
        mandante = jogo["mandante"]
        visitante = jogo["visitante"]
        super().__init__(title=f"Palpite: {mandante} x {visitante}")
        self.jogo = jogo
        self.gols_mandante = ui.TextInput(label=f"Gols do {mandante}", placeholder="Ex: 2", min_length=1, max_length=2, required=True)
        self.gols_visitante = ui.TextInput(label=f"Gols do {visitante}", placeholder="Ex: 1", min_length=1, max_length=2, required=True)
        self.add_item(self.gols_mandante)
        self.add_item(self.gols_visitante)

    async def on_submit(self, interaction: discord.Interaction):
        if not (self.gols_mandante.value.isdigit() and self.gols_visitante.value.isdigit()):
            await interaction.response.send_message("❌ Insira apenas números válidos para o placar!", ephemeral=True)
            return
        g_mand = int(self.gols_mandante.value)
        g_vis = int(self.gols_visitante.value)
        view = EscolhaElencoView(self.jogo, g_mand, g_vis)
        await interaction.response.send_message("⬇️ Selecione o **Marcador** e o **Assistente** abaixo:", view=view, ephemeral=True)

class SelectMarcador(ui.Select):
    def __init__(self, jogadores):
        options = [discord.SelectOption(label="Nenhum / Não haverá", value="Nenhum")]
        for j in jogadores[:24]:
            options.append(discord.SelectOption(label=j, value=j))
        super().__init__(placeholder="Selecione o Marcador (Gol)", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.marcador_escolhido = self.values[0]
        await interaction.response.defer()

class SelectAssistente(ui.Select):
    def __init__(self, jogadores):
        options = [discord.SelectOption(label="Nenhum / Sem assistência", value="Nenhum")]
        for j in jogadores[:24]:
            options.append(discord.SelectOption(label=j, value=j))
        super().__init__(placeholder="Selecione o Assistente (Passe)", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.assistente_escolhido = self.values[0]
        await interaction.response.defer()

class EscolhaElencoView(ui.View):
    def __init__(self, jogo, g_mand, g_vis):
        super().__init__(timeout=180)
        self.jogo = jogo
        self.g_mand = g_mand
        self.g_vis = g_vis
        self.marcador_escolhido = "Nenhum"
        self.assistente_escolhido = "Nenhum"
        guild_id = str(jogo.get("guild_id"))
        jogadores = obter_elenco_servidor(guild_id)
        if not jogadores:
            jogadores = ["Nenhum jogador cadastrado"]
        self.add_item(SelectMarcador(jogadores))
        self.add_item(SelectAssistente(jogadores))

    @ui.button(label="Confirmar Palpite Completo", style=discord.ButtonStyle.green, row=2)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        palpites_geral = carregar_dados(PALPITES_FILE)
        if guild_id not in palpites_geral:
            palpites_geral[guild_id] = {}
        palpites_servidor = palpites_geral[guild_id]
        if user_id in palpites_servidor:
            await interaction.response.send_message(f"❌ Você já enviou seu palpite!", ephemeral=True)
            return
        palpites_servidor[user_id] = {
            "nome": user_name,
            "g_mand": self.g_mand,
            "g_vis": self.g_vis,
            "marcador": self.marcador_escolhido,
            "assistente": self.assistente_escolhido
        }
        salvar_dados(PALPITES_FILE, palpites_geral)
        embed = discord.Embed(title="🎯 Palpite Registrado!", description=f"Partida: **{self.jogo['mandante']} {self.g_mand} x {self.g_vis} {self.jogo['visitante']}**\n⚽ **Marcador:** {self.marcador_escolhido}\n👟 **Assistente:** {self.assistente_escolhido}", color=0x0033A0)
        await interaction.response.edit_message(content=None, embed=embed, view=None)

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"🤖 Bot conectado como: {bot.user.name}")
        print(f"⚙️ Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

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

@bot.tree.command(name="configcargo", description="[Admin] Define cargo administrativo.")
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
    await interaction.response.send_message(f"✅ Cargo configurado.", ephemeral=True)

@bot.tree.command(name="configcanal", description="[Admin] Define canal de palpites.")
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
    await interaction.response.send_message(f"✅ Canal configurado para <#{canal_id}>.", ephemeral=True)

@bot.tree.command(name="configranking", description="[Admin] Define canal de ranking.")
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
    await interaction.response.send_message(f"✅ Canal de ranking configurado.", ephemeral=True)

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
    await interaction.response.send_message(f"⚽ Jogo **{mandante} x {visitante}** definido!", ephemeral=True)

@bot.tree.command(name="palpite", description="Abre o painel para registrar palpite.")
async def palpite_cmd(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_permitido = config.get("canal_comandos")
    if canal_permitido and str(interaction.channel_id) != canal_permitido:
        return await interaction.response.send_message(f"❌ Use no canal <#{canal_permitido}>.", ephemeral=True)
    jogos_geral = carregar_dados(JOGO_ATIVO_FILE)
    jogo = jogos_geral.get(guild_id)
    if not jogo:
        return await interaction.response.send_message("❌ Nenhum jogo ativo.", ephemeral=True)
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
    resultados_parciais = ""
    for uid, dados in palpites.items():
        g_m, g_v, nome = dados["g_mand"], dados["g_vis"], dados["nome"]
        marc_palpite, asst_palpite = dados["marcador"].lower(), dados.get("assistente", "Nenhum").lower()
        vencedor_palpite = "mandante" if g_m > g_v else ("visitante" if g_v > g_m else "empate")
        pontos = 0
        status = "❌ Errou"
        if g_m == gols_mandante and g_v == gols_visitante:
            pontos = 3
            status = "🎯 Placar Exato (+3)"
        elif vencedor_palpite == vencedor_real:
            pontos = 1
            status = "✅ Vencedor (+1)"
        if any(m.strip().lower() in marc_palpite for m in marcadores_reais.lower().split(',')) and marc_palpite != "nenhum":
            pontos += 2
            status += " + Marcador"
        if any(a.strip().lower() in asst_palpite for a in assistentes_reais.lower().split(',')) and asst_palpite != "nenhum":
            pontos += 1
            status += " + Assistência"
        if uid not in ranking:
            ranking[uid] = {"nome": nome, "pontos": 0}
        ranking[uid]["pontos"] += pontos
        resultados_parciais += f"- <@{uid}> (`{pontos} pts`)\n"
    salvar_dados(RANKING_FILE, ranking_geral)
    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    texto_ranking = "".join([f"**{i}º** {inf['nome']} (`{inf['pontos']} pts`)\n" for i, (u, inf) in enumerate(ranking_ordenado, 1)])
    embed = discord.Embed(title=f"🏁 Resultado: {jogo['mandante']} {gols_mandante} x {gols_visitante} {jogo['visitante']}", description=f"{resultados_parciais}\n🏆 **Ranking:**\n{texto_ranking}", color=0x0033A0)
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
