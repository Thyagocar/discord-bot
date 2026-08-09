import os
import json
import threading
import discord
from discord import app_commands, ui
from discord.ext import commands
from flask import Flask, jsonify

# ================= MINI SERVIDOR WEB PARA O RENDER =================
app = Flask(__name__)

@app.route('/', methods=['GET', 'HEAD'])
def home():
    return "Bot do Discord esta ativo e rodando!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
# ===================================================================

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


# ================= CARREGAR ELENCO INICIAL DO JSON =================
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


# ================= AUTOCOMPLETAR INTELIGENTE =================

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


# ================= MODAL E VIEWS DE PALPITE =================

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

        self.add_item(self.gols_mandante)
        self.add_item(self.gols_visitante)

    async def on_submit(self, interaction: discord.Interaction):
        if not (self.gols_mandante.value.isdigit() and self.gols_visitante.value.isdigit()):
            await interaction.response.send_message("❌ Insira apenas números válidos para o placar!", ephemeral=True)
            return

        g_mand = int(self.gols_mandante.value)
        g_vis = int(self.gols_visitante.value)
        
        view = EscolhaElencoView(self.jogo, g_mand, g_vis)
        await interaction.response.send_message("⬇️ Agora selecione o **Marcador** e o **Assistente** nos menus abaixo:", view=view, ephemeral=True)


class SelectMarcador(ui.Select):
    def __init__(self, jogadores):
        options = [discord.SelectOption(label="Nenhum / Não haverá", value="Nenhum")]
        for j in jogadores[:24]:
            options.append(discord.SelectOption(label=j, value=j))
        
        super().__init__(placeholder="Selecione o Jogador Marcador (Gol)", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.marcador_escolhido = self.values[0]
        await interaction.response.defer()


class SelectAssistente(ui.Select):
    def __init__(self, jogadores):
        options = [discord.SelectOption(label="Nenhum / Sem assistência", value="Nenhum")]
        for j in jogadores[:24]:
            options.append(discord.SelectOption(label=j, value=j))
        
        super().__init__(placeholder="Selecione o Jogador Assistente (Passe)", min_values=1, max_values=1, options=options)

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
            p_antigo = palpites_servidor[user_id]
            await interaction.response.send_message(
                f"❌ Você já enviou seu palpite para este jogo e ele está trancado!\n"
                f"Seu palpite: **{self.jogo['mandante']} {p_antigo['g_mand']} x {p_antigo['g_vis']} {self.jogo['visitante']}**", 
                ephemeral=True
            )
            return

        palpites_servidor[user_id] = {
            "nome": user_name,
            "g_mand": self.g_mand,
            "g_vis": self.g_vis,
            "marcador": self.marcador_escolhido,
            "assistente": self.assistente_escolhido
        }
        salvar_dados(PALPITES_FILE, palpites_geral)

        embed = discord.Embed(
            title="🎯 Palpite Registrado com Sucesso!",
            description=f"Partida: **{self.jogo['mandante']} {self.g_mand} x {self.g_vis} {self.jogo['visitante']}**\n"
                        f"⚽ **Marcador:** {self.marcador_escolhido}\n"
                        f"👟 **Assistente:** {self.assistente_escolhido}\n\n"
                        f"🔒 Salvo e trancado com sucesso!",
            color=0x0033A0
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)


# ================= EVENTO ON_READY =================

class PainelConfigView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📋 Como Configurar o Servidor", style=discord.ButtonStyle.primary, custom_id="btn_ajuda_admin", row=0)
    async def ajuda_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🛠️ Painel de Ajuda - Administradores",
            description="Utilize os comandos de barra (`/`) para gerenciar o bolão e o elenco:\n\n"
                        "⚙️ **`/configcargo` / `/configcanal` / `/configranking`**\n"
                        "⚽ **`/adicionarjogador` / `/removerjogador`** — Gerenciam o elenco.\n"
                        "📌 **`/setarjogo`** — Define o próximo confronto.\n"
                        "🏁 **`/placarfinal`** — Apura os pontos e assistências.",
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


# ================= COMANDOS DE GERENCIAMENTO DE ELENCO =================

@bot.tree.command(name="adicionarjogador", description="[Admin] Adiciona um jogador à lista oficial do elenco.")
@app_commands.describe(nome="Nome completo ou apelido do jogador")
async def adicionarjogador_cmd(interaction: discord.Interaction, nome: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    guild_id = str(interaction.guild_id)
    elenco_geral = carregar_dados(ELENCO_FILE)
    
    if guild_id not in elenco_geral:
        elenco_geral[guild_id] = obter_elenco_servidor(guild_id)

    nome_formatado = nome.strip()
    if nome_formatado in elenco_geral[guild_id]:
        return await interaction.response.send_message(f"❌ O jogador **{nome_formatado}** já está cadastrado no elenco!", ephemeral=True)

    elenco_geral[guild_id].append(nome_formatado)
    elenco_geral[guild_id].sort()
    salvar_dados(ELENCO_FILE, elenco_geral)

    await interaction.response.send_message(f"✅ Jogador **{nome_formatado}** adicionado com sucesso ao elenco do bolão!", ephemeral=True)


@bot.tree.command(name="removerjogador", description="[Admin] Remove um jogador da lista oficial do elenco.")
@app_commands.describe(nome="Selecione o jogador para remover")
@app_commands.autocomplete(nome=autocomplete_jogadores)
async def removerjogador_cmd(interaction: discord.Interaction, nome: str):
    if not verificar_permissao_adm(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    guild_id = str(interaction.guild_id)
    elenco_geral = carregar_dados(ELENCO_FILE)
    
    if guild_id not in elenco_geral:
        elenco_geral[guild_id] = obter_elenco_servidor(guild_id)

    if nome not in elenco_geral[guild_id]:
        return await interaction.response.send_message(f"❌ Jogador não encontrado na lista.", ephemeral=True)

    elenco_geral[guild_id].remove(nome)
    salvar_dados(ELENCO_FILE, elenco_geral)

    await interaction.response.send_message(f"🗑️ Jogador **{nome}** removido do elenco com sucesso!", ephemeral=True)


# ================= OUTRAS CONFIGURAÇÕES E COMANDOS DE JOGO =================

@bot.tree.command(name="configcargo", description="[Admin] Define o cargo com permissão administrativa.")
@app_commands.describe(cargo_id="Selecione o cargo")
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
    await interaction.response.send_message(f"✅ Cargo administrativo configurado.", ephemeral=True)

@bot.tree.command(name="configcanal", description="[Admin] Define canal de comandos.")
@app_commands.describe(canal_id="Canal de palpites")
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
    await interaction.response.send_message(f"✅ Canal de palpites configurado para <#{canal_id}>.", ephemeral=True)

@bot.tree.command(name="configranking", description="[Admin] Define canal de ranking.")
@app_commands.describe(canal_id="Canal do ranking")
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
    await interaction.response.send_message(f"✅ Canal de ranking configurado para <#{canal_id}>.", ephemeral=True)

@bot.tree.command(name="setarjogo", description="[Admin] Define o próximo jogo.")
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
        "aberto": True,
        "guild_id": guild_id
    }
    salvar_dados(JOGO_ATIVO_FILE, jogos_geral)

    palpites_geral = carregar_dados(PALPITES_FILE)
    palpites_geral[guild_id] = {}
    salvar_dados(PALPITES_FILE, palpites_geral)

    await interaction.response.send_message(f"⚽ Jogo **{mandante} x {visitante}** definido com sucesso!", ephemeral=True)


@bot.tree.command(name="palpite", description="Abre o painel interativo para registrar seu palpite.")
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
        return await interaction.response.send_message("❌ Os palpites para este jogo já foram encerrados!", ephemeral=True)

    await interaction.response.send_modal(PalpiteModal(jogo))


@bot.tree.command(name="placarfinal", description="[Admin] Insere placar, marcadores, assistentes reais e pontua.")
@app_commands.describe(
    gols_mandante="Gols do mandante", 
    gols_visitante="Gols do visitante",
    marcadores_reais="Quem fez os gols (Ex: Kaio Jorge, Dinenno)",
    assistentes_reais="Quem deu as assistências (Ex: Matheus Pereira)"
)
async def placarfinal_cmd(interaction: discord.Interaction, gols_mandante: int, gols_visitante: int, marcadores_reais: str, assistentes_reais: str):
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
        asst_palpite = dados.get("assistente", "Nenhum").lower()
        
        vencedor_palpite = "mandante" if g_m > g_v else ("visitante" if g_v > g_m else "empate")
        pontos_ganhos = 0
        status_texto = "❌ Errou"
        
        if g_m == gols_mandante and g_v == gols_visitante:
            pontos_ganhos = 3
            status_texto = "🎯 Placar Exato! (+3 pts)"
        elif vencedor_palpite == vencedor_real:
            pontos_ganhos = 1
            status_texto = "✅ Acertou Vencedor! (+1 pt)"

        if any(m.strip().lower() in marc_palpite for m in marcadores_reais.lower().split(',')) and marc_palpite != "nenhum":
            pontos_ganhos += 2
            status_texto += " + ⚽ Marcador (+2 pts)"

        if any(a.strip().lower() in asst_palpite for a in assistentes_reais.lower().split(',')) and asst_palpite != "nenhum":
            pontos_ganhos += 1
            status_texto += " + 👟 Assistência (+1 pt)"

        if uid not in ranking:
            ranking[uid] = {"nome": nome, "pontos": 0}
        
        ranking[uid]["pontos"] += pontos_ganhos
        resultados_parciais += f"- <@{uid}> ({g_m}x{g_v}) — **{status_texto}** (`{pontos_ganhos} pts`)\n"

    salvar_dados(RANKING_FILE, ranking_geral)

    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1]["pontos"], reverse=True)
    texto_ranking = ""
    for idx, (uid, info) in enumerate(ranking_ordenado, start=1):
        texto_ranking += f"**{idx}º** — {info['nome']} (`{info['pontos']} pts`)\n"

    embed = discord.Embed(
        title=f"🏁 Resultado Final: {jogo['mandante']} {gols_mandante} x {gols_visitante} {jogo['visitante']}",
        description=f"⚽ **Marcadores:** {marcadores_reais}\n👟 **Assistentes:** {assistentes_reais}\n\n"
                    f"**Apuração:**\n{resultados_parciais}\n\n"
                    f"🏆 **Ranking Atualizado:**\n{texto_ranking}",
        color=0x0033A0
    )

    config_geral = carregar_dados(CONFIG_FILE)
    config = config_geral.get(guild_id, {})
    canal_ranking_id = config.get("canal_ranking")
    
    if canal_ranking_id:
        canal_rank = interaction.guild.get_channel(int(canal_ranking_id))
        if canal_rank:
            await canal_rank.send(embed=embed)
            await interaction.response.send_message(f"✅ Apurado e enviado para {canal_rank.mention}.", ephemeral=True)
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


if __name__ == "__main__":
    # Inicia o servidor Flask em thread secundária daemon
    threading.Thread(target=run_flask, daemon=True).start()
    # Inicia o bot no processo principal
    bot.run(TOKEN_DO_BOT)
