#!/usr/bin/env python3
import asyncio
import datetime
import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

TOKEN           = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID        = int(os.environ["DISCORD_GUILD_ID"])
MEMBER_ROLE     = int(os.environ["DISCORD_MEMBER_ROLE_ID"])
WELCOME_CHANNEL = int(os.environ["DISCORD_WELCOME_CHANNEL_ID"])
BOT_CHANNEL     = int(os.environ["DISCORD_BOT_CHANNEL_ID"])
ROLLEN_CHANNEL  = int(os.environ["DISCORD_ROLLEN_CHANNEL_ID"])
VC_HUB_ID       = int(os.environ.get("DISCORD_VC_HUB_ID") or 0)
VC_CATEGORY_ID  = int(os.environ.get("DISCORD_VC_CATEGORY_ID") or 0)

# Feste Channel-IDs (für Setup + Logging)
CH_ROLLEN     = 1503531777124204615
CH_WELCOME    = 1503531781008134245
CH_MEDIA      = 1503531786003550271
CH_REGELN     = 1501720745976533133
CH_ANKUEND    = 1501720750409777172
CH_ALLGEMEIN  = 1501720759981178932
CH_BOT        = 1501720772186734724
CH_AFK        = 1501720791883186226
CH_STAFF_CAT  = 1503535739017760778
CH_MOD_CHAT   = 1503535757548064928
CH_MOD_LOG    = 1503535763013373962

REACTION_ROLES = {
    "🎵": 1501721272659480766,
    "🚀": 1501883993782620250,
    "🪓": 1501883995519057981,
    "🔴": 1501883996999651379,
}

warnings_db: dict[int, int] = {}
reaction_role_msg_id: int | None = None
managed_vcs: dict[int, int] = {}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def update_status():
    guild = bot.get_guild(GUILD_ID)
    if guild:
        await bot.change_presence(activity=discord.Game(name=f"mit {guild.member_count} Musikern 🎵"))


async def mod_log(embed: discord.Embed):
    ch = bot.get_channel(CH_MOD_LOG)
    if ch:
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            pass


@bot.event
async def on_ready():
    global reaction_role_msg_id
    guild = bot.get_guild(GUILD_ID)
    await update_status()
    log.info(f"Bot online: {bot.user} | {guild.member_count} Members")

    synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    log.info(f"Slash commands synced: {len(synced)}")

    channel = bot.get_channel(ROLLEN_CHANNEL)
    pins = await channel.pins()
    for pin in pins:
        if pin.author == bot.user and "Reaction Roles" in pin.content:
            reaction_role_msg_id = pin.id
            log.info(f"Reaction-Role-Message gefunden: {pin.id}")
            return

    lines = ["**🎭 Reaction Roles**\n", "Klick eine Reaktion um eine Rolle zu bekommen:\n"]
    for emoji, role_id in REACTION_ROLES.items():
        role = guild.get_role(role_id)
        lines.append(f"{emoji} → **{role.name}**")
    msg = await channel.send("\n".join(lines))
    await msg.pin()
    for emoji in REACTION_ROLES:
        await msg.add_reaction(emoji)
    reaction_role_msg_id = msg.id
    log.info(f"Reaction-Role-Message erstellt: {msg.id}")


# ─── Auto-Moderation ──────────────────────────────────────────────────────────

_spam_track: dict[int, list[float]] = defaultdict(list)
SPAM_LIMIT   = 5
SPAM_WINDOW  = 5.0
SPAM_TIMEOUT = 300

_SCAM_RE = re.compile(
    r"discord[-_\s]?nitro\.[a-z]"
    r"|discordgift\.[a-z]"
    r"|free\W{0,5}nitro"
    r"|nitro\W{0,5}free"
    r"|@everyone.{0,80}https?://"
    , re.IGNORECASE
)

_join_times: deque[float] = deque()
RAID_JOINS    = 8
RAID_WINDOW   = 20.0
RAID_SLOWMODE = 30
RAID_DURATION = 600


async def _automod_alert(channel: discord.TextChannel, member: discord.Member, reason: str, log_embed: discord.Embed | None = None):
    try:
        embed = discord.Embed(
            description=f"🛡️ {member.mention} — {reason}",
            color=discord.Color.orange()
        )
        msg = await channel.send(embed=embed)
        await asyncio.sleep(10)
        await msg.delete()
    except discord.HTTPException:
        pass
    if log_embed:
        await mod_log(log_embed)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        if message.guild and message.guild.id == GUILD_ID and message.author.id == bot.user.id:
            cmd = message.content.strip()
            if cmd == "!setup":
                await run_server_setup(message.guild, message.channel)
            elif cmd == "!audit":
                await run_audit(message.guild, message.channel)
            elif cmd == "!fixperms":
                await run_fix_perms(message.guild, message.channel)
        return

    if not message.guild or message.guild.id != GUILD_ID:
        return

    member = message.author
    is_mod = member.guild_permissions.kick_members or member.guild_permissions.administrator

    if is_mod:
        await bot.process_commands(message)
        return

    content = message.content

    if _SCAM_RE.search(content):
        await message.delete()
        log_embed = discord.Embed(
            title="🔗 Scam-Link gelöscht",
            description=f"**User:** {member.mention} (`{member.name}`)\n**Channel:** {message.channel.mention}\n**Inhalt:** ```{content[:200]}```",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        await _automod_alert(message.channel, member, "Scam-Link erkannt und gelöscht.", log_embed)
        log.info(f"AutoMod Scam: {member.name}")
        return

    if "@everyone" in content or "@here" in content:
        await message.delete()
        log_embed = discord.Embed(
            title="📢 @everyone durch Nicht-Mod",
            description=f"**User:** {member.mention} (`{member.name}`)\n**Channel:** {message.channel.mention}",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        await _automod_alert(message.channel, member, "@everyone/@here ist nur für Mods erlaubt.", log_embed)
        log.info(f"AutoMod @everyone: {member.name}")
        return

    now = time.monotonic()
    times = _spam_track[member.id]
    times.append(now)
    while times and times[0] < now - SPAM_WINDOW:
        times.pop(0)

    if len(times) >= SPAM_LIMIT:
        times.clear()
        until = discord.utils.utcnow() + datetime.timedelta(seconds=SPAM_TIMEOUT)
        try:
            await member.timeout(until, reason="Auto-Mod: Spam")
            log_embed = discord.Embed(
                title="🔇 Spam-Timeout",
                description=f"**User:** {member.mention} (`{member.name}`)\n**Dauer:** 5 Minuten\n**Channel:** {message.channel.mention}",
                color=discord.Color.dark_orange(),
                timestamp=discord.utils.utcnow(),
            )
            await _automod_alert(message.channel, member, "Spam erkannt — 5 Minuten Timeout.", log_embed)
            log.info(f"AutoMod Spam-Timeout: {member.name}")
        except discord.Forbidden:
            log.warning(f"AutoMod: kein Timeout-Recht für {member.name}")

    await bot.process_commands(message)


# ─── Dynamic Voice Channels ───────────────────────────────────────────────────

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.guild.id != GUILD_ID:
        return

    if VC_HUB_ID and after.channel and after.channel.id == VC_HUB_ID:
        category = None
        if VC_CATEGORY_ID:
            category = member.guild.get_channel(VC_CATEGORY_ID)
        elif after.channel.category:
            category = after.channel.category

        ch = await member.guild.create_voice_channel(
            name=f"🔊 {member.display_name}",
            category=category,
            user_limit=0,
        )
        managed_vcs[ch.id] = member.id
        await member.move_to(ch)
        log.info(f"VC erstellt: {ch.name} (owner={member.name})")

    if before.channel and before.channel.id in managed_vcs:
        ch = before.channel
        if len(ch.members) == 0:
            owner_id = managed_vcs.pop(ch.id)
            try:
                await ch.delete(reason="VC leer")
                log.info(f"VC gelöscht: {ch.name} (owner_id={owner_id})")
            except discord.NotFound:
                pass


def _get_managed_channel(interaction: discord.Interaction) -> discord.VoiceChannel | None:
    if not interaction.user.voice or not interaction.user.voice.channel:
        return None
    ch = interaction.user.voice.channel
    if managed_vcs.get(ch.id) != interaction.user.id:
        return None
    return ch


vc = app_commands.Group(name="vc", description="Deinen Voice Channel verwalten")


@vc.command(name="name", description="Channel umbenennen")
@app_commands.describe(name="Neuer Name")
async def vc_name(interaction: discord.Interaction, name: str):
    ch = _get_managed_channel(interaction)
    if not ch:
        await interaction.response.send_message("❌ Du bist nicht der Besitzer eines dynamischen Channels.", ephemeral=True)
        return
    await ch.edit(name=name)
    await interaction.response.send_message(f"✅ Channel umbenannt zu **{name}**", ephemeral=True)


@vc.command(name="limit", description="Userlimit setzen (0 = unbegrenzt)")
@app_commands.describe(limit="Maximale Nutzeranzahl (0–99, 0 = unbegrenzt)")
async def vc_limit(interaction: discord.Interaction, limit: int):
    ch = _get_managed_channel(interaction)
    if not ch:
        await interaction.response.send_message("❌ Du bist nicht der Besitzer eines dynamischen Channels.", ephemeral=True)
        return
    clamped = max(0, min(99, limit))
    await ch.edit(user_limit=clamped)
    text = f"✅ Userlimit auf **{clamped}** gesetzt" if clamped else "✅ Userlimit **aufgehoben**"
    await interaction.response.send_message(text, ephemeral=True)


@vc.command(name="lock", description="Channel privat machen")
async def vc_lock(interaction: discord.Interaction):
    ch = _get_managed_channel(interaction)
    if not ch:
        await interaction.response.send_message("❌ Du bist nicht der Besitzer eines dynamischen Channels.", ephemeral=True)
        return
    await ch.set_permissions(interaction.guild.default_role, connect=False)
    await interaction.response.send_message("🔒 Channel ist jetzt **privat**", ephemeral=True)


@vc.command(name="unlock", description="Channel öffentlich machen")
async def vc_unlock(interaction: discord.Interaction):
    ch = _get_managed_channel(interaction)
    if not ch:
        await interaction.response.send_message("❌ Du bist nicht der Besitzer eines dynamischen Channels.", ephemeral=True)
        return
    await ch.set_permissions(interaction.guild.default_role, connect=None)
    await interaction.response.send_message("🔓 Channel ist jetzt **öffentlich**", ephemeral=True)


@vc.command(name="invite", description="Bestimmten User in privaten Channel einladen")
@app_commands.describe(user="User der Zutritt bekommt")
async def vc_invite(interaction: discord.Interaction, user: discord.Member):
    ch = _get_managed_channel(interaction)
    if not ch:
        await interaction.response.send_message("❌ Du bist nicht der Besitzer eines dynamischen Channels.", ephemeral=True)
        return
    await ch.set_permissions(user, connect=True)
    await interaction.response.send_message(f"✅ {user.mention} darf jetzt joinen", ephemeral=True)


@vc.command(name="transfer", description="Channel-Ownership übertragen")
@app_commands.describe(user="Neuer Besitzer (muss im Channel sein)")
async def vc_transfer(interaction: discord.Interaction, user: discord.Member):
    ch = _get_managed_channel(interaction)
    if not ch:
        await interaction.response.send_message("❌ Du bist nicht der Besitzer eines dynamischen Channels.", ephemeral=True)
        return
    if user not in ch.members:
        await interaction.response.send_message("❌ Der User muss im Channel sein.", ephemeral=True)
        return
    managed_vcs[ch.id] = user.id
    await interaction.response.send_message(f"✅ Ownership an {user.mention} übertragen", ephemeral=True)
    log.info(f"VC Ownership {ch.name}: {interaction.user.name} → {user.name}")


bot.tree.add_command(vc, guild=discord.Object(id=GUILD_ID))

# ─── Members ──────────────────────────────────────────────────────────────────

@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return

    now = time.monotonic()
    _join_times.append(now)
    while _join_times and _join_times[0] < now - RAID_WINDOW:
        _join_times.popleft()

    if len(_join_times) >= RAID_JOINS:
        _join_times.clear()
        log.warning("RAID erkannt!")
        raid_embed = discord.Embed(
            title="🚨 Raid erkannt!",
            description=f"{RAID_JOINS} Joins in {int(RAID_WINDOW)}s — Slowmode ({RAID_SLOWMODE}s) aktiv für {RAID_DURATION // 60} Min.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        await mod_log(raid_embed)
        text_channels = [c for c in member.guild.text_channels if c.permissions_for(member.guild.me).manage_channels]
        for ch in text_channels:
            try:
                await ch.edit(slowmode_delay=RAID_SLOWMODE)
            except discord.HTTPException:
                pass

        async def _remove_slowmode():
            await asyncio.sleep(RAID_DURATION)
            for ch in text_channels:
                try:
                    await ch.edit(slowmode_delay=0)
                except discord.HTTPException:
                    pass
            log.info("Raid-Slowmode aufgehoben")

        asyncio.create_task(_remove_slowmode())

    role = member.guild.get_role(MEMBER_ROLE)
    if role:
        await member.add_roles(role, reason="Auto-Role on join")

    channel = bot.get_channel(WELCOME_CHANNEL)
    if channel:
        embed = discord.Embed(
            title="Willkommen bei Die Musiker! 🎵",
            description=f"Hey {member.mention}, schön dass du da bist!\nSchau dir 📋・regeln an und wähle deine Rollen in 🎭・rollen!",
            color=discord.Color.purple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Mitglied #{member.guild.member_count}")
        await channel.send(embed=embed)

    await update_status()


@bot.event
async def on_member_remove(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return
    channel = bot.get_channel(WELCOME_CHANNEL)
    if channel:
        embed = discord.Embed(
            title="Tschüss! 👋",
            description=f"**{member.display_name}** hat den Server verlassen.",
            color=discord.Color.red(),
        )
        await channel.send(embed=embed)
    await update_status()


# ─── Reaction Roles ───────────────────────────────────────────────────────────

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.message_id != reaction_role_msg_id or payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(GUILD_ID)
    role_id = REACTION_ROLES.get(str(payload.emoji))
    if not role_id:
        return
    role = guild.get_role(role_id)
    member = guild.get_member(payload.user_id)
    if role and member:
        await member.add_roles(role)
        log.info(f"Rolle {role.name} → {member.name}")


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id != reaction_role_msg_id:
        return
    guild = bot.get_guild(GUILD_ID)
    role_id = REACTION_ROLES.get(str(payload.emoji))
    if not role_id:
        return
    role = guild.get_role(role_id)
    member = guild.get_member(payload.user_id)
    if role and member:
        await member.remove_roles(role)
        log.info(f"Rolle {role.name} entfernt von {member.name}")


# ─── Prefix Commands ──────────────────────────────────────────────────────────

@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")


@bot.command()
async def members(ctx: commands.Context):
    embed = discord.Embed(title=f"Mitglieder — {ctx.guild.name}", color=discord.Color.blue())
    embed.add_field(name="Gesamt", value=ctx.guild.member_count)
    await ctx.send(embed=embed)


@bot.command()
async def info(ctx: commands.Context):
    g = ctx.guild
    embed = discord.Embed(title=g.name, color=discord.Color.purple())
    embed.add_field(name="Mitglieder", value=g.member_count, inline=True)
    embed.add_field(name="Channels", value=len(g.channels), inline=True)
    embed.add_field(name="Erstellt am", value=g.created_at.strftime("%d.%m.%Y"), inline=True)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx: commands.Context, member: discord.Member, *, reason: str = "Kein Grund angegeben"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 **{member.display_name}** wurde gekickt. Grund: {reason}")
    await mod_log(discord.Embed(
        title="👢 Kick",
        description=f"**User:** {member.mention}\n**Mod:** {ctx.author.mention}\n**Grund:** {reason}",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    ))


@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx: commands.Context, member: discord.Member, *, reason: str = "Kein Grund angegeben"):
    warnings_db[member.id] = warnings_db.get(member.id, 0) + 1
    count = warnings_db[member.id]
    await ctx.send(f"⚠️ {member.mention} wurde verwarnt ({count}x). Grund: {reason}")
    await mod_log(discord.Embed(
        title="⚠️ Verwarnung",
        description=f"**User:** {member.mention}\n**Mod:** {ctx.author.mention}\n**Grund:** {reason}\n**Gesamt:** {count}x",
        color=discord.Color.yellow(),
        timestamp=discord.utils.utcnow(),
    ))


@bot.command()
@commands.has_permissions(kick_members=True)
async def warns(ctx: commands.Context, member: discord.Member):
    count = warnings_db.get(member.id, 0)
    await ctx.send(f"⚠️ **{member.display_name}** hat {count} Verwarnung(en).")


@kick.error
@warn.error
@warns.error
async def mod_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Du hast keine Berechtigung dafür.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member nicht gefunden.")


# ─── Setup ────────────────────────────────────────────────────────────────────

async def run_server_setup(g: discord.Guild, channel: discord.abc.Messageable):
    msg = await channel.send("⚙️ Setup läuft...")
    results = []

    # 1. Rollenfarben
    role_colors = {
        "Among Us": discord.Color.from_rgb(231, 76, 60),
        "Minecraft": discord.Color.from_rgb(46, 204, 113),
        "Codenames": discord.Color.from_rgb(230, 126, 34),
        "Musiker":   discord.Color.from_rgb(88, 101, 242),
        "AOT":       discord.Color.from_rgb(153, 45, 34),
        "Member":    discord.Color.from_rgb(149, 165, 166),
    }
    for role in g.roles:
        if role.name in role_colors:
            try:
                await role.edit(color=role_colors[role.name])
                await asyncio.sleep(0.5)
            except discord.HTTPException as e:
                results.append(f"⚠️ Farbe {role.name}: {e}")
    results.append("✅ Rollenfarben gesetzt")

    # 2. Moderator-Rolle
    mod_role = discord.utils.get(g.roles, name="🛡 Moderator")
    if not mod_role:
        mod_perms = discord.Permissions(
            moderate_members=True, manage_messages=True, move_members=True,
            kick_members=True, mute_members=True, deafen_members=True,
            manage_nicknames=True, read_messages=True, send_messages=True,
            connect=True, speak=True, read_message_history=True,
            add_reactions=True, embed_links=True, attach_files=True,
        )
        mod_role = await g.create_role(
            name="🛡 Moderator",
            color=discord.Color.from_rgb(255, 165, 0),
            permissions=mod_perms,
            hoist=True,
        )
        results.append(f"✅ Moderator-Rolle erstellt ({mod_role.id})")
    else:
        results.append("ℹ️ Moderator-Rolle existiert bereits")

    admin_role = discord.utils.get(g.roles, name="Administrator")

    # 3. Readonly-Channels (@everyone kein Schreiben)
    readonly = {
        CH_ROLLEN:  "🎭・rollen",
        CH_WELCOME: "👋・welcome",
        CH_REGELN:  "📋・regeln",
        CH_ANKUEND: "📢・ankündigungen",
    }
    for ch_id, name in readonly.items():
        ch = bot.get_channel(ch_id)
        if ch:
            try:
                await ch.set_permissions(g.default_role, send_messages=False, add_reactions=False)
                await asyncio.sleep(0.3)
            except discord.HTTPException as e:
                results.append(f"⚠️ {name}: {e}")
    results.append("✅ Readonly-Channels gesetzt")

    # 4. Staff-Bereich: @everyone + Member unsichtbar, nur Mod + Admin
    member_role = g.get_role(MEMBER_ROLE)
    staff_channels = [CH_STAFF_CAT, CH_MOD_CHAT, CH_MOD_LOG]
    for ch_id in staff_channels:
        ch = bot.get_channel(ch_id)
        if ch:
            try:
                await ch.set_permissions(g.default_role, view_channel=False)
                await asyncio.sleep(0.2)
                if member_role:
                    await ch.set_permissions(member_role, view_channel=False)
                    await asyncio.sleep(0.2)
                if mod_role:
                    await ch.set_permissions(mod_role, view_channel=True, send_messages=True, read_message_history=True)
                    await asyncio.sleep(0.2)
                if admin_role:
                    await ch.set_permissions(admin_role, view_channel=True, send_messages=True, read_message_history=True)
                    await asyncio.sleep(0.2)
            except discord.HTTPException as e:
                results.append(f"⚠️ Staff-Channel {ch_id}: {e}")
    results.append("✅ Staff-Bereich gesichert (nur Mod/Admin sichtbar)")

    # 5. Channel-Topics
    topics = {
        CH_ALLGEMEIN: "Habt ihr was zu sagen? Dann raus damit 💬",
        CH_BOT:       "Bot-Commands · Kram · Debugging 🤖",
        CH_ANKUEND:   "Offizielle Infos von der Serverleitung 📢",
        CH_REGELN:    "Regeln lesen = Pflicht 📋",
    }
    for ch_id, topic in topics.items():
        ch = bot.get_channel(ch_id)
        if ch:
            try:
                await ch.edit(topic=topic)
                await asyncio.sleep(0.3)
            except discord.HTTPException:
                pass
    results.append("✅ Channel-Topics gesetzt")

    # 6. Slowmode ankündigungen
    ch = bot.get_channel(CH_ANKUEND)
    if ch:
        try:
            await ch.edit(slowmode_delay=60)
        except discord.HTTPException:
            pass
    results.append("✅ Slowmode (60s) auf ankündigungen")

    # 7. AFK-Timeout
    afk_ch = bot.get_channel(CH_AFK)
    try:
        await g.edit(afk_channel=afk_ch, afk_timeout=300)
        results.append("✅ AFK-Timeout 5 Minuten")
    except discord.HTTPException as e:
        results.append(f"⚠️ AFK: {e}")

    embed = discord.Embed(
        title="✅ Server-Setup abgeschlossen",
        description="\n".join(results),
        color=discord.Color.green(),
    )
    await msg.edit(content=None, embed=embed)
    log.info("!setup abgeschlossen")


@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_cmd(ctx: commands.Context):
    await run_server_setup(ctx.guild, ctx)


@setup_cmd.error
async def setup_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Nur Admins.")


# ─── Audit ────────────────────────────────────────────────────────────────────

async def run_audit(g: discord.Guild, channel: discord.abc.Messageable):
    issues = []
    ok = []
    info_lines = []

    everyone = g.default_role

    # Rollen: Admin-Check
    for role in g.roles:
        if role.name == "@everyone":
            continue
        if role.permissions.administrator:
            if role.name in ("Administrator",) or role.managed:
                ok.append(f"✅ **{role.name}** — Administrator (erwartet)")
            else:
                issues.append(f"🚨 **{role.name}** hat `administrator` — unerwartet!")
        else:
            if role.name == "🛡 Moderator":
                ok.append("✅ **🛡 Moderator** — kein Administrator ✓")

    # @everyone Server-Permissions
    if everyone.permissions.administrator:
        issues.append("🚨 @everyone hat `administrator`!")
    if everyone.permissions.manage_guild:
        issues.append("⚠️ @everyone hat `manage_guild`")
    if everyone.permissions.manage_roles:
        issues.append("⚠️ @everyone hat `manage_roles`")
    if everyone.permissions.manage_channels:
        issues.append("⚠️ @everyone hat `manage_channels`")
    if everyone.permissions.manage_webhooks:
        issues.append("⚠️ @everyone hat `manage_webhooks`")
    if everyone.permissions.mention_everyone:
        issues.append("⚠️ @everyone darf @everyone/@here pingen")
    else:
        ok.append("✅ @everyone darf nicht @everyone pingen")

    # Text-Channels: @everyone Schreibrecht
    write_allowed = []
    write_denied = []
    for ch in sorted(g.text_channels, key=lambda c: c.position):
        ow = ch.overwrites_for(everyone)
        # send_messages=None bedeutet: Server-Default (usually True)
        # send_messages=False bedeutet: explizit verboten
        # send_messages=True bedeutet: explizit erlaubt
        can_write = ow.send_messages is not False
        if can_write:
            write_allowed.append(f"✏️ #{ch.name}")
        else:
            write_denied.append(f"🔒 #{ch.name}")

    info_lines.append("**Text-Channels (@everyone Schreibrecht):**\n" +
                       " · ".join(write_allowed) + "\n" +
                       " · ".join(write_denied))

    # Staff-Channels: @everyone view_channel
    staff_visible = []
    for ch_id, name in [(CH_STAFF_CAT, "🔒 STAFF"), (CH_MOD_CHAT, "🛡・mod-chat"), (CH_MOD_LOG, "📋・mod-log")]:
        ch = bot.get_channel(ch_id)
        if ch:
            ow = ch.overwrites_for(everyone)
            if ow.view_channel is False:
                ok.append(f"✅ {name} — für @everyone unsichtbar ✓")
            else:
                issues.append(f"🚨 {name} — @everyone kann sehen!")

    # BOT-Rolle (managed)
    bot_role = next((r for r in g.roles if r.managed and r.name != "@everyone"), None)
    if bot_role:
        if bot_role.permissions.administrator:
            issues.append(f"🚨 Bot-Rolle **{bot_role.name}** hat `administrator`!")
        else:
            ok.append(f"✅ Bot-Rolle **{bot_role.name}** — kein Administrator ✓")

    # Webhooks
    try:
        webhooks = await g.webhooks()
        if webhooks:
            info_lines.append(f"ℹ️ {len(webhooks)} Webhook(s) aktiv: {', '.join(w.name for w in webhooks)}")
        else:
            ok.append("✅ Keine Webhooks konfiguriert")
    except discord.Forbidden:
        info_lines.append("ℹ️ Webhooks: kein Lesezugriff")

    embed = discord.Embed(
        title="🔍 Permissions Audit — Die Musiker",
        color=discord.Color.red() if issues else discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    if issues:
        embed.add_field(name="🚨 Probleme", value="\n".join(issues), inline=False)
    if ok:
        embed.add_field(name="✅ OK", value="\n".join(ok), inline=False)
    if info_lines:
        embed.add_field(name="ℹ️ Info", value="\n".join(info_lines), inline=False)

    await channel.send(embed=embed)
    log.info(f"Audit: {len(issues)} Probleme, {len(ok)} OK")
    for issue in issues:
        log.warning(f"Audit PROBLEM: {issue}")


@bot.command(name="audit")
@commands.has_permissions(administrator=True)
async def audit_cmd(ctx: commands.Context):
    await run_audit(ctx.guild, ctx)


# ─── Fix Perms ────────────────────────────────────────────────────────────────

async def run_fix_perms(g: discord.Guild, channel: discord.abc.Messageable):
    fixes = []

    # Fix 1: Manuelle "Bot"-Rolle hat fälschlicherweise Administrator
    bot_custom = discord.utils.get(g.roles, name="Bot", managed=False)
    if bot_custom and bot_custom.permissions.administrator:
        safe = discord.Permissions(
            read_messages=True, send_messages=True, read_message_history=True,
            connect=True, speak=True, add_reactions=True,
            embed_links=True, attach_files=True,
        )
        await bot_custom.edit(permissions=safe)
        fixes.append("✅ **Bot** Rolle — Administrator entfernt, sichere Permissions gesetzt")
    else:
        fixes.append("ℹ️ **Bot** Rolle — kein Administrator (oder nicht gefunden)")

    # Fix 2: @everyone darf @everyone/@here pingen
    if g.default_role.permissions.mention_everyone:
        new_val = g.default_role.permissions.value & ~discord.Permissions(mention_everyone=True).value
        await g.default_role.edit(permissions=discord.Permissions(new_val))
        fixes.append("✅ **@everyone** — mention_everyone entfernt")
    else:
        fixes.append("ℹ️ **@everyone** — mention_everyone war bereits deaktiviert")

    # Fix 3: Managed BOT-Rolle — nicht per Code editierbar
    managed_bot = next((r for r in g.roles if r.managed), None)
    if managed_bot and managed_bot.permissions.administrator:
        fixes.append(
            f"⚠️ **{managed_bot.name}** (managed) hat Administrator — nicht per Code fixbar.\n"
            "→ Bot neu einladen mit spezifischen Permissions statt `Administrator`"
        )

    embed = discord.Embed(
        title="🔧 Permission-Fixes",
        description="\n".join(fixes),
        color=discord.Color.green(),
    )
    await channel.send(embed=embed)
    log.info(f"fixperms abgeschlossen")


@bot.command(name="fixperms")
@commands.has_permissions(administrator=True)
async def fixperms_cmd(ctx: commands.Context):
    await run_fix_perms(ctx.guild, ctx)


bot.run(TOKEN)
