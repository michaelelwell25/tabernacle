import os
from flask import Blueprint, request, jsonify, abort
from app.services.discord_service import verify_signature, handle_interaction, register_commands

bp = Blueprint('discord', __name__, url_prefix='/discord')


@bp.route('/interactions', methods=['POST'])
def interactions():
    public_key = os.environ.get('DISCORD_PUBLIC_KEY')
    if not public_key:
        abort(503)

    signature = request.headers.get('X-Signature-Ed25519', '')
    timestamp = request.headers.get('X-Signature-Timestamp', '')
    if not verify_signature(public_key, signature, timestamp, request.data):
        abort(401)

    return jsonify(handle_interaction(request.get_json(silent=True) or {}))


@bp.cli.command('register-commands')
def register_commands_cli():
    """Register slash commands with Discord (needs DISCORD_APP_ID and DISCORD_BOT_TOKEN)."""
    names = register_commands()
    print(f'Registered commands: {", ".join(names)}')
