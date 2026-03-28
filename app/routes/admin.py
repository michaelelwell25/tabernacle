from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import current_user
from app import db
from app.models.user import User
from app.models.tournament import Tournament
from app.models.league import League
from app.models.invite import InviteToken

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.before_request
def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin():
        abort(403)


@bp.route('/')
def dashboard():
    users = User.query.order_by(User.created_at.desc()).all()
    user_data = []
    for u in users:
        user_data.append({
            'user': u,
            'tournament_count': u.tournaments.count(),
            'league_count': u.leagues.count(),
        })
    invites = InviteToken.query.order_by(InviteToken.created_at.desc()).all()
    return render_template('admin/dashboard.html', user_data=user_data, invites=invites)


@bp.route('/users/<int:user_id>/toggle-role', methods=['POST'])
def toggle_role(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You can't change your own role.", 'error')
        return redirect(url_for('admin.dashboard'))
    if user.role == 'admin':
        user.role = 'to'
    elif user.role == 'to':
        user.role = 'player'
    else:
        user.role = 'to'
    db.session.commit()
    flash(f'{user.name} is now {user.role.upper()}.', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You can't delete yourself.", 'error')
        return redirect(url_for('admin.dashboard'))

    # Reassign tournaments and leagues to current admin
    Tournament.query.filter_by(owner_id=user.id).update({'owner_id': current_user.id})
    League.query.filter_by(owner_id=user.id).update({'owner_id': current_user.id})

    db.session.delete(user)
    db.session.commit()
    flash(f'{user.name} has been deleted. Their tournaments/leagues were reassigned to you.', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/invites/create', methods=['POST'])
def create_invite():
    invite = InviteToken(role='to')
    db.session.add(invite)
    db.session.commit()
    flash('TO invite link created!', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/invites/<int:invite_id>/delete', methods=['POST'])
def delete_invite(invite_id):
    invite = InviteToken.query.get_or_404(invite_id)
    db.session.delete(invite)
    db.session.commit()
    flash('Invite deleted.', 'success')
    return redirect(url_for('admin.dashboard'))
