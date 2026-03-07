import os
from flask import Blueprint, request, session, redirect, url_for, render_template_string, current_app

auth_bp = Blueprint('auth', __name__)

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tabernacle — Admin Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #1a1a2e;
            color: #e0e0e0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .login-card {
            background: #16213e;
            border-radius: 12px;
            padding: 2.5rem;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        h1 {
            text-align: center;
            margin-bottom: 0.25rem;
            color: #e94560;
            font-size: 1.8rem;
        }
        .subtitle {
            text-align: center;
            color: #888;
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
        }
        .error {
            background: rgba(233, 69, 96, 0.15);
            border: 1px solid #e94560;
            color: #e94560;
            padding: 0.75rem;
            border-radius: 6px;
            margin-bottom: 1rem;
            text-align: center;
        }
        label {
            display: block;
            margin-bottom: 0.4rem;
            font-weight: 500;
        }
        input[type="password"] {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #333;
            border-radius: 6px;
            background: #0f3460;
            color: #e0e0e0;
            font-size: 1rem;
            margin-bottom: 1.25rem;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #e94560;
        }
        button {
            width: 100%;
            padding: 0.75rem;
            background: #e94560;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover { background: #c73652; }
    </style>
</head>
<body>
    <div class="login-card">
        <h1>Tabernacle</h1>
        <p class="subtitle">Tournament Admin</p>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" autofocus required>
            <button type="submit">Log In</button>
        </form>
    </div>
</body>
</html>
'''


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    admin_pw = os.environ.get('ADMIN_PASSWORD') or current_app.config.get('ADMIN_PASSWORD')
    if not admin_pw:
        session['authenticated'] = True
        return redirect(url_for('tournament.list_tournaments'))

    error = None
    if request.method == 'POST':
        if request.form.get('password') == admin_pw:
            session['authenticated'] = True
            session.permanent = True
            next_url = request.args.get('next') or url_for('tournament.list_tournaments')
            return redirect(next_url)
        error = 'Incorrect password'

    return render_template_string(LOGIN_TEMPLATE, error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
