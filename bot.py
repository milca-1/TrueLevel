import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
from datetime import datetime, timedelta

import os
TOKEN = os.environ.get("DISCORD_TOKEN")
LOG_CHANNEL_NAME = "logs-xp"
MJ_ROLE_NAME = "MJ"

MOB_XP = {
    1: 1000, 2: 800, 3: 650, 4: 500, 5: 380,
    6: 280,  7: 200, 8: 130, 9:  80, 10:  50
}

BOSS_XP = {
    1: 3000, 2: 2500, 3: 2000, 4: 1600, 5: 1200,
    6:  900, 7:  650, 8:  450, 9:  300, 10: 200
}

TRAINING_FIXED_XP   = 75
TRAINING_LUCKY_MIN  = 50
TRAINING_LUCKY_MAX  = 200
TRAINING_WEEKLY_MAX = 3
MAX_LEVEL = 100

def xp_needed_for_level(level):
    if level <= 1:
        return 0
    total = 0
    for lvl in range(2, level + 1):
        if lvl <= 10:
            total += 200
        elif lvl <= 25:
            total += 500
        elif lvl <= 50:
            total += 1000
        elif lvl <= 75:
            total += 2000
        else:
            total += 4000
    return total

def init_db():
    conn = sqlite3.connect("rpg.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            discord_id   INTEGER PRIMARY KEY,
            nom_perso    TEXT    DEFAULT 'Inconnu',
            classe       TEXT    DEFAULT 'Aventurier',
            xp           INTEGER DEFAULT 0,
            niveau       INTEGER DEFAULT 1,
            trainings_this_week INTEGER DEFAULT 0,
            week_start   TEXT    DEFAULT ''
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS xp_logs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            montant   INTEGER,
            source    TEXT,
            detail    TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_player(discord_id):
    conn = sqlite3.connect("rpg.db")
    c = conn.cursor()
    c.execute("SELECT * FROM players WHERE discord_id = ?", (discord_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    keys = ["discord_id","nom_perso","classe","xp","niveau","trainings_this_week","week_start"]
    return dict(zip(keys, row))

def create_player(discord_id, nom, classe):
    conn = sqlite3.connect("rpg.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO players (discord_id, nom_perso, classe) VALUES (?,?,?)", (discord_id, nom, classe))
    conn.commit()
    conn.close()

def add_xp(discord_id, montant, source, detail):
    conn = sqlite3.connect("rpg.db")
    c = conn.cursor()
    c.execute("SELECT xp, niveau FROM players WHERE discord_id = ?", (discord_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return {"error": "Joueur introuvable"}
    old_xp, old_level = row
    new_xp = old_xp + montant
    new_level = old_level
    leveled_up = False
    while new_level < MAX_LEVEL and new_xp >= xp_needed_for_level(new_level + 1):
        new_level += 1
        leveled_up = True
    c.execute("UPDATE players SET xp = ?, niveau = ? WHERE discord_id = ?", (new_xp, new_level, discord_id))
    c.execute("INSERT INTO xp_logs (discord_id, montant, source, detail, timestamp) VALUES (?,?,?,?,?)", (discord_id, montant, source, detail, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"old_xp": old_xp, "new_xp": new_xp, "old_level": old_level, "new_level": new_level, "leveled_up": leveled_up, "montant": montant}

def get_week_start():
    today = datetime.utcnow()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%W")

def check_and_reset_trainings(discord_id):
    conn = sqlite3.connect("rpg.db")
    c = conn.cursor()
    current_week = get_week_start()
    c.execute("SELECT trainings_this_week, week_start FROM players WHERE discord_id = ?", (discord_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return 0
    count, week_start = row
    if week_start != current_week:
        c.execute("UPDATE players SET trainings_this_week = 0, week_start = ? WHERE discord_id = ?", (current_week, discord_id))
        conn.commit()
        count = 0
    conn.close()
    return TRAINING_WEEKLY_MAX - count

def use_training(discord_id):
    conn = sqlite3.connect("rpg.db")
    c = conn.cursor()
    current_week = get_week_start()
    c.execute("UPDATE players SET trainings_this_week = trainings_this_week + 1, week_start = ? WHERE discord_id = ?", (current_week, discord_id))
    conn.commit()
    conn.close()

def xp_bar(xp, niveau):
    if niveau >= MAX_LEVEL:
        return "NIVEAU MAX"
    xp_current_level = xp_needed_for_level(niveau)
    xp_next_level = xp_needed_for_level(niveau + 1)
    progress = xp - xp_current_level
    needed = xp_next_level - xp_current_level
    ratio = min(progress / needed, 1.0)
    filled = int(ratio * 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"{bar} {progress}/{needed} XP"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def is_mj(interaction):
    return any(r.name == MJ_ROLE_NAME for r in interaction.user.roles)

async def send_log(guild, embed):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if channel:
        await channel.send(embed=embed)

@tree.command(name="inscription", description="Créer son personnage RP")
@app_commands.describe(nom="Nom de ton personnage", classe="Ta classe")
async def inscription(interaction: discord.Interaction, nom: str, classe: str):
    if get_player(interaction.user.id):
        await interaction.response.send_message("Tu as déjà un personnage !", ephemeral=True)
        return
    create_player(interaction.user.id, nom, classe)
    embed = discord.Embed(title="Nouveau héros !", description=f"**{nom}** le **{classe}** entre dans la légende.", color=0x8B5CF6)
    await interaction.response.send_message(embed=embed)

@tree.command(name="profil", description="Afficher la fiche d'un joueur")
@app_commands.describe(joueur="Le joueur (laisse vide pour toi)")
async def profil(interaction: discord.Interaction, joueur: discord.Member = None):
    target = joueur or interaction.user
    p = get_player(target.id)
    if not p:
        await interaction.response.send_message("Ce joueur n'a pas de personnage.", ephemeral=True)
        return
    embed = discord.Embed(title=f"{p['nom_perso']}", color=0xF59E0B)
    embed.add_field(name="Classe", value=p["classe"], inline=True)
    embed.add_field(name="Niveau", value=f"**{p['niveau']}** / {MAX_LEVEL}", inline=True)
    embed.add_field(name="XP Total", value=f"{p['xp']:,}", inline=True)
    embed.add_field(name="Progression", value=xp_bar(p["xp"], p["niveau"]), inline=False)
    embed.set_thumbnail(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@tree.command(name="mob", description="[MJ] Valider la victoire contre un mob")
@app_commands.describe(joueur="Le joueur", rang="Rang du mob (1-10)", nom_mob="Nom du mob")
async def mob(interaction: discord.Interaction, joueur: discord.Member, rang: int, nom_mob: str = None):
    if not is_mj(interaction):
        await interaction.response.send_message("Réservé aux MJ.", ephemeral=True)
        return
    if rang < 1 or rang > 10:
        await interaction.response.send_message("Le rang doit être entre 1 et 10.", ephemeral=True)
        return
    p = get_player(joueur.id)
    if not p:
        await interaction.response.send_message("Ce joueur n'a pas de personnage.", ephemeral=True)
        return
    xp = MOB_XP[rang]
    nom = nom_mob or f"Mob Rang {rang}"
    result = add_xp(joueur.id, xp, "mob", f"{nom} (Rang {rang})")
    embed = discord.Embed(title="Victoire !", description=f"**{p['nom_perso']}** a vaincu **{nom}**", color=0x10B981)
    embed.add_field(name="XP gagnée", value=f"+{xp} XP", inline=True)
    embed.add_field(name="Niveau", value=f"**{result['new_level']}**", inline=True)
    if result["leveled_up"]:
        embed.add_field(name="LEVEL UP !", value=f"Niveau {result['new_level']} atteint !", inline=False)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="boss", description="[MJ] Valider la victoire contre un boss")
@app_commands.describe(joueur="Le joueur", rang="Rang du boss (1-10)", nom_boss="Nom du boss")
async def boss(interaction: discord.Interaction, joueur: discord.Member, rang: int, nom_boss: str = None):
    if not is_mj(interaction):
        await interaction.response.send_message("Réservé aux MJ.", ephemeral=True)
        return
    if rang < 1 or rang > 10:
        await interaction.response.send_message("Le rang doit être entre 1 et 10.", ephemeral=True)
        return
    p = get_player(joueur.id)
    if not p:
        await interaction.response.send_message("Ce joueur n'a pas de personnage.", ephemeral=True)
        return
    xp = BOSS_XP[rang]
    nom = nom_boss or f"Boss Rang {rang}"
    result = add_xp(joueur.id, xp, "boss", f"{nom} (Boss Rang {rang})")
    embed = discord.Embed(title="Boss vaincu !", description=f"**{p['nom_perso']}** a terrassé **{nom}**", color=0xEF4444)
    embed.add_field(name="XP gagnée", value=f"+{xp} XP", inline=True)
    embed.add_field(name="Niveau", value=f"**{result['new_level']}**", inline=True)
    if result["leveled_up"]:
        embed.add_field(name="LEVEL UP !", value=f"Niveau {result['new_level']} atteint !", inline=False)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="entrainement", description="[MJ] Valider une session d'entraînement")
@app_commands.describe(joueur="Le joueur", type="normal ou chanceux")
async def entrainement(interaction: discord.Interaction, joueur: discord.Member, type: str = "normal"):
    if not is_mj(interaction):
        await interaction.response.send_message("Réservé aux MJ.", ephemeral=True)
        return
    p = get_player(joueur.id)
    if not p:
        await interaction.response.send_message("Ce joueur n'a pas de personnage.", ephemeral=True)
        return
    restants = check_and_reset_trainings(joueur.id)
    if restants <= 0:
        await interaction.response.send_message(f"**{p['nom_perso']}** a déjà utilisé ses {TRAINING_WEEKLY_MAX} entraînements cette semaine.", ephemeral=True)
        return
    if type.lower() == "chanceux":
        xp = random.randint(TRAINING_LUCKY_MIN, TRAINING_LUCKY_MAX)
        label = "Entraînement chanceux"
        color = 0xF59E0B
    else:
        xp = TRAINING_FIXED_XP
        label = "Entraînement"
        color = 0x6366F1
    use_training(joueur.id)
    result = add_xp(joueur.id, xp, "entraînement", type)
    embed = discord.Embed(title=label, color=color)
    embed.description = f"**{p['nom_perso']}** s'est entraîné !"
    embed.add_field(name="XP gagnée", value=f"+{xp} XP", inline=True)
    embed.add_field(name="Entraînements restants", value=f"{restants - 1}/{TRAINING_WEEKLY_MAX}", inline=True)
    if result["leveled_up"]:
        embed.add_field(name="LEVEL UP !", value=f"Niveau {result['new_level']} atteint !", inline=False)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="recompense", description="[MJ] Donner de l'XP libre à un joueur")
@app_commands.describe(joueur="Le joueur", xp="Montant d'XP", raison="Raison")
async def recompense(interaction: discord.Interaction, joueur: discord.Member, xp: int, raison: str = "Récompense MJ"):
    if not is_mj(interaction):
        await interaction.response.send_message("Réservé aux MJ.", ephemeral=True)
        return
    p = get_player(joueur.id)
    if not p:
        await interaction.response.send_message("Ce joueur n'a pas de personnage.", ephemeral=True)
        return
    result = add_xp(joueur.id, xp, "récompense", raison)
    embed = discord.Embed(title="Récompense !", color=0xF59E0B)
    embed.description = f"**{p['nom_perso']}** reçoit une récompense."
    embed.add_field(name="XP gagnée", value=f"+{xp} XP", inline=True)
    embed.add_field(name="Raison", value=raison, inline=True)
    if result["leveled_up"]:
        embed.add_field(name="LEVEL UP !", value=f"Niveau {result['new_level']} atteint !", inline=False)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="quete", description="[MJ] Valider la complétion d'une quête")
@app_commands.describe(joueur="Le joueur", nom_quete="Nom de la quête", xp="XP accordée")
async def quete(interaction: discord.Interaction, joueur: discord.Member, nom_quete: str, xp: int):
    if not is_mj(interaction):
        await interaction.response.send_message("Réservé aux MJ.", ephemeral=True)
        return
    p = get_player(joueur.id)
    if not p:
        await interaction.response.send_message("Ce joueur n'a pas de personnage.", ephemeral=True)
        return
    result = add_xp(joueur.id, xp, "quête", nom_quete)
    embed = discord.Embed(title="Quête accomplie !", description=f"**{p['nom_perso']}** a terminé **{nom_quete}**", color=0x8B5CF6)
    embed.add_field(name="XP gagnée", value=f"+{xp} XP", inline=True)
    if result["leveled_up"]:
        embed.add_field(name="LEVEL UP !", value=f"Niveau {result['new_level']} atteint !", inline=False)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="classement", description="Top 10 des joueurs du serveur")
async def classement(interaction: discord.Interaction):
    conn = sqlite3.connect("rpg.db")
    c = conn.cursor()
    c.execute("SELECT discord_id, nom_perso, classe, niveau, xp FROM players ORDER BY xp DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    medals = ["1","2","3"] + ["⚔️"] * 7
    embed = discord.Embed(title="Classement des héros", color=0xF59E0B)
    lines = []
    for i, (did, nom, classe, niveau, xp) in enumerate(rows):
        lines.append(f"{medals[i]} **{nom}** (Niv. {niveau}) — {xp:,} XP")
    embed.description = "\n".join(lines) if lines else "Aucun joueur encore."
    await interaction.response.send_message(embed=embed)

@tree.command(name="xp_info", description="Voir les gains d'XP par source")
async def xp_info(interaction: discord.Interaction):
    embed = discord.Embed(title="Tableau des XP", color=0x6366F1)
    mob_lines = "\n".join([f"Rang {r} : {xp} XP" for r, xp in MOB_XP.items()])
    boss_lines = "\n".join([f"Rang {r} : {xp} XP" for r, xp in BOSS_XP.items()])
    embed.add_field(name="Mobs", value=mob_lines, inline=True)
    embed.add_field(name="Boss", value=boss_lines, inline=True)
    embed.add_field(name="Entraînements", value=f"Normal : {TRAINING_FIXED_XP} XP\nChanceux : {TRAINING_LUCKY_MIN}-{TRAINING_LUCKY_MAX} XP\nMax/semaine : {TRAINING_WEEKLY_MAX}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    init_db()
    await tree.sync()
    print(f"Bot connecté : {bot.user}")

bot.run(TOKEN)