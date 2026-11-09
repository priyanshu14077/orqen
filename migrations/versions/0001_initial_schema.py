"""Initial schema: tenants, users, problems, eval rules, submissions, results, usage.

Every tenant-owned table carries `tenant_id`, and child tables reference their parent
through a composite `(tenant_id, id)` foreign key. That makes a row pointing at
another tenant's parent impossible at the database level, not just in app code.

CHECK constraints mirror the enums in orqen_core.models; change both together.

Revision ID: 0001
Revises:
Create Date: 2026-11-09
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE tenants (
        id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        slug             text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
        name             text NOT NULL,
        settings         jsonb NOT NULL DEFAULT '{}',
        provider_key_enc bytea,
        created_at       timestamptz NOT NULL DEFAULT now()
    );

    -- Users are global: one person can belong to several tenants.
    CREATE TABLE users (
        id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        email             text NOT NULL UNIQUE CHECK (email = lower(email)),
        password_hash     text NOT NULL,
        is_platform_owner boolean NOT NULL DEFAULT false,
        created_at        timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE memberships (
        tenant_id  uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
        user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        role       text NOT NULL CHECK (role IN ('admin', 'member')),
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, user_id)
    );
    CREATE INDEX memberships_user_idx ON memberships (user_id);

    CREATE TABLE problems (
        id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id             uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
        slug                  text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
        title                 text NOT NULL,
        statement_md          text NOT NULL,
        kinds                 text[] NOT NULL DEFAULT '{prompt,code}'
                              CHECK (kinds <@ '{prompt,code}' AND cardinality(kinds) > 0),
        models_allowed        text[] NOT NULL CHECK (cardinality(models_allowed) > 0),
        tools_spec            jsonb NOT NULL DEFAULT '[]',
        time_limit_ms         integer NOT NULL CHECK (time_limit_ms > 0),
        mem_limit_mb          integer NOT NULL CHECK (mem_limit_mb > 0),
        token_budget_per_test integer NOT NULL CHECK (token_budget_per_test > 0),
        max_steps             integer NOT NULL CHECK (max_steps > 0),
        visibility            text NOT NULL DEFAULT 'draft'
                              CHECK (visibility IN ('draft', 'published')),
        created_by            uuid REFERENCES users (id) ON DELETE SET NULL,
        created_at            timestamptz NOT NULL DEFAULT now(),
        UNIQUE (tenant_id, slug),
        UNIQUE (tenant_id, id)
    );

    -- Rows are never updated except `status`: editing a rule inserts version N+1.
    CREATE TABLE eval_rules (
        id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id             uuid NOT NULL,
        problem_id            uuid NOT NULL,
        version               integer NOT NULL CHECK (version > 0),
        spec                  jsonb NOT NULL,
        status                text NOT NULL DEFAULT 'draft'
                              CHECK (status IN ('draft', 'active', 'retired')),
        calibration_agreement numeric(4, 3) CHECK (calibration_agreement BETWEEN 0 AND 1),
        created_by            uuid REFERENCES users (id) ON DELETE SET NULL,
        created_at            timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY (tenant_id, problem_id) REFERENCES problems (tenant_id, id) ON DELETE CASCADE,
        UNIQUE (problem_id, version),
        UNIQUE (tenant_id, id)
    );
    -- At most one active rule per problem.
    CREATE UNIQUE INDEX eval_rules_one_active_idx ON eval_rules (problem_id)
        WHERE status = 'active';

    CREATE TABLE calibration_examples (
        id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id      uuid NOT NULL,
        eval_rule_id   uuid NOT NULL,
        input          jsonb NOT NULL,
        output         jsonb NOT NULL,
        expected_score numeric(4, 3) NOT NULL CHECK (expected_score BETWEEN 0 AND 1),
        is_canary      boolean NOT NULL DEFAULT false,
        FOREIGN KEY (tenant_id, eval_rule_id)
            REFERENCES eval_rules (tenant_id, id) ON DELETE CASCADE
    );

    CREATE TABLE test_cases (
        id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id  uuid NOT NULL,
        problem_id uuid NOT NULL,
        ordinal    integer NOT NULL CHECK (ordinal > 0),
        input      jsonb NOT NULL,
        expected   jsonb NOT NULL,
        is_sample  boolean NOT NULL DEFAULT false,
        weight     integer NOT NULL DEFAULT 1 CHECK (weight > 0),
        FOREIGN KEY (tenant_id, problem_id) REFERENCES problems (tenant_id, id) ON DELETE CASCADE,
        UNIQUE (problem_id, ordinal),
        UNIQUE (tenant_id, id)
    );

    CREATE TABLE submissions (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       uuid NOT NULL,
        user_id         uuid NOT NULL,
        problem_id      uuid NOT NULL,
        eval_rule_id    uuid NOT NULL,
        kind            text NOT NULL CHECK (kind IN ('prompt', 'code')),
        mode            text NOT NULL CHECK (mode IN ('run', 'submit')),
        payload         jsonb NOT NULL,
        status          text NOT NULL DEFAULT 'QUEUED' CHECK (status IN (
                            'WAITING', 'QUEUED', 'EXPANDING', 'RUNNING', 'AGGREGATING',
                            'COMPLETED', 'FAILED', 'TIMED_OUT')),
        total_tests     integer CHECK (total_tests >= 0),
        score           numeric(6, 3),
        total_tokens    integer NOT NULL DEFAULT 0,
        cost_usd        numeric(12, 6) NOT NULL DEFAULT 0,
        idempotency_key text,
        trace_id        text,
        created_at      timestamptz NOT NULL DEFAULT now(),
        started_at      timestamptz,
        completed_at    timestamptz,
        FOREIGN KEY (tenant_id, user_id) REFERENCES memberships (tenant_id, user_id),
        FOREIGN KEY (tenant_id, problem_id) REFERENCES problems (tenant_id, id),
        FOREIGN KEY (tenant_id, eval_rule_id) REFERENCES eval_rules (tenant_id, id),
        UNIQUE (tenant_id, user_id, idempotency_key),
        UNIQUE (tenant_id, id)
    );
    CREATE INDEX submissions_problem_idx ON submissions (tenant_id, problem_id, created_at DESC);
    CREATE INDEX submissions_user_idx ON submissions (tenant_id, user_id, created_at DESC);
    -- The watchdog's sweep for stuck and waiting submissions.
    CREATE INDEX submissions_open_idx ON submissions (status, created_at)
        WHERE status NOT IN ('COMPLETED', 'FAILED', 'TIMED_OUT');

    -- The primary key is the fan-in dedupe: a redelivered test result inserts nothing.
    CREATE TABLE test_results (
        submission_id    uuid NOT NULL,
        test_case_id     uuid NOT NULL,
        tenant_id        uuid NOT NULL,
        verdict          text NOT NULL CHECK (verdict IN (
                             'PASS', 'FAIL', 'ERROR', 'TLE', 'MLE', 'BUDGET', 'SYSTEM_ERROR')),
        score            numeric(4, 3) CHECK (score BETWEEN 0 AND 1),
        output           jsonb,
        criterion_scores jsonb,
        judge_reason     text,
        error_msg        text,
        latency_ms       integer,
        queue_wait_ms    integer NOT NULL DEFAULT 0,
        tokens           integer NOT NULL DEFAULT 0,
        attempts         integer NOT NULL DEFAULT 1,
        created_at       timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (submission_id, test_case_id),
        FOREIGN KEY (tenant_id, submission_id)
            REFERENCES submissions (tenant_id, id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, test_case_id) REFERENCES test_cases (tenant_id, id)
    );

    CREATE TABLE llm_usage (
        id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        tenant_id     uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
        submission_id uuid,
        test_case_id  uuid,
        purpose       text NOT NULL CHECK (purpose IN ('agent', 'judge')),
        model         text NOT NULL,
        input_tokens  integer NOT NULL,
        output_tokens integer NOT NULL,
        latency_ms    integer NOT NULL,
        created_at    timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX llm_usage_tenant_idx ON llm_usage (tenant_id, created_at);
    CREATE INDEX llm_usage_submission_idx ON llm_usage (submission_id)
        WHERE submission_id IS NOT NULL;

    CREATE TABLE audit_log (
        id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        tenant_id uuid REFERENCES tenants (id) ON DELETE CASCADE,
        actor_id  uuid REFERENCES users (id) ON DELETE SET NULL,
        action    text NOT NULL,
        target    text NOT NULL,
        diff      jsonb NOT NULL DEFAULT '{}',
        at        timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX audit_log_tenant_idx ON audit_log (tenant_id, at DESC);
    """)

    # The application role. NOLOGIN: services connect as the owner and switch with
    # `SET LOCAL ROLE orqen_app` per transaction (orqen_core.db.tenant_tx). Because
    # it is not the table owner, RLS policies added in M7 will apply to it.
    # Roles are cluster-wide, so this tolerates the role already existing.
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'orqen_app') THEN
            CREATE ROLE orqen_app NOLOGIN;
        END IF;
    END
    $$;
    GRANT orqen_app TO CURRENT_USER;
    GRANT USAGE ON SCHEMA public TO orqen_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON
        tenants, users, memberships, problems, eval_rules, calibration_examples,
        test_cases, submissions, test_results
        TO orqen_app;
    -- Usage and audit rows are append-only for the application.
    GRANT SELECT, INSERT ON llm_usage, audit_log TO orqen_app;
    """)


def downgrade() -> None:
    # The orqen_app role is left in place: roles are cluster-wide and another
    # database (the test database, for one) may still use it.
    op.execute("""
    DROP TABLE audit_log, llm_usage, test_results, submissions, test_cases,
        calibration_examples, eval_rules, problems, memberships, users, tenants;
    """)
