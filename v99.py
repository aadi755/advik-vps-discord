import discord
from discord import app_commands
from discord.ext import commands
import docker

TOKEN = "Bot_Token_Here"

# Init
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
client = docker.from_env()

# Store SSH sessions in memory
ssh_sessions = {}

# ---------------- DEPLOY ---------------- #
@bot.tree.command(name="deploy", description="Deploy a new VPS with SSH access")
@app_commands.describe(name="Name for the VPS container")
async def deploy(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)

    try:
        # Step 1: Create Ubuntu container
        container = client.containers.run(
            "ubuntu:22.04",
            name=name,
            detach=True,
            tty=True,
            stdin_open=True,
            privileged=True,
        )

        # Step 2: Install tmate
        exit_code, output = container.exec_run(
            "bash -c 'apt-get update && apt-get install -y tmate openssh-client'"
        )
        if exit_code != 0:
            await interaction.followup.send(
                f"✅ Deployed `{name}`, but ❌ failed to install tmate:\n```{output.decode()}```"
            )
            return

        # Step 3: Start tmate session
        container.exec_run("tmate -S /tmp/tmate.sock new-session -d")

        # Step 4: Get SSH session
        exit_code, ssh_output = container.exec_run(
            "tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}'"
        )
        ssh_session = ssh_output.decode().strip()

        if ssh_session:
            ssh_sessions[name] = ssh_session
            await interaction.followup.send(f"✅ VPS `{name}` deployed!\n🔑 SSH: `{ssh_session}`")
        else:
            await interaction.followup.send(f"✅ Deployed `{name}`, but ❌ failed to get SSH session.")

    except Exception as e:
        await interaction.followup.send(f"❌ Error deploying VPS: `{str(e)}`")


# ---------------- LIST ---------------- #
@bot.tree.command(name="list", description="List all running VPS with SSH")
async def list_vps(interaction: discord.Interaction):
    containers = client.containers.list()
    if not containers:
        await interaction.response.send_message("❌ No VPS running.")
        return

    msg = "**🖥️ Active VPS:**\n"
    for c in containers:
        ssh = ssh_sessions.get(c.name, "❌ No SSH session")
        msg += f"- `{c.name}` → {ssh}\n"

    await interaction.response.send_message(msg)


# ---------------- DELETE ---------------- #
@bot.tree.command(name="delete", description="Delete a VPS by name")
@app_commands.describe(name="Name of the VPS to delete")
async def delete_vps(interaction: discord.Interaction, name: str):
    try:
        container = client.containers.get(name)
        container.stop()
        container.remove()
        ssh_sessions.pop(name, None)
        await interaction.response.send_message(f"✅ VPS `{name}` deleted.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: `{str(e)}`")


# ---------------- PURGE ---------------- #
@bot.tree.command(name="purge", description="Delete all VPS")
async def purge_vps(interaction: discord.Interaction):
    containers = client.containers.list()
    if not containers:
        await interaction.response.send_message("❌ No VPS to delete.")
        return

    for c in containers:
        c.stop()
        c.remove()
        ssh_sessions.pop(c.name, None)

    await interaction.response.send_message("✅ Purged all VPS.")


# ---------------- REGEN SSH ---------------- #
@bot.tree.command(name="regen-ssh", description="Regenerate SSH for a VPS")
@app_commands.describe(name="Name of the VPS container")
async def regen_ssh(interaction: discord.Interaction, name: str):
    try:
        container = client.containers.get(name)
        container.exec_run("tmate -S /tmp/tmate.sock new-session -d")
        exit_code, ssh_output = container.exec_run(
            "tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}'"
        )
        ssh_session = ssh_output.decode().strip()

        if ssh_session:
            ssh_sessions[name] = ssh_session
            await interaction.response.send_message(f"🔑 New SSH for `{name}`: `{ssh_session}`")
        else:
            await interaction.response.send_message(f"❌ Failed to regenerate SSH for `{name}`")

    except Exception as e:
        await interaction.response.send_message(f"❌ Error: `{str(e)}`")


# ---------------- START ---------------- #
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
