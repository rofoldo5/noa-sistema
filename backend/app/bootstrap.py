import getpass
import os
from sqlalchemy import select, inspect
from app.main import engine, SessionLocal, User, hasher

def main():
    if not inspect(engine).has_table("alembic_version"):
        raise SystemExit("Ejecuta primero: python -m app.migrate")
    email = input('Correo SuperAdmin: ').strip().lower()
    name = input('Nombre SuperAdmin: ').strip()
    password = getpass.getpass('Contraseña (mínimo 12 caracteres): ')
    if not name or '@' not in email or len(password) < 12:
        raise SystemExit('Datos inválidos')
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit('Ese correo ya existe; no se modificó')
        db.add(User(name=name, email=email, password_hash=hasher.hash(password), role='SUPERADMIN', active=True))
        db.commit()
    print('SuperAdmin creado correctamente')
if __name__ == '__main__': main()
