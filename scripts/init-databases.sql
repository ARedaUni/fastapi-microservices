-- One database per service. Runs once, from the postgres image's
-- /docker-entrypoint-initdb.d/ hook, against an empty data directory.
--
-- Adding a service means adding two lines here and nothing else: the server is
-- shared, the data is not. Two services in one database means two Alembic
-- histories fighting over one `alembic_version` table, and an autogenerate in
-- either one proposing to drop the other's tables.
--
-- POSTGRES_DB is `postgres` for this server -- the bootstrap database these
-- statements run against, which no service ever connects to.

CREATE DATABASE users;
GRANT ALL PRIVILEGES ON DATABASE users TO "user";
