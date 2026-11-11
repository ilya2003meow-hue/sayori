import ipaddress
import json
import os
import re
import secrets
import socket
import warnings
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO
from urllib.parse import urlsplit
from flask import has_request_context

import qrcode
from flask import Flask, g, jsonify, redirect, render_template, request, send_file, send_from_directory
from PIL import Image, UnidentifiedImageError

from database import PROCEDURES, available_slots, get_db, hash_password, init_db, setting, verify_password
from assistant import answer as assistant_answer
from translations import LANGS, LANG_LABELS, PROCEDURE_CONTENT, SETTINGS_CONTENT, i18n_json, merged_ui, tr, tr_error

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE, 'public'), static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 27 * 1024 * 1024
init_db()

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
BOOKING_STATUSES = ('new', 'confirmed', 'completed', 'cancelled', 'rejected')
PUBLIC_SETTINGS = ('salon_name', 'phone', 'address', 'hours', 'about')


def https_url_from_env(name):
    value = os.environ.get(name, '').strip()
    if not value:
        return ''
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
        warnings.warn(f'{name} must be a valid HTTPS URL; ignoring it')
        return ''
    return value


PUBLIC_BASE_URL = https_url_from_env('PUBLIC_BASE_URL')
KASPI_PAYMENT_URL = https_url_from_env('KASPI_PAYMENT_URL')


def bad(message, code=400, err_code=None):
    body = {'error': tr_error(message, g.lang)}
    if err_code:
        body['code'] = err_code
    return jsonify(body), code


def public_user(u):
    return {k: u[k] for k in ('id', 'name', 'email', 'phone', 'role')}


@app.before_request
def load_user():
    lang = request.cookies.get('pspa_lang', 'ru')
    g.lang = lang if lang in LANGS else 'ru'
    g.user = None
    token = request.cookies.get('pspa_session')
    if token:
        conn = get_db()
        row = conn.execute(
            'SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id '
            'WHERE s.token=? AND s.expires_at > ? AND u.blocked=0',
            (token, datetime.now().isoformat(timespec='seconds'))).fetchone()
        conn.close()
        if row:
            g.user = dict(row)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.user:
            return bad('Требуется вход', 401)
        return fn(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not g.user:
                return bad('Требуется вход', 401)
            if g.user['role'] not in roles:
                return bad('Недостаточно прав', 403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def session_response(user, status=200):
    token = secrets.token_hex(32)
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        current = conn.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        if not current or current['blocked']:
            return bad('Аккаунт заблокирован. Свяжитесь с администратором', 403)
        user = dict(current)
        conn.execute('INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)',
                     (token, user['id'], (datetime.now() + timedelta(days=7)).isoformat(timespec='seconds')))
    resp = jsonify(user=public_user(user))
    resp.status_code = status
    resp.set_cookie('pspa_session', token, max_age=7 * 24 * 3600, httponly=True, samesite='Lax', secure=bool(PUBLIC_BASE_URL))
    return resp


def role_labels():
    return {r: tr('role_' + r, g.lang) for r in ('client', 'admin', 'owner')}


@app.template_filter('price')
def fmt_price(value):
    return f'{int(value):,}'.replace(',', ' ') + ' ₸'


@app.template_global('_')
def tpl_tr(key):
    return tr(key, g.lang)


@app.template_filter('cat')
def tpl_cat(category):
    return merged_ui(g.lang)['cats'].get(category, category)


def loc_settings(data):
    overlay = SETTINGS_CONTENT.get(g.lang, {})
    return {**data, **{k: v for k, v in overlay.items() if k in data}}


def loc_proc(p):
    procedure_id = p['id']
    if 1 <= procedure_id <= len(PROCEDURES):
        seeded = PROCEDURES[procedure_id - 1]
        if p['name'] == seeded[0] and p['description'] == seeded[1]:
            overlay = PROCEDURE_CONTENT.get(procedure_id, {}).get(g.lang)
            if overlay:
                return {**p, **overlay}
    return p


def loc_proc_name(row):
    procedure_id = row['procedure_id']
    if 1 <= procedure_id <= len(PROCEDURES) and row['procedure_name'] == PROCEDURES[procedure_id - 1][0]:
        overlay = PROCEDURE_CONTENT.get(procedure_id, {}).get(g.lang)
        if overlay:
            row['procedure_name'] = overlay['name']
    return row


@app.context_processor
def inject_globals():
    conn = get_db()
    data = {k: setting(conn, k, '') for k in PUBLIC_SETTINGS}
    conn.close()
    return dict(settings=loc_settings(data), current_user=g.user, role_labels=role_labels(),
                lang=g.lang, lang_labels=LANG_LABELS, i18n_json=i18n_json(g.lang))


def active_procedures(conn, limit=None):
    query = 'SELECT * FROM procedures WHERE active=1 AND published=1 ORDER BY id'
    rows = conn.execute(query + (' LIMIT ?' if limit else ''), (limit,) if limit else ()).fetchall()
    return [loc_proc(dict(r)) for r in rows]


def reviews_with_replies(conn, limit):
    rows = [dict(r) for r in conn.execute('SELECT id, name, text, rating, created_at FROM reviews ORDER BY id DESC LIMIT ?', (limit,))]
    if rows:
        marks = ','.join('?' * len(rows))
        replies = conn.execute(
            'SELECT rr.id, rr.review_id, rr.text, rr.created_at, u.name AS author_name, u.role AS author_role '
            'FROM review_replies rr JOIN users u ON u.id = rr.user_id '
            f'WHERE rr.review_id IN ({marks}) ORDER BY rr.id', [r['id'] for r in rows]).fetchall()
        by_review = {}
        for rep in replies:
            by_review.setdefault(rep['review_id'], []).append(dict(rep))
        for r in rows:
            r['replies'] = by_review.get(r['id'], [])
    return rows


@app.get('/')
def page_home():
    conn = get_db()
    procs = active_procedures(conn, 3)
    revs = reviews_with_replies(conn, 3)
    conn.close()
    return render_template('index.html', procedures=procs, reviews=revs, active_page='home')


@app.get('/procedures')
def page_procedures():
    conn = get_db()
    procs = active_procedures(conn)
    conn.close()
    categories = list(dict.fromkeys(p['category'] for p in procs))
    return render_template('procedures.html', procedures=procs, categories=categories, active_page='procedures')


@app.get('/procedures/<int:procedure_id>')
def page_procedure(procedure_id):
    conn = get_db()
    proc = conn.execute('SELECT * FROM procedures WHERE id=? AND active=1 AND published=1', (procedure_id,)).fetchone()
    conn.close()
    if not proc:
        return render_template('404.html', active_page=''), 404
    return render_template('procedure.html', proc=loc_proc(dict(proc)), active_page='procedures')


@app.get('/about')
def page_about():
    return render_template('about.html', active_page='about')


@app.get('/reviews')
def page_reviews():
    conn = get_db()
    revs = reviews_with_replies(conn, 50)
    conn.close()
    return render_template('reviews.html', reviews=revs, active_page='reviews')


@app.get('/events')
def page_events():
    return render_template('events.html', active_page='events', can_manage_events=bool(g.user and g.user['role'] in ('admin', 'owner')))


def serialize_events(conn):
    event_rows = conn.execute(
        'SELECT e.id, e.title, e.description, e.created_at, COALESCE(u.name, ?) AS author_name '
        'FROM events e LEFT JOIN users u ON u.id=e.created_by ORDER BY e.id DESC LIMIT 100',
        ('Princess Spa',)).fetchall()
    if not event_rows:
        return []
    event_ids = [row['id'] for row in event_rows]
    marks = ','.join('?' * len(event_ids))
    photo_rows = conn.execute(
        f'SELECT id, event_id, image_path FROM event_photos WHERE event_id IN ({marks}) ORDER BY id',
        event_ids).fetchall()
    comment_rows = conn.execute(
        f'SELECT id, event_id, parent_id, author_name, text, created_at '
        f'FROM event_comments WHERE event_id IN ({marks}) ORDER BY id', event_ids).fetchall()

    photos_by_event = {}
    for photo in photo_rows:
        photos_by_event.setdefault(photo['event_id'], []).append(photo['image_path'])

    comments_by_event = {}
    for row in comment_rows:
        item = dict(row)
        item['replies'] = []
        comments_by_event.setdefault(item['event_id'], []).append(item)
    comments_by_id = {
        item['id']: item
        for group in comments_by_event.values()
        for item in group
    }
    for group in comments_by_event.values():
        for item in group:
            if item['parent_id'] is not None:
                parent = comments_by_id.get(item['parent_id'])
                if parent:
                    parent['replies'].append(item)
    result = []
    for row in event_rows:
        result.append({
            **dict(row),
            'photos': photos_by_event.get(row['id'], []),
            'comments': [item for item in comments_by_event.get(row['id'], []) if item['parent_id'] is None],
        })
    return result


def store_event_photo(upload):
    raw = upload.stream.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError('Каждое фото должно быть не больше 5 МБ')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP'):
                    raise ValueError('Поддерживаются фото PNG, JPEG и WebP')
                if source.width * source.height > 16_000_000:
                    raise ValueError('Фото слишком большое: максимум 16 миллионов пикселей')
                source.verify()
            with Image.open(BytesIO(raw)) as source:
                source.load()
                with source.convert('RGBA') as pixels:
                    with Image.frombytes('RGBA', pixels.size, pixels.tobytes()) as clean:
                        encoded = BytesIO()
                        clean.save(encoded, format='WEBP', quality=86, method=5)
    except ValueError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Фото слишком большое: максимум 16 миллионов пикселей')
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError('Не удалось прочитать фото. Загрузите PNG, JPEG или WebP')

    directory = os.path.join(app.static_folder, 'img', 'events')
    os.makedirs(directory, exist_ok=True)
    filename = secrets.token_hex(16) + '.webp'
    path = os.path.join(directory, filename)
    with open(path, 'xb') as target:
        target.write(encoded.getvalue())
    return 'img/events/' + filename, path


@app.get('/api/events')
def api_events():
    with closing(get_db()) as conn:
        return jsonify(serialize_events(conn))


@app.post('/api/events')
@roles_required('admin', 'owner')
def create_event():
    title = (request.form.get('title') or '').strip()
    description = (request.form.get('description') or '').strip()
    uploads = [item for item in request.files.getlist('photos') if item and item.filename]
    if not 3 <= len(title) <= 120:
        return bad('Название мероприятия должно быть от 3 до 120 символов')
    if not 5 <= len(description) <= 4000:
        return bad('Описание мероприятия должно быть от 5 до 4000 символов')
    if not uploads:
        return bad('Добавьте хотя бы одно фото')
    if len(uploads) > 5:
        return bad('Можно добавить не больше 5 фотографий')

    saved = []
    try:
        for upload in uploads:
            saved.append(store_event_photo(upload))
        with closing(get_db()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute(
                'INSERT INTO events (title, description, created_by) VALUES (?,?,?)',
                (title, description, g.user['id']))
            event_id = cur.lastrowid
            conn.executemany(
                'INSERT INTO event_photos (event_id, image_path) VALUES (?,?)',
                [(event_id, item[0]) for item in saved])
            row = conn.execute('SELECT id FROM events WHERE id=?', (event_id,)).fetchone()
            event = next(item for item in serialize_events(conn) if item['id'] == row['id'])
    except ValueError as exc:
        for _, path in saved:
            try:
                os.unlink(path)
            except OSError:
                pass
        return bad(str(exc))
    except Exception:
        for _, path in saved:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise
    return jsonify(event), 201


@app.delete('/api/events/<int:event_id>')
@roles_required('admin', 'owner')
def delete_event(event_id):
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT id FROM events WHERE id=?', (event_id,)).fetchone()
        if not row:
            return bad('Мероприятие не найдено', 404)
        photos = conn.execute('SELECT image_path FROM event_photos WHERE event_id=?', (event_id,)).fetchall()
        conn.execute('DELETE FROM events WHERE id=?', (event_id,))
    event_dir = os.path.realpath(os.path.join(app.static_folder, 'img', 'events'))
    for photo in photos:
        candidate = os.path.realpath(os.path.join(app.static_folder, photo['image_path']))
        if candidate.startswith(event_dir + os.sep):
            try:
                os.unlink(candidate)
            except FileNotFoundError:
                pass
    return jsonify(ok=True)


@app.post('/api/events/<int:event_id>/comments')
@login_required
def add_event_comment(event_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad('Ожидается JSON-объект')
    text = data.get('text')
    parent_id = data.get('parent_id')
    if not isinstance(text, str) or not 2 <= len(text.strip()) <= 1500:
        return bad('Комментарий должен содержать от 2 до 1500 символов')
    if parent_id is not None and (type(parent_id) is not int or parent_id < 1):
        return bad('Некорректный комментарий для ответа')
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT id FROM events WHERE id=?', (event_id,)).fetchone():
            return bad('Мероприятие не найдено', 404)
        if parent_id is not None and not conn.execute(
            'SELECT id FROM event_comments WHERE id=? AND event_id=? AND parent_id IS NULL',
            (parent_id, event_id)).fetchone():
            return bad('На этот комментарий нельзя ответить', 404)
        cur = conn.execute(
            'INSERT INTO event_comments (event_id, parent_id, user_id, author_name, text) VALUES (?,?,?,?,?)',
            (event_id, parent_id, g.user['id'], g.user['name'], text.strip()))
        row = conn.execute(
            'SELECT id, event_id, parent_id, author_name, text, created_at FROM event_comments WHERE id=?',
            (cur.lastrowid,)).fetchone()
    return jsonify({**dict(row), 'replies': []}), 201


def local_network_ip():
    """Return the computer's LAN IPv4 address for QR access from a phone."""
    # Asking the OS which interface it would use for an external route is more
    # reliable than resolving the computer name (which can return 127.0.0.1).
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('1.1.1.1', 80))
        candidate = sock.getsockname()[0]
        address = ipaddress.ip_address(candidate)
        if address.is_private and not address.is_loopback and not address.is_link_local:
            return candidate
    except OSError:
        pass
    finally:
        sock.close()

    # Offline fallback: inspect all IPv4 addresses assigned to the hostname.
    try:
        addresses = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        addresses = []
    for item in addresses:
        candidate = item[4][0]
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.is_private and not address.is_loopback and not address.is_link_local:
            return candidate

    # This fallback keeps the local page usable, but cannot be opened by a
    # second device. The startup instructions explain the LAN requirement.
    return '127.0.0.1'


def phone_visit_url():
    # PUBLIC_BASE_URL makes the QR portable across Wi-Fi, mobile data and
    # other networks. Without it, use the current public host when available.
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip('/') + '/'
    if has_request_context():
        host = request.host.split(':', 1)[0].lower()
        if host in ('localhost', '127.0.0.1', '::1'):
            return f'http://{local_network_ip()}:5000/'
        return request.url_root
    return f'http://{local_network_ip()}:5000/'


@app.get('/contacts')
def page_contacts():
    return render_template('contacts.html', active_page='contacts', phone_url=phone_visit_url())


@app.get('/qr.png')
def site_qr():
    image = qrcode.make(phone_visit_url(), box_size=10, border=4)
    stream = BytesIO()
    image.save(stream, format='PNG')
    stream.seek(0)
    return send_file(stream, mimetype='image/png', download_name='PrincessSpa-QR.png', max_age=0)


@app.get('/login')
def page_login():
    if g.user:
        return redirect('/cabinet' if g.user['role'] == 'client' else '/staff')
    return render_template('login.html', active_page='')


@app.get('/booking/<int:procedure_id>')
def page_booking(procedure_id):
    if not g.user:
        return redirect(f'/login?next=/booking/{procedure_id}')
    conn = get_db()
    proc = conn.execute('SELECT * FROM procedures WHERE id=? AND active=1 AND published=1', (procedure_id,)).fetchone()
    conn.close()
    if not proc:
        return render_template('404.html', active_page=''), 404
    return render_template('booking.html', proc=loc_proc(dict(proc)), active_page='procedures',
                           kaspi_payment_enabled=bool(KASPI_PAYMENT_URL))


@app.get('/payment/<int:booking_id>')
@login_required
def page_payment(booking_id):
    conn = get_db()
    row = conn.execute(
        'SELECT b.*, p.name AS procedure_name, p.price, p.duration_min '
        'FROM bookings b JOIN procedures p ON p.id=b.procedure_id WHERE b.id=?',
        (booking_id,)).fetchone()
    conn.close()
    if not row:
        return render_template('404.html', active_page=''), 404
    booking = dict(row)
    if g.user['role'] == 'client' and booking['client_id'] != g.user['id']:
        return bad('Недостаточно прав', 403)
    if (booking['payment_channel'] != 'kaspi_qr' or booking['payment_method'] == 'onsite'
            or booking['status'] in ('cancelled', 'rejected')):
        return redirect('/cabinet')
    return render_template('payment.html', booking=booking, kaspi_payment_url=KASPI_PAYMENT_URL,
                           active_page='cabinet')


@app.get('/payment/<int:booking_id>/qr.png')
@login_required
def payment_qr(booking_id):
    conn = get_db()
    row = conn.execute('SELECT client_id, payment_channel, payment_method, payment_status, status FROM bookings WHERE id=?',
                       (booking_id,)).fetchone()
    conn.close()
    if not row:
        return bad('Запись не найдена', 404)
    if g.user['role'] == 'client' and row['client_id'] != g.user['id']:
        return bad('Недостаточно прав', 403)
    if (row['payment_channel'] != 'kaspi_qr' or row['payment_method'] == 'onsite'
        or row['payment_status'] != 'pending' or row['status'] in ('cancelled', 'rejected')
        or not KASPI_PAYMENT_URL):
        return bad('QR для оплаты недоступен', 404)
    image = qrcode.make(KASPI_PAYMENT_URL, box_size=10, border=4)
    stream = BytesIO()
    image.save(stream, format='PNG')
    stream.seek(0)
    return send_file(stream, mimetype='image/png', download_name=f'PrincessSpa-payment-{booking_id}.png', max_age=0)


@app.get('/cabinet')
def page_cabinet():
    if not g.user:
        return redirect('/login?next=/cabinet')
    if g.user['role'] != 'client':
        return redirect('/staff')
    return render_template('cabinet.html', active_page='cabinet')


@app.get('/staff')
def page_staff():
    if not g.user:
        return redirect('/login?next=/staff')
    if g.user['role'] not in ('admin', 'owner'):
        return redirect('/?denied=1')
    return render_template('staff.html', active_page='staff')


@app.get('/clients')
def page_clients():
    if not g.user:
        return redirect('/login?next=/clients')
    if g.user['role'] not in ('admin', 'owner'):
        return redirect('/?denied=1')
    return render_template('clients.html', active_page='clients')


@app.post('/api/register')
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    phone = (data.get('phone') or '').strip()
    password = data.get('password') or ''
    if len(name) < 2:
        return bad('Укажите имя (минимум 2 символа)')
    if not EMAIL_RE.match(email):
        return bad('Некорректный e-mail')
    if len(password) < 6:
        return bad('Пароль должен быть не короче 6 символов')
    conn = get_db()
    if conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
        conn.close()
        return bad('Этот e-mail уже зарегистрирован', 409)
    cur = conn.execute('INSERT INTO users (name, email, phone, password_hash, role) VALUES (?,?,?,?,?)',
                       (name, email, phone, hash_password(password), 'client'))
    conn.commit()
    user = dict(conn.execute('SELECT * FROM users WHERE id=?', (cur.lastrowid,)).fetchone())
    conn.close()
    return session_response(user, 201)


@app.post('/api/login')
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    conn.close()
    if not row or not verify_password(password, row['password_hash']):
        return bad('Неверный e-mail или пароль', 401)
    if row['blocked']:
        return bad('Аккаунт заблокирован. Свяжитесь с администратором', 403)
    return session_response(dict(row))


@app.post('/api/logout')
def logout():
    token = request.cookies.get('pspa_session')
    if token:
        conn = get_db()
        conn.execute('DELETE FROM sessions WHERE token=?', (token,))
        conn.commit()
        conn.close()
    resp = jsonify(ok=True)
    resp.delete_cookie('pspa_session')
    return resp


@app.get('/api/me')
def me():
    return jsonify(user=public_user(g.user) if g.user else None)


@app.patch('/api/me')
@login_required
def update_me():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    if len(name) < 2:
        return bad('Укажите имя (минимум 2 символа)')
    if len(phone) > 30:
        return bad('Телефон слишком длинный')
    conn = get_db()
    conn.execute('UPDATE users SET name=?, phone=? WHERE id=?', (name, phone, g.user['id']))
    conn.commit()
    user = dict(conn.execute('SELECT * FROM users WHERE id=?', (g.user['id'],)).fetchone())
    conn.close()
    return jsonify(user=public_user(user))


@app.get('/api/settings')
def public_settings():
    conn = get_db()
    data = {k: setting(conn, k, '') for k in PUBLIC_SETTINGS}
    conn.close()
    return jsonify(loc_settings(data))


@app.get('/api/procedures')
def procedures():
    conn = get_db()
    rows = conn.execute('SELECT * FROM procedures WHERE active=1 AND published=1 ORDER BY id').fetchall()
    conn.close()
    return jsonify([loc_proc(dict(r)) for r in rows])


@app.get('/api/reviews')
def reviews():
    try:
        limit = int(request.args.get('limit', 6))
    except (TypeError, ValueError):
        limit = 6
    limit = max(1, min(limit, 50))
    conn = get_db()
    rows = reviews_with_replies(conn, limit)
    conn.close()
    response = jsonify(rows)
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.post('/api/reviews')
@login_required
def add_review():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    try:
        rating = int(data.get('rating', 0))
    except (TypeError, ValueError):
        rating = 0
    if not 5 <= len(text) <= 1000:
        return bad('Отзыв должен быть от 5 до 1000 символов')
    if not 1 <= rating <= 5:
        return bad('Оценка должна быть от 1 до 5')
    conn = get_db()
    cur = conn.execute('INSERT INTO reviews (user_id, name, text, rating) VALUES (?,?,?,?)',
                       (g.user['id'], g.user['name'], text, rating))
    conn.commit()
    review = dict(conn.execute(
        'SELECT id, name, text, rating, created_at FROM reviews WHERE id=?', (cur.lastrowid,)
    ).fetchone())
    conn.close()
    review['replies'] = []
    return jsonify(review), 201


@app.post('/api/reviews/<int:review_id>/replies')
@login_required
def add_review_reply(review_id):
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not 2 <= len(text) <= 1000:
        return bad('Ответ должен быть от 2 до 1000 символов')
    conn = get_db()
    if not conn.execute('SELECT id FROM reviews WHERE id=?', (review_id,)).fetchone():
        conn.close()
        return bad('Отзыв не найден', 404)
    cur = conn.execute('INSERT INTO review_replies (review_id, user_id, text) VALUES (?,?,?)',
                       (review_id, g.user['id'], text))
    conn.commit()
    reply = dict(conn.execute(
        'SELECT rr.id, rr.text, rr.created_at, u.name AS author_name, u.role AS author_role '
        'FROM review_replies rr JOIN users u ON u.id = rr.user_id WHERE rr.id=?', (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(reply), 201


@app.post('/api/assistant')
def api_assistant():
    data = request.get_json(silent=True) or {}
    message = str(data.get('message') or '')[:500]
    return jsonify(assistant_answer(message, g.lang, g.user))


def parse_day(value):
    if not DATE_RE.match(value or ''):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@app.get('/api/slots')
def slots():
    try:
        procedure_id = int(request.args.get('procedure_id', 0))
    except ValueError:
        return bad('Некорректная процедура')
    day = parse_day(request.args.get('date', ''))
    if not day:
        return bad('Некорректная дата')
    if day < date.today() or day > date.today() + timedelta(days=30):
        return bad('Запись возможна на ближайшие 30 дней')
    conn = get_db()
    proc = conn.execute('SELECT * FROM procedures WHERE id=? AND active=1 AND published=1', (procedure_id,)).fetchone()
    if not proc:
        conn.close()
        return bad('Процедура не найдена', 404)
    result = available_slots(conn, proc, day)
    conn.close()
    return jsonify(slots=result)


@app.post('/api/bookings')
@login_required
def create_booking():
    data = request.get_json(silent=True) or {}
    try:
        procedure_id = int(data.get('procedure_id', 0))
        child_age = int(data.get('child_age', 0))
        children_count = int(data.get('children_count', 1))
    except (TypeError, ValueError):
        return bad('Некорректные данные записи')
    child_name = (data.get('child_name') or '').strip()
    comment = (data.get('comment') or '').strip()[:500]
    # Online payment is always an explicit choice; old clients that omit this
    # field keep working with the safe on-site default.
    payment_channel = data.get('payment_channel', 'onsite')
    if payment_channel not in ('kaspi_qr', 'onsite'):
        return bad('Выберите способ оплаты')
    if payment_channel == 'kaspi_qr':
        if not KASPI_PAYMENT_URL:
            return bad('Оплата Kaspi QR пока не настроена. Выберите оплату на месте.', 503, err_code='kaspi_not_configured')
        payment_method = data.get('payment_method', 'deposit')
        if payment_method not in ('deposit', 'full'):
            return bad('Выберите сумму предоплаты')
    else:
        payment_method = 'onsite'
    day = parse_day(data.get('date'))
    time = data.get('time') or ''
    if len(child_name) < 2:
        return bad('Укажите имя ребёнка')
    if not 2 <= child_age <= 17:
        return bad('Возраст ребёнка должен быть от 2 до 17 лет')
    if not 1 <= children_count <= 12:
        return bad('Количество детей должно быть от 1 до 12')
    if not day or day < date.today() or day > date.today() + timedelta(days=30):
        return bad('Выберите дату в ближайшие 30 дней')
    conn = get_db()
    conn.execute('BEGIN IMMEDIATE')
    proc = conn.execute('SELECT * FROM procedures WHERE id=? AND active=1 AND published=1', (procedure_id,)).fetchone()
    if not proc:
        conn.rollback()
        conn.close()
        return bad('Процедура не найдена', 404)
    if time not in available_slots(conn, proc, day):
        conn.rollback()
        conn.close()
        return bad('Это время уже занято, выберите другое', 409, err_code='slot_taken')
    total_price = int(proc['price'])
    # Round 20% to the nearest tenge using conventional half-up rounding.
    deposit_amount = (((total_price * 20 + 50) // 100) if payment_method == 'deposit'
                      else total_price if payment_method == 'full' else 0)
    payment_status = 'pending' if payment_channel == 'kaspi_qr' else 'not_required'
    cur = conn.execute(
        'INSERT INTO bookings (client_id, procedure_id, date, time, child_name, child_age, children_count, comment, payment_method, payment_channel, deposit_amount, payment_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (g.user['id'], procedure_id, day.isoformat(), time, child_name, child_age, children_count, comment, payment_method, payment_channel, deposit_amount, payment_status))
    conn.commit()
    booking_id = cur.lastrowid
    conn.close()
    return jsonify(id=booking_id, payment_method=payment_method, payment_channel=payment_channel,
                   deposit_amount=deposit_amount, payment_status=payment_status,
                   payment_url=f'/payment/{booking_id}' if payment_channel == 'kaspi_qr' else None), 201


@app.get('/api/my/bookings')
@login_required
def my_bookings():
    conn = get_db()
    rows = conn.execute(
        'SELECT b.*, p.name AS procedure_name, p.duration_min, p.price, p.image, p.category '
        'FROM bookings b JOIN procedures p ON p.id = b.procedure_id '
        'WHERE b.client_id=? ORDER BY b.date DESC, b.time DESC LIMIT 100', (g.user['id'],)).fetchall()
    conn.close()
    return jsonify([loc_proc_name(dict(r)) for r in rows])


@app.post('/api/bookings/<int:booking_id>/cancel')
@login_required
def cancel_booking(booking_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone()
    if not row:
        conn.close()
        return bad('Запись не найдена', 404)
    if g.user['role'] == 'client' and row['client_id'] != g.user['id']:
        conn.close()
        return bad('Недостаточно прав', 403)
    if row['status'] not in ('new', 'confirmed'):
        conn.close()
        return bad('Эту запись уже нельзя отменить')
    conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.get('/api/admin/bookings')
@roles_required('admin', 'owner')
def admin_bookings():
    query = ('SELECT b.*, p.name AS procedure_name, p.price, p.duration_min, '
             'u.name AS client_name, u.phone AS client_phone, u.email AS client_email '
             'FROM bookings b JOIN procedures p ON p.id = b.procedure_id JOIN users u ON u.id = b.client_id')
    conditions, params = [], []
    status = request.args.get('status')
    day = request.args.get('date')
    if status in BOOKING_STATUSES:
        conditions.append('b.status=?')
        params.append(status)
    if day and DATE_RE.match(day):
        conditions.append('b.date=?')
        params.append(day)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY b.date DESC, b.time DESC LIMIT 200'
    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([loc_proc_name(dict(r)) for r in rows])


@app.patch('/api/admin/bookings/<int:booking_id>')
@roles_required('admin', 'owner')
def admin_set_status(booking_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    row = conn.execute('SELECT id, status, payment_channel, payment_status FROM bookings WHERE id=?',
                       (booking_id,)).fetchone()
    if not row:
        conn.close()
        return bad('Запись не найдена', 404)

    if 'payment_status' in data:
        if data.get('payment_status') != 'paid':
            conn.close()
            return bad('Можно подтвердить только полученную оплату')

        if (row['payment_channel'] == 'kaspi_qr' and row['payment_status'] == 'pending'
                and row['status'] not in ('cancelled', 'rejected')):
            expected_payment_status = 'pending'
        elif (row['payment_channel'] == 'onsite' and row['payment_status'] == 'not_required'
                and row['status'] in ('confirmed', 'completed')):
            # On-site payment can be marked received after the appointment has
            # been accepted; it does not require a prepayment from the client.
            expected_payment_status = 'not_required'
        else:
            conn.close()
            return bad('Для этой записи сейчас нельзя подтвердить оплату', 409)

        updated = conn.execute(
            "UPDATE bookings SET payment_status='paid' WHERE id=? AND payment_channel=?"
            " AND payment_status=? AND status=?",
            (booking_id, row['payment_channel'], expected_payment_status, row['status']))
        if updated.rowcount != 1:
            conn.close()
            return bad('Статус оплаты уже изменился. Обновите список записей.', 409)
        conn.commit()
        conn.close()
        return jsonify(ok=True, payment_status='paid')

    status = data.get('status')
    if status not in BOOKING_STATUSES:
        conn.close()
        return bad('Некорректный статус')
    allowed_transitions = {
        'new': {'confirmed', 'rejected', 'cancelled'},
        'confirmed': {'completed', 'cancelled'},
    }
    if status not in allowed_transitions.get(row['status'], set()):
        conn.close()
        return bad('Нельзя изменить статус этой записи таким образом', 409)
    conn.execute('UPDATE bookings SET status=? WHERE id=?', (status, booking_id))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


PROCEDURE_FIELDS = ('name', 'description', 'category', 'duration_min', 'price', 'image', 'active')


def valid_procedure_image(image):
    if not image:
        return True
    if len(image) > 255 or '\\' in image or ':' in image or '\x00' in image:
        return False
    parts = image.split('/')
    if parts[0] != 'img' or any(part in ('', '.', '..') for part in parts):
        return False
    if os.path.splitext(image)[1].lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
        return False
    root = os.path.realpath(os.path.join(app.static_folder, 'img'))
    path = os.path.realpath(os.path.join(app.static_folder, *parts))
    try:
        return os.path.commonpath((root, path)) == root and os.path.isfile(path)
    except ValueError:
        return False


def validate_procedure(data):
    if not isinstance(data, dict):
        return None, 'Ожидается JSON-объект'
    strings = {key: data.get(key, default) for key, default in (
        ('name', ''), ('description', ''), ('category', 'Уход'), ('image', ''))}
    if any(not isinstance(value, str) for value in strings.values()):
        return None, 'Текстовые поля должны быть строками'
    name, description, category, image = (strings[key].strip() for key in strings)
    if not 3 <= len(name) <= 160:
        return None, 'Название процедуры — от 3 до 160 символов'
    if len(description) > 4000:
        return None, 'Описание — максимум 4000 символов'
    if not 1 <= len(category) <= 80:
        return None, 'Категория — от 1 до 80 символов'
    if not valid_procedure_image(image):
        return None, 'Некорректный путь изображения'
    duration, price = data.get('duration_min', 0), data.get('price', 0)
    if type(duration) is not int or type(price) is not int:
        return None, 'Длительность и цена должны быть целыми числами'
    if not 15 <= duration <= 240:
        return None, 'Длительность должна быть от 15 до 240 минут'
    if not 0 < price <= 100000:
        return None, 'Цена должна быть от 1 до 100 000 ₸'
    active = data.get('active', 1)
    if type(active) not in (bool, int) or active not in (0, 1):
        return None, 'Активность должна быть 0 или 1'
    return dict(name=name, description=description, category=category,
                duration_min=duration, price=price, image=image, active=int(active)), None


@app.post('/api/admin/images')
@roles_required('admin')
def admin_upload_image():
    upload = request.files.get('image')
    if upload is None:
        return bad('Выберите изображение')
    raw = upload.stream.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        return bad('Изображение больше 5 МиБ', 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP'):
                    return bad('Нужен корректный PNG, JPEG или WebP')
                if source.width * source.height > 16_000_000:
                    return bad('Изображение больше 16 миллионов пикселей')
                source.verify()
            with Image.open(BytesIO(raw)) as source:
                source.load()
                with source.convert('RGBA') as pixels:
                    # A fresh pixel-only image cannot carry EXIF, comments or ICC data.
                    with Image.frombytes('RGBA', pixels.size, pixels.tobytes()) as clean:
                        encoded = BytesIO()
                        clean.save(encoded, format='PNG')
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return bad('Изображение больше 16 миллионов пикселей')
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return bad('Нужен корректный PNG, JPEG или WebP')
    directory = os.path.join(app.static_folder, 'img', 'uploads')
    os.makedirs(directory, exist_ok=True)
    while True:
        filename = secrets.token_hex(16) + '.png'
        path = os.path.join(directory, filename)
        try:
            target = open(path, 'xb')
            break
        except FileExistsError:
            continue
    try:
        with target:
            target.write(encoded.getvalue())
    except Exception:
        os.unlink(path)
        raise
    return jsonify(image='img/uploads/' + filename), 201


def revision_fields(conn, procedure):
    pending = conn.execute(
        "SELECT fields FROM procedure_requests WHERE procedure_id=? AND status='pending'",
        (procedure['id'],)).fetchone()
    return json.loads(pending['fields']) if pending else {key: procedure[key] for key in PROCEDURE_FIELDS}


def submit_procedure_revision(conn, procedure_id, fields):
    # The caller holds BEGIN IMMEDIATE through superseding and insertion.
    conn.execute("UPDATE procedure_requests SET status='superseded' WHERE procedure_id=? AND status='pending'",
                 (procedure_id,))
    cur = conn.execute(
        'INSERT INTO procedure_requests (procedure_id, fields, submitted_by) VALUES (?,?,?)',
        (procedure_id, json.dumps(fields, ensure_ascii=False), g.user['id']))
    return cur.lastrowid


@app.get('/api/admin/procedures')
@roles_required('admin', 'owner')
def admin_procedures():
    with closing(get_db()) as conn:
        rows = conn.execute(
            'SELECT p.*, r.id AS request_id, r.status AS request_status, r.fields AS request_fields '
            'FROM procedures p LEFT JOIN procedure_requests r ON r.id = '
            '(SELECT MAX(id) FROM procedure_requests WHERE procedure_id=p.id) ORDER BY p.id').fetchall()
    result = []
    for row in rows:
        procedure = dict(row)
        request_id = procedure.pop('request_id')
        status = procedure.pop('request_status')
        fields = procedure.pop('request_fields')
        procedure['request'] = ({'id': request_id, 'status': status, 'fields': json.loads(fields)}
                                if request_id is not None else None)
        result.append(procedure)
    return jsonify(result)


@app.post('/api/admin/procedures')
@roles_required('admin')
def admin_add_procedure():
    fields, error = validate_procedure(request.get_json(silent=True))
    if error:
        return bad(error)
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        cur = conn.execute(
            'INSERT INTO procedures (name, description, category, duration_min, price, image, active, published) '
            'VALUES (:name, :description, :category, :duration_min, :price, :image, :active, 0)', fields)
        procedure_id = cur.lastrowid
        request_id = submit_procedure_revision(conn, procedure_id, fields)
    return jsonify(id=procedure_id, request_id=request_id), 201


@app.patch('/api/admin/procedures/<int:procedure_id>')
@roles_required('admin')
def admin_edit_procedure(procedure_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad('Ожидается JSON-объект')
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM procedures WHERE id=?', (procedure_id,)).fetchone()
        if not row:
            return bad('Процедура не найдена', 404)
        proposed = revision_fields(conn, row)
        proposed.update({key: data[key] for key in PROCEDURE_FIELDS if key in data})
        fields, error = validate_procedure(proposed)
        if error:
            return bad(error)
        request_id = submit_procedure_revision(conn, procedure_id, fields)
    return jsonify(ok=True, request_id=request_id)


@app.delete('/api/admin/procedures/<int:procedure_id>')
@roles_required('admin')
def admin_delete_procedure(procedure_id):
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM procedures WHERE id=?', (procedure_id,)).fetchone()
        if not row:
            return bad('Процедура не найдена', 404)
        fields = revision_fields(conn, row)
        fields['active'] = 0
        request_id = submit_procedure_revision(conn, procedure_id, fields)
    return jsonify(ok=True, request_id=request_id)


@app.get('/api/owner/procedure-requests')
@roles_required('owner')
def owner_procedure_requests():
    with closing(get_db()) as conn:
        rows = conn.execute(
            'SELECT p.*, r.id AS request_id, r.fields AS request_fields '
            'FROM procedure_requests r JOIN procedures p ON p.id=r.procedure_id '
            "WHERE r.status='pending' ORDER BY r.id").fetchall()
    result = []
    for row in rows:
        current = dict(row)
        request_id = current.pop('request_id')
        fields = json.loads(current.pop('request_fields'))
        result.append({'id': request_id, 'procedure_id': current['id'], 'fields': fields,
                       'current': current if current['published'] else None})
    return jsonify(result)


@app.post('/api/owner/procedure-requests/<int:request_id>/decision')
@roles_required('owner')
def owner_procedure_decision(request_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('decision') not in ('approve', 'reject'):
        return bad('Некорректное решение')
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        revision = conn.execute('SELECT * FROM procedure_requests WHERE id=?', (request_id,)).fetchone()
        if not revision:
            return bad('Заявка не найдена', 404)
        if revision['status'] != 'pending':
            return bad('Заявка уже рассмотрена или заменена', 409)
        if data['decision'] == 'approve':
            proposed = json.loads(revision['fields'])
            fields = {key: proposed[key] for key in PROCEDURE_FIELDS}
            fields['id'] = revision['procedure_id']
            conn.execute(
                'UPDATE procedures SET name=:name, description=:description, category=:category, '
                'duration_min=:duration_min, price=:price, image=:image, active=:active, published=1 WHERE id=:id',
                fields)
        status = 'approved' if data['decision'] == 'approve' else 'rejected'
        conn.execute('UPDATE procedure_requests SET status=? WHERE id=?', (status, request_id))
    return jsonify(ok=True)


@app.get('/api/admin/clients')
@roles_required('admin', 'owner')
def admin_clients():
    conn = get_db()
    rows = conn.execute(
        "SELECT u.id, u.name, u.email, u.phone, u.blocked, u.created_at, COUNT(b.id) AS bookings_count, "
        "COALESCE(SUM(CASE WHEN b.status='completed' THEN p.price ELSE 0 END), 0) AS total_spent "
        "FROM users u LEFT JOIN bookings b ON b.client_id = u.id "
        "LEFT JOIN procedures p ON p.id = b.procedure_id "
        "WHERE u.role='client' GROUP BY u.id ORDER BY u.id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.patch('/api/admin/clients/<int:user_id>/block')
@roles_required('admin')
def admin_block_client(user_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get('blocked')) is not bool:
        return bad('Поле blocked должно быть true или false')
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        user = conn.execute('SELECT role FROM users WHERE id=?', (user_id,)).fetchone()
        if not user:
            return bad('Клиент не найден', 404)
        if user['role'] != 'client':
            return bad('Нельзя блокировать сотрудников', 403)
        conn.execute('UPDATE users SET blocked=? WHERE id=?', (int(data['blocked']), user_id))
        if data['blocked']:
            conn.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    return jsonify(ok=True)


@app.delete('/api/admin/clients/<int:user_id>')
@roles_required('admin')
def admin_delete_client(user_id):
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        user = conn.execute('SELECT role FROM users WHERE id=?', (user_id,)).fetchone()
        if not user:
            return bad('Клиент не найден', 404)
        if user['role'] != 'client':
            return bad('Можно удалить только аккаунт клиента', 403)

        # Remove records that reference this user before deleting the account.
        conn.execute('DELETE FROM review_replies WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM reviews WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM bookings WHERE client_id=?', (user_id,))
        conn.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    return jsonify(ok=True)


@app.delete('/api/admin/reviews/<int:review_id>')
@roles_required('admin')
def admin_delete_review(review_id):
    with closing(get_db()) as conn, conn:
        deleted = conn.execute('DELETE FROM reviews WHERE id=?', (review_id,))
        if not deleted.rowcount:
            return bad('Отзыв не найден', 404)
    return jsonify(ok=True)


@app.get('/api/owner/stats')
@roles_required('owner')
def owner_stats():
    conn = get_db()
    revenue = conn.execute(
        "SELECT COALESCE(SUM(p.price), 0) FROM bookings b JOIN procedures p ON p.id = b.procedure_id "
        "WHERE b.status='completed'").fetchone()[0]
    week_ago = (date.today() - timedelta(days=6)).isoformat()
    revenue_week = conn.execute(
        "SELECT COALESCE(SUM(p.price), 0) FROM bookings b JOIN procedures p ON p.id = b.procedure_id "
        "WHERE b.status='completed' AND b.date >= ?", (week_ago,)).fetchone()[0]
    status_counts = {r['status']: r['c'] for r in conn.execute(
        'SELECT status, COUNT(*) AS c FROM bookings GROUP BY status')}
    clients_count = conn.execute("SELECT COUNT(*) FROM users WHERE role='client'").fetchone()[0]
    today_upcoming = conn.execute(
        "SELECT COUNT(*) FROM bookings WHERE date=? AND status IN ('new','confirmed')",
        (date.today().isoformat(),)).fetchone()[0]
    top = conn.execute(
        'SELECT p.id AS procedure_id, p.name AS procedure_name, COUNT(*) AS cnt, '
        "COALESCE(SUM(CASE WHEN b.status='completed' THEN p.price ELSE 0 END), 0) AS revenue "
        'FROM bookings b JOIN procedures p ON p.id = b.procedure_id '
        'GROUP BY p.id ORDER BY cnt DESC LIMIT 5').fetchall()
    conn.close()
    return jsonify(revenue=revenue, revenue_week=revenue_week, status_counts=status_counts,
                   clients_count=clients_count, today_upcoming=today_upcoming,
                   top_procedures=[loc_proc_name(dict(r)) for r in top])


@app.get('/api/owner/staff')
@roles_required('owner')
def owner_staff():
    conn = get_db()
    rows = conn.execute("SELECT id, name, email, phone, role, created_at FROM users WHERE role IN ('admin','owner') ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.post('/api/owner/staff')
@roles_required('owner')
def owner_add_staff():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    phone = (data.get('phone') or '').strip()
    password = data.get('password') or ''
    if len(name) < 2:
        return bad('Укажите имя')
    if not EMAIL_RE.match(email):
        return bad('Некорректный e-mail')
    if len(password) < 6:
        return bad('Пароль должен быть не короче 6 символов')
    conn = get_db()
    if conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
        conn.close()
        return bad('Этот e-mail уже зарегистрирован', 409)
    cur = conn.execute("INSERT INTO users (name, email, phone, password_hash, role) VALUES (?,?,?,?, 'admin')",
                       (name, email, phone, hash_password(password)))
    conn.commit()
    conn.close()
    return jsonify(id=cur.lastrowid), 201


@app.delete('/api/owner/staff/<int:user_id>')
@roles_required('owner')
def owner_delete_staff(user_id):
    if user_id == g.user['id']:
        return bad('Нельзя удалить самого себя')
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE id=? AND role='admin'", (user_id,)).fetchone()
    if not row:
        conn.close()
        return bad('Администратор не найден', 404)
    conn.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith('/api/'):
        return bad('Не найдено', 404)
    return render_template('404.html', active_page=''), 404


@app.errorhandler(413)
def request_too_large(_):
    return bad('Файл слишком большой', 413)


@app.errorhandler(500)
def server_error(_):
    return bad('Внутренняя ошибка сервера', 500)


if __name__ == '__main__':
    print('Princess Spa: http://localhost:5000')
    print('Phone / QR: ' + phone_visit_url())
    if PUBLIC_BASE_URL:
        print('Public QR is configured for any network: ' + PUBLIC_BASE_URL)
    else:
        print('For a QR that works outside the local Wi-Fi, set PUBLIC_BASE_URL to your HTTPS domain and deploy the site.')
    app.run(host='0.0.0.0', port=5000, debug=False)