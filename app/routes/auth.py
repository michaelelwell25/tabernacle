from flask import Blueprint, request, redirect, url_for, render_template, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('tournament.list_tournaments'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_url = request.args.get('next') or url_for('tournament.list_tournaments')
            return redirect(next_url)

        flash('Invalid email or password', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('tournament.list_tournaments'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not name or not email or not password:
            flash('All fields are required', 'error')
            return render_template('auth/register.html')

        if password != confirm:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists', 'error')
            return render_template('auth/register.html')

        user = User(name=name, email=email)
        user.set_password(password)

        # First user gets admin role
        if User.query.count() == 0:
            user.role = 'admin'

        db.session.add(user)
        db.session.commit()

        login_user(user, remember=True)
        flash(f'Welcome to Tabernacle, {name}!', 'success')
        return redirect(url_for('tournament.list_tournaments'))

    return render_template('auth/register.html')


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
