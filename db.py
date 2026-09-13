import os
from contextlib import contextmanager
from decimal import Decimal
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    order_details TEXT NOT NULL,
    order_date DATE NOT NULL DEFAULT CURRENT_DATE,
    total_cost NUMERIC(12,2) NOT NULL DEFAULT 0,
    deposit NUMERIC(12,2) NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'لم يدفع',
    order_status TEXT NOT NULL DEFAULT 'قيد التنفيذ',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT deposit_nonnegative CHECK (deposit >= 0),
    CONSTRAINT total_nonnegative CHECK (total_cost >= 0)
);

CREATE TABLE IF NOT EXISTS daily_notes (
    note_id BIGSERIAL PRIMARY KEY,
    note_date DATE NOT NULL UNIQUE,
    note_text TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);
"""


def _connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL غير موجود. أضفه في إعدادات السيرفر.")
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode=os.getenv("DB_SSLMODE", "require"))


@contextmanager
def connection():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)


def payment_status(total: float, deposit: float) -> str:
    if total > 0 and deposit >= total:
        return "تم الدفع بالكامل"
    if deposit > 0:
        return f"تم دفع عربون — المتبقي: {total - deposit:,.2f} ج"
    return "لم يدفع"


def create_order(name: str, phone: str, details: str, total: float, deposit: float, status: str, order_date):
    pay = payment_status(total, deposit)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO customers (name, phone) VALUES (%s, %s) RETURNING customer_id", (name, phone or None))
            customer_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO orders (customer_id, order_details, order_date, total_cost, deposit, payment_status, order_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING order_id
            """, (customer_id, details, order_date, total, deposit, pay, status))
            return cur.fetchone()[0]


def list_orders(search: str = "", status: str = "الكل", order_date: Optional[str] = None):
    clauses, params = [], []
    if search:
        clauses.append("(c.name ILIKE %s OR COALESCE(c.phone,'') ILIKE %s OR o.order_details ILIKE %s)")
        q = f"%{search}%"
        params.extend([q, q, q])
    if status and status != "الكل":
        clauses.append("o.order_status = %s")
        params.append(status)
    if order_date:
        clauses.append("o.order_date = %s")
        params.append(order_date)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"""
        SELECT o.order_id, c.name, c.phone, o.order_details, o.order_date,
               o.total_cost, o.deposit, o.payment_status, o.order_status,
               o.created_at, o.updated_at
        FROM orders o JOIN customers c ON c.customer_id=o.customer_id
        {where} ORDER BY o.order_id DESC
    """
    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_order(order_id: int):
    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT o.*, c.name, c.phone FROM orders o
                JOIN customers c ON c.customer_id=o.customer_id WHERE o.order_id=%s
            """, (order_id,))
            return cur.fetchone()


def update_order(order_id: int, deposit: float, status: str):
    order = get_order(order_id)
    if not order:
        raise ValueError("الطلب غير موجود")
    pay = payment_status(float(order["total_cost"]), deposit)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE orders SET deposit=%s, payment_status=%s, order_status=%s, updated_at=NOW()
                WHERE order_id=%s
            """, (deposit, pay, status, order_id))


def save_note(note_date, text: str):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO daily_notes(note_date,note_text) VALUES(%s,%s)
                ON CONFLICT(note_date) DO UPDATE SET note_text=EXCLUDED.note_text, updated_at=NOW()
            """, (note_date, text))


def get_note(note_date):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT note_text FROM daily_notes WHERE note_date=%s", (note_date,))
            row = cur.fetchone()
            return row[0] if row else ""


def recent_notes(limit=10):
    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT note_date, note_text FROM daily_notes
                WHERE TRIM(note_text)<>'' ORDER BY note_date DESC LIMIT %s
            """, (limit,))
            return cur.fetchall()


def statistics():
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE order_status='تم التسليم'),
                       COUNT(*) FILTER (WHERE order_status='قيد التنفيذ'),
                       COALESCE(SUM(total_cost),0),
                       COALESCE(SUM(deposit),0),
                       COALESCE(SUM(total_cost-deposit),0)
                FROM orders
            """)
            row = cur.fetchone()
            return row
