"""
Copia TODOS los datos entre la base PostgreSQL de producción y un archivo SQLite, en ambos sentidos.

Para qué existe: hosting temporal en PythonAnywhere (plan gratis = solo SQLite) mientras el droplet de
DigitalOcean no está disponible, y luego la vuelta a Postgres sin perder ninguna venta (en julio 2026 las
ventas hechas en PythonAnywhere nunca volvieron a DO y el inventario se descuadró).

Copia tabla por tabla conservando los IDs, así que todo lo que apunta a otro registro sigue igual.
Al final compara la cantidad de filas de cada tabla en origen y destino y aborta si algo no cuadra.

Uso (desde bodega_system/, con el venv activo y psycopg2 instalado):

    # Postgres -> SQLite (ida). El SQLite destino NO debe existir: se crea con las migraciones.
    python scripts/copiar_base.py a-sqlite --pg "host=localhost port=55432 dbname=abastos user=abastos password=..." \
        --sqlite /ruta/db.sqlite3

    # SQLite -> Postgres (vuelta). La base Postgres destino debe estar VACÍA (solo migrada).
    python scripts/copiar_base.py a-postgres --pg "..." --sqlite /ruta/db.sqlite3
"""
import argparse
import datetime
import decimal
import json
import os
import sqlite3
import sys
import zoneinfo

import psycopg2

# El sistema corre con USE_TZ=False y TIME_ZONE='America/Caracas': Django guarda en Postgres columnas
# timestamptz, pero en SQLite espera fechas SIN zona en hora de Caracas. Si se copian con el desfase
# ('...-04:00'), Django las lee como fechas con zona y luego no puede volver a guardarlas
# ("SQLite backend does not support timezone-aware datetimes when USE_TZ is False").
ZONA = zoneinfo.ZoneInfo('America/Caracas')

# Tablas que crea/llena migrate y no se deben copiar
EXCLUIR = {'django_migrations', 'sqlite_sequence'}


def tablas_sqlite(conn):
    filas = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return {f[0] for f in filas} - EXCLUIR


def tablas_pg(cur):
    cur.execute("select tablename from pg_tables where schemaname='public'")
    return {f[0] for f in cur.fetchall()} - EXCLUIR


def a_sqlite(valor):
    """Convierte un valor leído de Postgres al formato que guarda Django en SQLite."""
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, decimal.Decimal):
        return str(valor)
    if isinstance(valor, datetime.datetime) and valor.tzinfo is not None:
        valor = valor.astimezone(ZONA).replace(tzinfo=None)
    if isinstance(valor, (datetime.datetime, datetime.date, datetime.time)):
        return str(valor)  # 'YYYY-MM-DD HH:MM:SS[.ffffff]', igual que Django
    if isinstance(valor, (dict, list)):
        return json.dumps(valor)
    if isinstance(valor, memoryview):
        return bytes(valor)
    return valor


def migrar_sqlite_vacio(ruta):
    """Crea el SQLite destino con el esquema exacto del código actual (manage.py migrate)."""
    if os.path.exists(ruta):
        sys.exit(f'ERROR: {ruta} ya existe; borrarlo o elegir otra ruta.')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bodega_system.settings')
    os.environ.pop('DB_NAME', None)
    import django
    from django.conf import settings
    django.setup()
    settings.DATABASES['default']['NAME'] = ruta
    from django.core.management import call_command
    call_command('migrate', verbosity=0)
    from django.db import connections
    connections.close_all()


def copiar_a_sqlite(dsn, ruta):
    migrar_sqlite_vacio(ruta)
    pg = psycopg2.connect(dsn)
    sq = sqlite3.connect(ruta)
    sq.execute('PRAGMA foreign_keys=OFF')
    cur = pg.cursor()
    cur.execute("set time zone 'America/Caracas'")
    faltan = tablas_pg(cur) - tablas_sqlite(sq)
    if faltan:
        sys.exit(f'ERROR: tablas en Postgres sin equivalente en SQLite (¿código distinto?): {sorted(faltan)}')
    for tabla in sorted(tablas_sqlite(sq)):
        cols_sq = [c[1] for c in sq.execute(f'pragma table_info("{tabla}")')]
        cur.execute('select column_name from information_schema.columns where table_name=%s', (tabla,))
        cols_pg = {c[0] for c in cur.fetchall()}
        if set(cols_sq) != cols_pg:
            sys.exit(f'ERROR: columnas distintas en {tabla}: {set(cols_sq) ^ cols_pg}')
        sq.execute(f'delete from "{tabla}"')  # migrate pudo sembrar filas (contenttypes, turnos)
        lista = ', '.join(f'"{c}"' for c in cols_sq)
        cur.execute(f'select {lista} from "{tabla}"')
        marcas = ', '.join('?' * len(cols_sq))
        while True:
            lote = cur.fetchmany(5000)
            if not lote:
                break
            sq.executemany(f'insert into "{tabla}" ({lista}) values ({marcas})',
                           [tuple(a_sqlite(v) for v in fila) for fila in lote])
    sq.commit()
    rotas = sq.execute('PRAGMA foreign_key_check').fetchall()
    if rotas:
        sys.exit(f'ERROR: referencias rotas en SQLite: {rotas[:10]}')
    verificar(cur, sq)


def copiar_a_postgres(dsn, ruta):
    pg = psycopg2.connect(dsn)
    sq = sqlite3.connect(ruta)
    cur = pg.cursor()
    tablas = sorted(tablas_sqlite(sq))
    faltan = set(tablas) - tablas_pg(cur)
    if faltan:
        sys.exit(f'ERROR: tablas sin equivalente en Postgres (¿falta migrar?): {sorted(faltan)}')
    # Las fechas del SQLite son hora de Caracas sin zona: que Postgres las interprete así
    cur.execute("set time zone 'America/Caracas'")
    # Los triggers de FK se desactivan durante la carga y se verifican al final
    cur.execute('set session_replication_role = replica')
    for tabla in tablas:
        cur.execute('select column_name, data_type from information_schema.columns where table_name=%s',
                    (tabla,))
        tipos = dict(cur.fetchall())
        cols = [c[1] for c in sq.execute(f'pragma table_info("{tabla}")')]
        booleanas = [i for i, c in enumerate(cols) if tipos[c] == 'boolean']
        cur.execute(f'delete from "{tabla}"')  # migrate pudo sembrar filas
        lista = ', '.join(f'"{c}"' for c in cols)
        marcas = ', '.join(['%s'] * len(cols))
        filas = sq.execute(f'select {lista} from "{tabla}"')
        while True:
            lote = filas.fetchmany(5000)
            if not lote:
                break
            convertidas = []
            for fila in lote:
                fila = list(fila)
                for i in booleanas:
                    if fila[i] is not None:
                        fila[i] = bool(fila[i])
                convertidas.append(fila)
            cur.executemany(f'insert into "{tabla}" ({lista}) values ({marcas})', convertidas)
    cur.execute('set session_replication_role = origin')
    # Secuencias de IDs: que la próxima venta no choque con una ID ya usada
    cur.execute("""
        select c.table_name, c.column_name, pg_get_serial_sequence(c.table_name, c.column_name)
        from information_schema.columns c
        where c.table_schema='public' and pg_get_serial_sequence(c.table_name, c.column_name) is not null
    """)
    for tabla, col, seq in cur.fetchall():
        cur.execute(f'select setval(%s, coalesce((select max("{col}") from "{tabla}"), 0) + 1, false)', (seq,))
    pg.commit()
    verificar(cur, sq)


def verificar(cur, sq):
    """Compara filas por tabla y sumas de dinero clave. Aborta si algo no cuadra."""
    errores = []
    for tabla in sorted(tablas_sqlite(sq)):
        n_sq = sq.execute(f'select count(*) from "{tabla}"').fetchone()[0]
        cur.execute(f'select count(*) from "{tabla}"')
        n_pg = cur.fetchone()[0]
        if n_sq != n_pg:
            errores.append(f'{tabla}: postgres={n_pg} sqlite={n_sq}')
    for tabla, col in [('sales_sale', 'total_usd'), ('inventory_product', 'stock'),
                       ('customers_customercredit', 'amount_usd')]:
        try:
            cur.execute(f'select coalesce(sum("{col}"), 0) from "{tabla}"')
            s_pg = decimal.Decimal(cur.fetchone()[0])
            s_sq = decimal.Decimal(str(sq.execute(f'select coalesce(sum("{col}"), 0) from "{tabla}"').fetchone()[0]))
            estado = 'OK' if abs(s_pg - s_sq) < decimal.Decimal('0.01') else 'DIFERENTE'
            print(f'  suma {tabla}.{col}: postgres={s_pg} sqlite={s_sq} {estado}')
            if estado != 'OK':
                errores.append(f'suma {tabla}.{col}')
        except (psycopg2.Error, sqlite3.Error):
            cur.connection.rollback()  # columna con otro nombre: se omite esa suma
    if errores:
        sys.exit('ERROR, no cuadra:\n  ' + '\n  '.join(errores))
    print(f'OK: {len(tablas_sqlite(sq))} tablas con la misma cantidad de filas en ambos lados.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('direccion', choices=['a-sqlite', 'a-postgres'])
    p.add_argument('--pg', required=True, help='DSN de Postgres')
    p.add_argument('--sqlite', required=True, help='Ruta del archivo SQLite')
    a = p.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if a.direccion == 'a-sqlite':
        copiar_a_sqlite(a.pg, a.sqlite)
    else:
        copiar_a_postgres(a.pg, a.sqlite)
