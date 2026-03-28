from flask import Blueprint, request, redirect, url_for, render_template, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from app.models.invite import InviteToken
from app.models.player import Player
from app.models.pod_assignment import PodAssignment

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)

        flash('Invalid email or password', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    token_str = request.args.get('token', '')
    invite = None
    if token_str:
        invite = InviteToken.query.filter_by(token=token_str, used_by_id=None).first()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        token_str = request.form.get('token', '')

        if token_str:
            invite = InviteToken.query.filter_by(token=token_str, used_by_id=None).first()

        if not name or not email or not password:
            flash('All fields are required', 'error')
            return render_template('auth/register.html', invite=invite, token=token_str)

        if password != confirm:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html', invite=invite, token=token_str)

        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('auth/register.html', invite=invite, token=token_str)

        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists', 'error')
            return render_template('auth/register.html', invite=invite, token=token_str)

        user = User(name=name, email=email)
        user.set_password(password)

        # First user gets admin
        if User.query.count() == 0:
            user.role = 'admin'
        elif invite:
            user.role = invite.role
            invite.used_by_id = user.id
        else:
            user.role = 'player'

        db.session.add(user)
        db.session.commit()

        if invite:
            invite.used_by_id = user.id
            db.session.commit()

        login_user(user, remember=True)
        flash(f'Welcome to Tabernacle, {name}!', 'success')
        return redirect(url_for('index'))

    return render_template('auth/register.html', invite=invite, token=token_str)


@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()

        if not name or not email:
            flash('Name and email are required', 'error')
            return render_template('auth/profile.html')

        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != current_user.id:
            flash('That email is already in use', 'error')
            return render_template('auth/profile.html')

        current_user.name = name
        current_user.email = email
        db.session.commit()
        flash('Profile updated', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html')


@auth_bp.route('/profile/password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    if not current_user.check_password(current_pw):
        flash('Current password is incorrect', 'error')
        return redirect(url_for('auth.profile'))

    if not new_pw or len(new_pw) < 6:
        flash('New password must be at least 6 characters', 'error')
        return redirect(url_for('auth.profile'))

    if new_pw != confirm_pw:
        flash('New passwords do not match', 'error')
        return redirect(url_for('auth.profile'))

    current_user.set_password(new_pw)
    db.session.commit()
    flash('Password changed', 'success')
    return redirect(url_for('auth.profile'))


@auth_bp.route('/my-stats')
@login_required
def my_stats():
    player_records = current_user.player_records.all()

    tournaments_played = len(player_records)
    total_matches = 0
    total_wins = 0
    total_pods = 0
    tournament_history = []

    for p in player_records:
        t = p.tournament
        assignments = p.pod_assignments.filter(PodAssignment.points_earned.isnot(None)).all()
        matches = len(assignments)
        wins = sum(1 for a in assignments if a.placement == 1)
        total_matches += matches
        total_wins += wins
        total_pods += matches

        tournament_history.append({
            'tournament': t,
            'matches': matches,
            'wins': wins,
            'points': p.get_total_points(),
            'commander': p.commander,
            'dropped': p.dropped,
        })

    win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0

    return render_template('auth/stats.html',
        tournaments_played=tournaments_played,
        total_matches=total_matches,
        total_wins=total_wins,
        win_rate=win_rate,
        tournament_history=tournament_history,
    )
