-- Runs once, when the Postgres volume is first created. Integration tests migrate
-- and seed this database so they never touch the dev data in `orqen`.
CREATE DATABASE orqen_test OWNER orqen;
