import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import random
from datetime import datetime, timedelta

import os
TOKEN = os.environ.get("DISCORD_TOKEN")
MJ_ROLE_NAME = "MJ"
LOG_CHANNEL_NAME = "logs-economie"
TAXE_MARCHE = 0.10

SALAIRE_HEBDO = 500

DONJON_CREDITS = {
    "E-": 100, "E": 150, "E+": 200,
    "D-": 300, "D": 400, "D+": 500,
    "C-": 700, "C": 900, "C+": 1100,
    "B-": 1400, "B": 1700, "B+": 2000,
    "A-": 2500, "A": 3000, "A+": 3500
}

RANGS_DONJON = list(DONJON_CREDITS.keys())

RARETES = ["Commun", "Peu Commun", "Rare", "Épique", "Légendaire", "Mythique", "Transcendant", "Ego"]
RARETE_COULEURS = {
    "Commun": 0xAAAAAA,
    "Peu Commun": 0x57F287,
    "Rare": 0x3498DB,
    "Épique": 0x9B59B6,
    "Légendaire": 0xF1C40F,
    "Mythique": 0xFF6B35,
    "Transcendant": 0xFF0000,
    "Ego": 0xFFFFFF
}

BOUTIQUE_DEFAULT = [
    {"nom": "Potion de soin", "prix": 100, "rarete": "Commun", "type": "consommable", "effet": "Soin en RP", "xp_bonus": 0},
    {"nom": "Gemme d'expérience", "prix": 300, "rarete": "Peu Commun", "type": "gemme", "effet": "Donne 200 XP", "xp_bonus": 200},
    {"nom": "Grande Gemme", "prix": 800, "rarete": "Rare", "type": "gemme", "effet": "Donne 600 XP", "xp_bonus": 600},
    {"nom": "Gemme Épique", "prix": 2000, "rarete": "Épique", "type": "gemme", "effet": "Donne 1500 XP", "xp_bonus": 1500},
    {"nom": "Coffre Mystère", "prix": 500, "rarete": "Rare", "type": "coffre", "effet": "Contient un item aléatoire", "xp_bonus": 0},
]

def init_db():
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            discord_id INTEGER PRIMARY KEY,
            credits    INTEGER DEFAULT 0,
            last_salaire TEXT DEFAULT ''
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventaires (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            item_nom   TEXT,
            rarete     TEXT,
            type_item  TEXT,
            xp_bonus   INTEGER DEFAULT 0,
            quantite   INTEGER DEFAULT 1
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS boutique (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            nom      TEXT UNIQUE,
            prix     INTEGER,
            rarete   TEXT,
            type_item TEXT,
            effet    TEXT,
            xp_bonus INTEGER DEFAULT 0,
            disponible INTEGER DEFAULT 1
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS marche (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            vendeur_id INTEGER,
            item_nom   TEXT,
            rarete     TEXT,
            type_item  TEXT,
            xp_bonus   INTEGER DEFAULT 0,
            prix       INTEGER,
            date_mise  TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            action     TEXT,
            montant    INTEGER,
            detail     TEXT,
            timestamp  TEXT
        )
    """)
    for item in BOUTIQUE_DEFAULT:
        c.execute("INSERT OR IGNORE INTO boutique (nom, prix, rarete, type_item, effet, xp_bonus) VALUES (?,?,?,?,?,?)",
                  (item["nom"], item["prix"], item["rarete"], item["type"], item["effet"], item["xp_bonus"]))
    conn.commit()
    conn.close()

def get_wallet(discord_id):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO wallets (discord_id) VALUES (?)", (discord_id,))
    conn.commit()
    c.execute("SELECT credits, last_salaire FROM wallets WHERE discord_id = ?", (discord_id,))
    row = c.fetchone()
    conn.close()
    return {"credits": row[0], "last_salaire": row[1]}

def add_credits(discord_id, montant, action, detail):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO wallets (discord_id) VALUES (?)", (discord_id,))
    c.execute("UPDATE wallets SET credits = credits + ? WHERE discord_id = ?", (montant, discord_id))
    c.execute("INSERT INTO logs (discord_id, action, montant, detail, timestamp) VALUES (?,?,?,?,?)",
              (discord_id, action, montant, detail, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def remove_credits(discord_id, montant):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT credits FROM wallets WHERE discord_id = ?", (discord_id,))
    row = c.fetchone()
    if not row or row[0] <montant:
        conn.close()
        return False
    c.execute("UPDATE wallets SET credits = credits - ? WHERE discord_id = ?", (montant, discord_id))
    conn.commit()
    conn.close()
    return True

def add_item_inventaire(discord_id, nom, rarete, type_item, xp_bonus):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT id, quantite FROM inventaires WHERE discord_id = ? AND item_nom = ?", (discord_id, nom))
    row = c.fetchone()
    if row:
        c.execute("UPDATE inventaires SET quantite = quantite + 1 WHERE id = ?", (row[0],))
    else:
        c.execute("INSERT INTO inventaires (discord_id, item_nom, rarete, type_item, xp_bonus) VALUES (?,?,?,?,?)",
                  (discord_id, nom, rarete, type_item, xp_bonus))
    conn.commit()
    conn.close()

def remove_item_inventaire(discord_id, nom):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT id, quantite, rarete, type_item, xp_bonus FROM inventaires WHERE discord_id = ? AND item_nom = ?", (discord_id, nom))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    item_data = {"rarete": row[2], "type_item": row[3], "xp_bonus": row[4]}
    if row[1] > 1:
        c.execute("UPDATE inventaires SET quantite = quantite - 1 WHERE id = ?", (row[0],))
    else:
        c.execute("DELETE FROM inventaires WHERE id = ?", (row[0],))
    conn.commit()
    conn.close()
    return item_data

def get_week_str():
    today = datetime.utcnow()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%W")

def rarete_couleur(rarete):
    return RARETE_COULEURS.get(rarete, 0xFFFFFF)

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

@tasks.loop(hours=1)
async def salaire_hebdo():
    now = datetime.utcnow()
    if now.weekday() != 0 or now.hour != 8:
        return
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    week = get_week_str()
    c.execute("SELECT discord_id FROM wallets WHERE last_salaire != ?", (week,))
    joueurs = c.fetchall()
    for (did,) in joueurs:
        c.execute("UPDATE wallets SET credits = credits + ?, last_salaire = ? WHERE discord_id = ?",
                  (SALAIRE_HEBDO, week, did))
        c.execute("INSERT INTO logs (discord_id, action, montant, detail, timestamp) VALUES (?,?,?,?,?)",
                  (did, "salaire", SALAIRE_HEBDO, "Salaire hebdomadaire", datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

@tree.command(name="credits", description="Voir ses crédits")
@app_commands.describe(joueur="Le joueur (laisse vide pour toi)")
async def credits_cmd(interaction: discord.Interaction, joueur: discord.Member = None):
    target = joueur or interaction.user
    w = get_wallet(target.id)
    embed = discord.Embed(title=f"Portefeuille de {target.display_name}", color=0xF59E0B)
    embed.add_field(name="Credits", value=f"**{w['credits']:,} credits**")
    await interaction.response.send_message(embed=embed)

@tree.command(name="donner_credits", description="[MJ] Donner des credits a un joueur")
@app_commands.describe(joueur="Le joueur", montant="Montant", raison="Raison")
async def donner_credits(interaction: discord.Interaction, joueur: discord.Member, montant: int, raison: str = "Don MJ"):
    if not is_mj(interaction):
        await interaction.response.send_message("Reserve aux MJ.", ephemeral=True)
        return
    add_credits(joueur.id, montant, "don_mj", raison)
    embed = discord.Embed(title="Credits recus !", color=0xF59E0B)
    embed.description = f"**{joueur.display_name}** recoit **{montant:,} credits**"
    embed.add_field(name="Raison", value=raison)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="retirer_credits", description="[MJ] Retirer des credits a un joueur")
@app_commands.describe(joueur="Le joueur", montant="Montant", raison="Raison")
async def retirer_credits(interaction: discord.Interaction, joueur: discord.Member, montant: int, raison: str = "Retrait MJ"):
    if not is_mj(interaction):
        await interaction.response.send_message("Reserve aux MJ.", ephemeral=True)
        return
    ok = remove_credits(joueur.id, montant)
    if not ok:
        await interaction.response.send_message("Ce joueur n'a pas assez de credits.", ephemeral=True)
        return
    embed = discord.Embed(title="Credits retires", color=0xEF4444)
    embed.description = f"**{montant:,} credits** retires a **{joueur.display_name}**"
    embed.add_field(name="Raison", value=raison)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="classement_credits", description="Top 10 des joueurs les plus riches")
async def classement_credits(interaction: discord.Interaction):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT discord_id, credits FROM wallets ORDER BY credits DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    medals = ["1","2","3"] + ["x"] * 7
    embed = discord.Embed(title="Classement des plus riches", color=0xF59E0B)
    lines = []
    for i, (did, creds) in enumerate(rows):
        user = bot.get_user(did)
        nom = user.display_name if user else f"Joueur {did}"
        lines.append(f"{medals[i]} **{nom}** - {creds:,} credits")
    embed.description = "\n".join(lines) if lines else "Aucun joueur encore."
    await interaction.response.send_message(embed=embed)

@tree.command(name="donjon", description="[MJ] Valider la completion d'un donjon")
@app_commands.describe(joueur="Le joueur", rang="Rang du donjon (ex: E-, C+, A)")
async def donjon(interaction: discord.Interaction, joueur: discord.Member, rang: str):
    if not is_mj(interaction):
        await interaction.response.send_message("Reserve aux MJ.", ephemeral=True)
        return
    rang = rang.upper().replace(" ", "")
    if rang not in DONJON_CREDITS:
        await interaction.response.send_message(f"Rang invalide. Rangs disponibles : {', '.join(RANGS_DONJON)}", ephemeral=True)
        return
    credits = DONJON_CREDITS[rang]
    add_credits(joueur.id, credits, "donjon", f"Donjon {rang}")
    embed = discord.Embed(title="Donjon complete !", color=0x8B5CF6)
    embed.description = f"**{joueur.display_name}** a survécu au **Donjon {rang}** !"
    embed.add_field(name="Recompense", value=f"**+{credits:,} credits**")
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="donjons_liste", description="Voir les credits par rang de donjon")
async def donjons_liste(interaction: discord.Interaction):
    embed = discord.Embed(title="Recompenses des Donjons", color=0x8B5CF6)
    lines = "\n".join([f"**{r}** -> {c:,} credits" for r, c in DONJON_CREDITS.items()])
    embed.description = lines
    await interaction.response.send_message(embed=embed)

@tree.command(name="boutique", description="Voir les items disponibles a l'achat")
async def boutique(interaction: discord.Interaction):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT nom, prix, rarete, effet FROM boutique WHERE disponible = 1 ORDER BY prix ASC")
    items = c.fetchall()
    conn.close()
    embed = discord.Embed(title="Boutique", color=0xF59E0B)
    if not items:
        embed.description = "La boutique est vide."
    else:
        for nom, prix, rarete, effet in items:
            embed.add_field(name=f"{nom} - {prix:,} credits", value=f"{rarete} | {effet}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="acheter", description="Acheter un item dans la boutique")
@app_commands.describe(item="Nom de l'item a acheter")
async def acheter(interaction: discord.Interaction, item: str):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT nom, prix, rarete, type_item, xp_bonus FROM boutique WHERE nom = ? AND disponible = 1", (item,))
    row = c.fetchone()
    conn.close()
    if not row:
        await interaction.response.send_message("Item introuvable dans la boutique.", ephemeral=True)
        return
    nom, prix, rarete, type_item, xp_bonus = row
    ok = remove_credits(interaction.user.id, prix)
    if not ok:
        await interaction.response.send_message(f"Tu n'as pas assez de credits. Prix : {prix:,}", ephemeral=True)
        return
    add_item_inventaire(interaction.user.id, nom, rarete, type_item, xp_bonus)
    embed = discord.Embed(title="Achat effectue !", color=rarete_couleur(rarete))
    embed.description = f"Tu as achete **{nom}** (rariete : {rarete})"
    embed.add_field(name="Prix paye", value=f"{prix:,} credits")
    await interaction.response.send_message(embed=embed)

@tree.command(name="ajouter_item_boutique", description="[MJ] Ajouter un item a la boutique")
@app_commands.describe(nom="Nom", prix="Prix", rarete="Rarete", type_item="gemme/consommable/coffre/autre", effet="Effet", xp_bonus="XP si gemme")
async def ajouter_item_boutique(interaction: discord.Interaction, nom: str, prix: int, rarete: str, type_item: str, effet: str, xp_bonus: int = 0):
    if not is_mj(interaction):
        await interaction.response.send_message("Reserve aux MJ.", ephemeral=True)
        return
    if rarete not in RARETES:
        await interaction.response.send_message(f"Rarete invalide. Choix : {', '.join(RARETES)}", ephemeral=True)
        return
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO boutique (nom, prix, rarete, type_item, effet, xp_bonus) VALUES (?,?,?,?,?,?)",
              (nom, prix, rarete, type_item, effet, xp_bonus))
    conn.commit()
    conn.close()
    embed = discord.Embed(title="Item ajoute a la boutique", color=rarete_couleur(rarete))
    embed.add_field(name=nom, value=f"{prix:,} credits | {rarete} | {effet}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="inventaire", description="Voir son inventaire")
@app_commands.describe(joueur="Le joueur (laisse vide pour toi)")
async def inventaire(interaction: discord.Interaction, joueur: discord.Member = None):
    target = joueur or interaction.user
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT item_nom, rarete, type_item, xp_bonus, quantite FROM inventaires WHERE discord_id = ?", (target.id,))
    items = c.fetchall()
    conn.close()
    embed = discord.Embed(title=f"Inventaire de {target.display_name}", color=0x6366F1)
    if not items:
        embed.description = "Inventaire vide."
    else:
        for nom, rarete, type_item, xp_bonus, qte in items:
            extra = f" (+{xp_bonus} XP)" if xp_bonus > 0 else ""
            embed.add_field(name=f"{nom} x{qte}", value=f"{rarete} | {type_item}{extra}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="utiliser", description="Utiliser un item de son inventaire")
@app_commands.describe(item="Nom de l'item a utiliser")
async def utiliser(interaction: discord.Interaction, item: str):
    item_data = remove_item_inventaire(interaction.user.id, item)
    if not item_data:
        await interaction.response.send_message("Tu n'as pas cet item dans ton inventaire.", ephemeral=True)
        return
    if item_data["type_item"] == "gemme":
        xp = item_data["xp_bonus"]
        embed = discord.Embed(title="Gemme utilisee !", color=rarete_couleur(item_data["rarete"]))
        embed.description = f"**{interaction.user.display_name}** utilise **{item}**"
        embed.add_field(name="XP a valider", value=f"+{xp} XP")
        embed.add_field(name="Note", value="Un MJ doit valider l'XP avec /recompense dans le bot de niveaux")
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)
    elif item_data["type_item"] == "coffre":
        conn = sqlite3.connect("economie.db")
        c = conn.cursor()
        c.execute("SELECT nom, rarete, type_item, xp_bonus FROM boutique WHERE disponible = 1")
        pool = c.fetchall()
        conn.close()
        if not pool:
            await interaction.response.send_message("Aucun item disponible dans le coffre.", ephemeral=True)
            return
        gain = random.choice(pool)
        add_item_inventaire(interaction.user.id, gain[0], gain[1], gain[2], gain[3])
        embed = discord.Embed(title="Coffre ouvert !", color=rarete_couleur(gain[1]))
        embed.description = f"**{interaction.user.display_name}** ouvre un coffre mystere !"
        embed.add_field(name="Item obtenu", value=f"**{gain[0]}** (rarete : {gain[1]})")
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(title="Item utilise", color=0x10B981)
        embed.description = f"Tu as utilise **{item}**. Informe un MJ de l'effet en RP."
        await interaction.response.send_message(embed=embed)

@tree.command(name="donner_item", description="[MJ] Donner un item a un joueur")
@app_commands.describe(joueur="Le joueur", item="Nom de l'item", rarete="Rarete", type_item="Type", xp_bonus="XP si gemme")
async def donner_item(interaction: discord.Interaction, joueur: discord.Member, item: str, rarete: str, type_item: str = "autre", xp_bonus: int = 0):
    if not is_mj(interaction):
        await interaction.response.send_message("Reserve aux MJ.", ephemeral=True)
        return
    add_item_inventaire(joueur.id, item, rarete, type_item, xp_bonus)
    embed = discord.Embed(title="Item recu !", color=rarete_couleur(rarete))
    embed.description = f"**{joueur.display_name}** recoit **{item}** (rarete : {rarete})"
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

@tree.command(name="vendre", description="Mettre un item en vente sur le marche")
@app_commands.describe(item="Nom de l'item", prix="Prix en credits")
async def vendre(interaction: discord.Interaction, item: str, prix: int):
    item_data = remove_item_inventaire(interaction.user.id, item)
    if not item_data:
        await interaction.response.send_message("Tu n'as pas cet item dans ton inventaire.", ephemeral=True)
        return
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("INSERT INTO marche (vendeur_id, item_nom, rarete, type_item, xp_bonus, prix, date_mise) VALUES (?,?,?,?,?,?,?)",
              (interaction.user.id, item, item_data["rarete"], item_data["type_item"], item_data["xp_bonus"], prix, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    taxe = int(prix * TAXE_MARCHE)
    embed = discord.Embed(title="Item mis en vente !", color=rarete_couleur(item_data["rarete"]))
    embed.description = f"**{item}** mis en vente pour **{prix:,} credits**"
    embed.add_field(name="Taxe 10%", value=f"{taxe:,} credits preleves a la vente")
    await interaction.response.send_message(embed=embed)

@tree.command(name="marche", description="Voir les items en vente entre joueurs")
async def marche(interaction: discord.Interaction):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT id, vendeur_id, item_nom, rarete, prix FROM marche ORDER BY prix ASC")
    items = c.fetchall()
    conn.close()
    embed = discord.Embed(title="Marche des joueurs", color=0x10B981)
    if not items:
        embed.description = "Aucun item en vente."
    else:
        for mid, vid, nom, rarete, prix in items:
            vendeur = bot.get_user(vid)
            nom_vendeur = vendeur.display_name if vendeur else "Inconnu"
            embed.add_field(name=f"#{mid} - {nom} - {prix:,} credits", value=f"{rarete} | Vendeur : {nom_vendeur}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="racheter", description="Acheter un item sur le marche joueur")
@app_commands.describe(id_annonce="ID de l'annonce (voir /marche)")
async def racheter(interaction: discord.Interaction, id_annonce: int):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT vendeur_id, item_nom, rarete, type_item, xp_bonus, prix FROM marche WHERE id = ?", (id_annonce,))
    row = c.fetchone()
    if not row:
        await interaction.response.send_message("Annonce introuvable.", ephemeral=True)
        conn.close()
        return
    vendeur_id, nom, rarete, type_item, xp_bonus, prix = row
    if vendeur_id == interaction.user.id:
        await interaction.response.send_message("Tu ne peux pas acheter ton propre item.", ephemeral=True)
        conn.close()
        return
    ok = remove_credits(interaction.user.id, prix)
    if not ok:
        await interaction.response.send_message(f"Tu n'as pas assez de credits. Prix : {prix:,}", ephemeral=True)
        conn.close()
        return
    taxe = int(prix * TAXE_MARCHE)
    gain_vendeur = prix - taxe
    add_credits(vendeur_id, gain_vendeur, "vente_marche", f"Vente de {nom}")
    add_item_inventaire(interaction.user.id, nom, rarete, type_item, xp_bonus)
    c.execute("DELETE FROM marche WHERE id = ?", (id_annonce,))
    conn.commit()
    conn.close()
    embed = discord.Embed(title="Achat effectue !", color=rarete_couleur(rarete))
    embed.description = f"Tu as achete **{nom}** (rarete : {rarete})"
    embed.add_field(name="Prix paye", value=f"{prix:,} credits")
    embed.add_field(name="Vendeur recoit", value=f"{gain_vendeur:,} credits apres taxe")
    await interaction.response.send_message(embed=embed)

@tree.command(name="retirer_vente", description="Retirer son item du marche")
@app_commands.describe(id_annonce="ID de l'annonce")
async def retirer_vente(interaction: discord.Interaction, id_annonce: int):
    conn = sqlite3.connect("economie.db")
    c = conn.cursor()
    c.execute("SELECT vendeur_id, item_nom, rarete, type_item, xp_bonus FROM marche WHERE id = ?", (id_annonce,))
    row = c.fetchone()
    if not row:
        await interaction.response.send_message("Annonce introuvable.", ephemeral=True)
        conn.close()
        return
    if row[0] != interaction.user.id and not is_mj(interaction):
        await interaction.response.send_message("Ce n'est pas ton annonce.", ephemeral=True)
        conn.close()
        return
    add_item_inventaire(interaction.user.id, row[1], row[2], row[3], row[4])
    c.execute("DELETE FROM marche WHERE id = ?", (id_annonce,))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"**{row[1]}** retire du marche et remis dans ton inventaire.")

@bot.event
async def on_ready():
    init_db()
    await tree.sync()
    salaire_hebdo.start()
    print(f"Bot Economie connecte : {bot.user}")

bot.run(TOKEN)