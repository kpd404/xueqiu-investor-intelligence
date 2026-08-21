# Database migrations

Alembic owns schema evolution. Apply migrations with `alembic upgrade head`; do not use
`Base.metadata.create_all()` in application startup.

