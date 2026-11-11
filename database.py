import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('SPA_DB_PATH', os.path.join(BASE, 'data', 'spa.db'))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'client' CHECK (role IN ('client','admin','owner')),
    blocked INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS procedures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'Уход',
    duration_min INTEGER NOT NULL,
    price INTEGER NOT NULL,
    image TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    published INTEGER NOT NULL DEFAULT 1 CHECK (published IN (0,1))
);
CREATE TABLE IF NOT EXISTS procedure_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_id INTEGER NOT NULL REFERENCES procedures(id),
    fields TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','superseded')),
    submitted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_procedure_requests_latest ON procedure_requests(procedure_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_procedure_requests_pending
    ON procedure_requests(procedure_id) WHERE status='pending';
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES users(id),
    procedure_id INTEGER NOT NULL REFERENCES procedures(id),
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    child_name TEXT NOT NULL,
    child_age INTEGER NOT NULL,
    children_count INTEGER NOT NULL DEFAULT 1 CHECK (children_count BETWEEN 1 AND 12),
    comment TEXT NOT NULL DEFAULT '',
    payment_method TEXT NOT NULL DEFAULT 'onsite' CHECK (payment_method IN ('deposit','full','onsite')),
    payment_channel TEXT NOT NULL DEFAULT 'onsite' CHECK (payment_channel IN ('kaspi_qr','onsite')),
    deposit_amount INTEGER NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'not_required' CHECK (payment_status IN ('not_required','pending','paid')),
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','confirmed','completed','cancelled','rejected')),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS review_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS event_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    image_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES event_comments(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    author_name TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(id DESC);
CREATE INDEX IF NOT EXISTS idx_event_photos_event ON event_photos(event_id, id);
CREATE INDEX IF NOT EXISTS idx_event_comments_event ON event_comments(event_id, id);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date, status);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def setting(conn, key, default=None):
    row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def available_slots(conn, procedure, day):
    open_h = int(setting(conn, 'open_hour', '10'))
    close_h = int(setting(conn, 'close_hour', '20'))
    step = int(setting(conn, 'slot_step', '30'))
    rows = conn.execute(
        'SELECT b.time, p.duration_min FROM bookings b JOIN procedures p ON p.id = b.procedure_id '
        "WHERE b.date=? AND b.status NOT IN ('cancelled', 'rejected')", (day.isoformat(),)).fetchall()
    busy = []
    for r in rows:
        h, m = map(int, r['time'].split(':'))
        start = h * 60 + m
        busy.append((start, start + r['duration_min']))
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    slots = []
    t = open_h * 60
    while t + procedure['duration_min'] <= close_h * 60:
        end = t + procedure['duration_min']
        if not any(t < b_end and b_start < end for b_start, b_end in busy):
            if day != date.today() or t > now_min:
                slots.append(f'{t // 60:02d}:{t % 60:02d}')
        t += step
    return slots


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return salt.hex() + '$' + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split('$')
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


PROCEDURES = [
    ('Маникюр «Принцесса»', 'Бережный детский маникюр: аккуратная обработка, гипоаллергенный лак и блёстки на выбор.', 'Ноготки', 30, 5000, 'img/proc-nails-v2.png'),
    ('Педикюр «Золушка»', 'Ванночка с морской пеной, нежный педикюр и сияющий лак — ножки как у принцессы.', 'Ноготки', 45, 6000, 'img/proc-pedi-v2.png'),
    ('Причёски «Рапунцель»', 'Косы, локоны, диадемы и короны — сказочный образ для маленькой модницы.', 'Волосы', 40, 7000, 'img/proc-hair-v2.png'),
    ('Аквагрим «Фея»', 'Бабочки, единороги и цветочные узоры безопасными грим-красками на водной основе.', 'Образ', 30, 4000, 'img/proc-face-v2.png'),
    ('СПА-уход «Маленькая принцесса»', 'Молочная ванночка, нежная маска, лёгкий массаж и ароматный чай после процедуры.', 'Уход', 60, 10000, 'img/proc-spa-v2.png'),
    ('СПА-вечеринка «Бал принцесс»', 'Праздник для компании до 6 девочек: маникюр, причёски, аквагрим, фотозона и сладкий стол.', 'Праздники', 120, 35000, 'img/proc-party-v2.png'),
    ('День рождения «Принцессе — ура!»', 'Именинный праздник под ключ: украшения с шарами, маникюр и причёски гостям, торт со свечами и фотозона.', 'Праздники', 90, 25000, 'img/proc-bday-v2.png'),
    ('Выпускной бал «Прощай, детство»', 'Трогательный выпускной для девочек: нарядные образы, локоны и диадемы, фотозона с розами и сладкий стол.', 'Праздники', 120, 30000, 'img/proc-grad-v2.png'),
    ('Пижамная вечеринка «Ночь чудес»', 'Уютный праздник в пижамах: маски для лица, какао с маршмеллоу, сказочный шатёр с гирляндами и лёгкий маникюр.', 'Праздники', 90, 22000, 'img/proc-pajama-v2.png'),
    ('Наурыз мейрамы «Весенняя сказка»', 'Весенний праздник с национальным колоритом: баурсаки, орнаменты, цветочные венки, аквагрим и косички с лентами.', 'Праздники', 90, 20000, 'img/proc-nauryz-v2.png'),
]

REVIEWS = [
    ('Анна, мама Софии', 'Дочка в восторге! Маникюр сделали аккуратно, мастер — настоящая фея. Теперь ходим каждые выходные.', 5),
    ('Светлана, мама Алисы', 'Отмечали день рождения — спа-вечеринка для шести принцесс. Дети счастливы, родители спокойны!', 5),
    ('Марина, мама Евы', 'Очень нежный уход: ребёнок расслабился и чуть не уснул в кресле. Обязательно вернёмся.', 5),
]

SETTINGS = [
    ('salon_name', 'Princess Spa'),
    ('phone', '+7 (775) 123-45-67'),
    ('address', 'г. Актобе, ул. Цветочная, 12'),
    ('hours', 'Ежедневно 10:00–20:00'),
    ('open_hour', '10'),
    ('close_hour', '20'),
    ('slot_step', '30'),
    ('about', 'Princess Spa — спа-салон, созданный специально для маленьких принцесс от 3 до 14 лет. Мы используем только гипоаллергенную детскую косметику, стерильные инструменты и дарим каждой гостье ощущение настоящего сказочного праздника.'),
]


def seed(conn):
    users = [
        ('Екатерина Волкова', 'owner@princess-spa.ru', '+7 (701) 100-00-01', 'owner123', 'owner'),
        ('Мария Смирнова', 'admin@princess-spa.ru', '+7 (701) 100-00-02', 'admin123', 'admin'),
        ('Ольга Петрова', 'client@mail.ru', '+7 (705) 123-45-67', 'client123', 'client'),
    ]
    for name, email, phone, password, role in users:
        conn.execute('INSERT INTO users (name, email, phone, password_hash, role) VALUES (?,?,?,?,?)',
                     (name, email, phone, hash_password(password), role))
    conn.executemany('INSERT INTO procedures (name, description, category, duration_min, price, image) VALUES (?,?,?,?,?,?)',
                     PROCEDURES)
    conn.executemany('INSERT INTO reviews (name, text, rating) VALUES (?,?,?)', REVIEWS)
    conn.executemany('INSERT INTO settings (key, value) VALUES (?,?)', SETTINGS)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    conn.execute('INSERT INTO bookings (client_id, procedure_id, date, time, child_name, child_age, status) VALUES (3,5,?,?,?,?,?)',
                 (yesterday, '15:00', 'София', 7, 'completed'))
    conn.execute('INSERT INTO bookings (client_id, procedure_id, date, time, child_name, child_age, status) VALUES (3,1,?,?,?,?,?)',
                 (tomorrow, '11:00', 'София', 7, 'new'))


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    try:
        migrations = []
        for table, column, definition in (
            ('users', 'blocked', 'INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0,1))'),
            ('procedures', 'published', 'INTEGER NOT NULL DEFAULT 1 CHECK (published IN (0,1))'),
            ('bookings', 'children_count', 'INTEGER NOT NULL DEFAULT 1 CHECK (children_count BETWEEN 1 AND 12)'),
            ('bookings', 'payment_method', "TEXT NOT NULL DEFAULT 'onsite' CHECK (payment_method IN ('deposit','full','onsite'))"),
            ('bookings', 'payment_channel', "TEXT NOT NULL DEFAULT 'onsite' CHECK (payment_channel IN ('kaspi_qr','onsite'))"),
            ('bookings', 'deposit_amount', 'INTEGER NOT NULL DEFAULT 0'),
            ('bookings', 'payment_status', "TEXT NOT NULL DEFAULT 'not_required' CHECK (payment_status IN ('not_required','pending','paid'))"),
        ):
            columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}
            if columns and column not in columns:
                migrations.append((table, column, definition))
        tables = {row['name'] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        booking_schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bookings'").fetchone()
        needs_booking_status_migration = bool(booking_schema and 'rejected' not in booking_schema['sql'].lower())
        needs_payment_method_migration = bool(booking_schema and "'full'" not in booking_schema['sql'].lower())
        if migrations or needs_booking_status_migration or needs_payment_method_migration or (tables and 'procedure_requests' not in tables) or (tables and 'events' not in tables):
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            backup_path = os.path.join(os.path.dirname(DB_PATH),
                                       f'{os.path.basename(DB_PATH)}.{stamp}-{secrets.token_hex(8)}.bak')
            backup = sqlite3.connect(backup_path)
            try:
                conn.backup(backup)
            finally:
                backup.close()
        # Complete the backup before DDL; migrate and seed in one transaction.
        conn.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
        for table, column, definition in migrations:
            # A concurrent initializer may have added the column while we waited.
            columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}
            if column not in columns:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

        # SQLite cannot alter a table CHECK constraint in place. Rebuild the
        # bookings table once so the new 'rejected' state is accepted while
        # preserving every existing booking and its child count.
        booking_schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bookings'").fetchone()
        if booking_schema and ('rejected' not in booking_schema['sql'].lower() or "'full'" not in booking_schema['sql'].lower()):
            conn.execute('ALTER TABLE bookings RENAME TO bookings_before_rejected_migration')
            conn.execute("""CREATE TABLE bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES users(id),
                procedure_id INTEGER NOT NULL REFERENCES procedures(id),
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                child_name TEXT NOT NULL,
                child_age INTEGER NOT NULL,
                children_count INTEGER NOT NULL DEFAULT 1 CHECK (children_count BETWEEN 1 AND 12),
                comment TEXT NOT NULL DEFAULT '',
                payment_method TEXT NOT NULL DEFAULT 'onsite' CHECK (payment_method IN ('deposit','full','onsite')),
                payment_channel TEXT NOT NULL DEFAULT 'onsite' CHECK (payment_channel IN ('kaspi_qr','onsite')),
                deposit_amount INTEGER NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'not_required' CHECK (payment_status IN ('not_required','pending','paid')),
                status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','confirmed','completed','cancelled','rejected')),
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )""")
            conn.execute("""INSERT INTO bookings
                (id, client_id, procedure_id, date, time, child_name, child_age, children_count, comment, payment_method, payment_channel, deposit_amount, payment_status, status, created_at)
                SELECT id, client_id, procedure_id, date, time, child_name, child_age, children_count, comment, payment_method, payment_channel, deposit_amount, payment_status, status, created_at
                FROM bookings_before_rejected_migration""")
            conn.execute('DROP TABLE bookings_before_rejected_migration')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date, status)')

        if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
            seed(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
