"""Feature schemas, contestant and setter roles, contests, leaderboards and billing.

1. Each feature gets its own schema, and the existing tables move into it:

   identity     tenants, users, memberships
   authoring    problems, problem_authors, eval_rules, calibration_examples, test_cases
   judging      submissions, test_results
   competition  contests, contest_problems, contest_standings, practice_bests
   billing      plans, subscriptions, usage_periods, model_prices, paddle_events
   ops          llm_usage, audit_log

   `ALTER TABLE ... SET SCHEMA` keeps rows, indexes, constraints, grants and identity
   sequences. Foreign keys point at tables, not names, so they keep working. Code must
   use schema-qualified names: there is no search_path entry for these schemas.

2. Membership roles become `admin`, `setter` and `contestant`. Every `member` becomes a
   `contestant`. A membership holds one role, and the roles nest: an admin can do
   everything a setter can, and a setter everything a contestant can.

3. Contests rank ICPC-style. `problems.pass_mark` is the score, on the same 0 to 1 scale
   as `submissions.score`, at which a submission counts as accepted. A submission to a
   problem its submitter authored is stored with `ranked = false`.

4. Users subscribe individually. `billing.plans` is a platform-wide catalog, so it has
   no `tenant_id`; neither do `model_prices` and `paddle_events`. The two plans are
   inserted here because subscriptions reference them.

The Supabase Data API exposes only the schemas listed in its settings, and these new
schemas have no grants for `anon` or `authenticated`, so the Data API can't read them.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SCHEMAS = ("identity", "authoring", "judging", "competition", "billing", "ops")

MOVES = {
    "identity": ("tenants", "users", "memberships"),
    "authoring": ("problems", "eval_rules", "calibration_examples", "test_cases"),
    "judging": ("submissions", "test_results"),
    "ops": ("llm_usage", "audit_log"),
}


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA {schema}")
    for schema, tables in MOVES.items():
        for table in tables:
            op.execute(f"ALTER TABLE public.{table} SET SCHEMA {schema}")

    op.execute("""
    ALTER TABLE identity.memberships DROP CONSTRAINT memberships_role_check;
    UPDATE identity.memberships SET role = 'contestant' WHERE role = 'member';
    ALTER TABLE identity.memberships ADD CONSTRAINT memberships_role_check
        CHECK (role IN ('admin', 'setter', 'contestant'));
    """)

    op.execute("""
    ALTER TABLE authoring.problems
        ADD COLUMN pass_mark numeric(4, 3) NOT NULL DEFAULT 1
            CHECK (pass_mark > 0 AND pass_mark <= 1);

    -- Who wrote a problem. A submission to your own problem is unranked.
    CREATE TABLE authoring.problem_authors (
        tenant_id  uuid NOT NULL,
        problem_id uuid NOT NULL,
        user_id    uuid NOT NULL,
        added_at   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (problem_id, user_id),
        FOREIGN KEY (tenant_id, problem_id)
            REFERENCES authoring.problems (tenant_id, id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, user_id)
            REFERENCES identity.memberships (tenant_id, user_id) ON DELETE CASCADE
    );
    CREATE INDEX problem_authors_user_idx ON authoring.problem_authors (tenant_id, user_id);

    INSERT INTO authoring.problem_authors (tenant_id, problem_id, user_id)
    SELECT p.tenant_id, p.id, p.created_by
    FROM authoring.problems p
    JOIN identity.memberships m ON m.tenant_id = p.tenant_id AND m.user_id = p.created_by;
    """)

    op.execute("""
    CREATE TABLE competition.contests (
        id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id               uuid NOT NULL REFERENCES identity.tenants (id) ON DELETE CASCADE,
        slug                    text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
        title                   text NOT NULL,
        description_md          text NOT NULL DEFAULT '',
        starts_at               timestamptz NOT NULL,
        ends_at                 timestamptz NOT NULL,
        max_submits_per_problem integer CHECK (max_submits_per_problem > 0),
        penalty_minutes         integer NOT NULL DEFAULT 20 CHECK (penalty_minutes >= 0),
        visibility              text NOT NULL DEFAULT 'draft'
                                CHECK (visibility IN ('draft', 'published')),
        created_by              uuid REFERENCES identity.users (id) ON DELETE SET NULL,
        created_at              timestamptz NOT NULL DEFAULT now(),
        CHECK (ends_at > starts_at),
        UNIQUE (tenant_id, slug),
        UNIQUE (tenant_id, id)
    );
    CREATE INDEX contests_window_idx ON competition.contests (tenant_id, starts_at, ends_at);

    CREATE TABLE competition.contest_problems (
        tenant_id  uuid NOT NULL,
        contest_id uuid NOT NULL,
        problem_id uuid NOT NULL,
        label      text NOT NULL CHECK (label ~ '^[A-Z][0-9]?$'),
        ordinal    integer NOT NULL CHECK (ordinal > 0),
        PRIMARY KEY (contest_id, problem_id),
        FOREIGN KEY (tenant_id, contest_id)
            REFERENCES competition.contests (tenant_id, id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, problem_id) REFERENCES authoring.problems (tenant_id, id),
        UNIQUE (contest_id, label),
        UNIQUE (contest_id, ordinal),
        UNIQUE (tenant_id, contest_id, problem_id)
    );
    CREATE INDEX contest_problems_problem_idx ON competition.contest_problems (problem_id);

    -- A submission belongs to a contest when it was made through one; NULL is practice.
    ALTER TABLE judging.submissions
        ADD COLUMN contest_id uuid,
        ADD COLUMN ranked boolean NOT NULL DEFAULT true,
        ADD CONSTRAINT submissions_contest_fk FOREIGN KEY (tenant_id, contest_id, problem_id)
            REFERENCES competition.contest_problems (tenant_id, contest_id, problem_id);
    -- The per-contest submit cap and the standings rebuild both read this.
    CREATE INDEX submissions_contest_idx ON judging.submissions
        (contest_id, user_id, problem_id, created_at) WHERE contest_id IS NOT NULL;

    -- One row per contest, user and problem. The grader updates it when it aggregates a
    -- ranked submit. Rank = problems accepted DESC, then total penalty ASC, where a
    -- problem's penalty is minutes from starts_at to accepted_at plus
    -- penalty_minutes * rejected_before_accept.
    CREATE TABLE competition.contest_standings (
        tenant_id              uuid NOT NULL,
        contest_id             uuid NOT NULL,
        problem_id             uuid NOT NULL,
        user_id                uuid NOT NULL,
        submits                integer NOT NULL DEFAULT 0 CHECK (submits >= 0),
        rejected_before_accept integer NOT NULL DEFAULT 0 CHECK (rejected_before_accept >= 0),
        best_score             numeric(6, 3),
        accepted_at            timestamptz,
        accepted_submission_id uuid,
        updated_at             timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (contest_id, user_id, problem_id),
        FOREIGN KEY (tenant_id, contest_id, problem_id)
            REFERENCES competition.contest_problems (tenant_id, contest_id, problem_id)
            ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, user_id)
            REFERENCES identity.memberships (tenant_id, user_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, accepted_submission_id)
            REFERENCES judging.submissions (tenant_id, id),
        CHECK ((accepted_at IS NULL) = (accepted_submission_id IS NULL))
    );

    -- The practice leaderboard: each user's best ranked score per problem.
    CREATE TABLE competition.practice_bests (
        tenant_id     uuid NOT NULL,
        problem_id    uuid NOT NULL,
        user_id       uuid NOT NULL,
        best_score    numeric(6, 3) NOT NULL,
        submission_id uuid NOT NULL,
        reached_at    timestamptz NOT NULL,
        PRIMARY KEY (problem_id, user_id),
        FOREIGN KEY (tenant_id, problem_id)
            REFERENCES authoring.problems (tenant_id, id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, user_id)
            REFERENCES identity.memberships (tenant_id, user_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, submission_id) REFERENCES judging.submissions (tenant_id, id)
    );
    -- Ties go to whoever reached the score first.
    CREATE INDEX practice_bests_board_idx ON competition.practice_bests
        (problem_id, best_score DESC, reached_at);
    """)

    op.execute("""
    CREATE TABLE billing.plans (
        id              text PRIMARY KEY CHECK (id ~ '^[a-z][a-z0-9_]{1,31}$'),
        name            text NOT NULL,
        price_usd       numeric(10, 2) NOT NULL CHECK (price_usd >= 0),
        credit_usd      numeric(10, 2) NOT NULL CHECK (credit_usd >= 0),
        -- Set on the trial only. Paid periods come from Paddle (subscriptions.current_period_*).
        period_days     integer CHECK (period_days > 0),
        submission_cap  integer CHECK (submission_cap >= 0),
        runs_per_hour   integer NOT NULL CHECK (runs_per_hour > 0),
        is_trial        boolean NOT NULL DEFAULT false,
        paddle_price_id text UNIQUE,
        active          boolean NOT NULL DEFAULT true,
        created_at      timestamptz NOT NULL DEFAULT now(),
        CHECK (NOT is_trial OR period_days IS NOT NULL)
    );
    INSERT INTO billing.plans
        (id, name, price_usd, credit_usd, period_days, submission_cap, runs_per_hour, is_trial)
    VALUES
        ('free_trial', 'Free trial', 0, 1, 7, 1, 10, true),
        ('pro', 'Pro', 20, 10, NULL, NULL, 60, false);

    CREATE TABLE billing.subscriptions (
        id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id              uuid NOT NULL,
        user_id                uuid NOT NULL,
        plan_id                text NOT NULL REFERENCES billing.plans (id),
        status                 text NOT NULL CHECK (status IN (
                                   'trialing', 'active', 'past_due', 'canceled', 'expired')),
        current_period_start   timestamptz NOT NULL,
        current_period_end     timestamptz NOT NULL,
        cancel_at              timestamptz,
        paddle_customer_id     text,
        paddle_subscription_id text UNIQUE,
        created_at             timestamptz NOT NULL DEFAULT now(),
        updated_at             timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY (tenant_id, user_id)
            REFERENCES identity.memberships (tenant_id, user_id) ON DELETE CASCADE,
        CHECK (current_period_end > current_period_start),
        UNIQUE (tenant_id, id)
    );
    -- One live subscription per user.
    CREATE UNIQUE INDEX subscriptions_one_live_idx ON billing.subscriptions (tenant_id, user_id)
        WHERE status IN ('trialing', 'active', 'past_due');
    -- One trial per account, ever.
    CREATE UNIQUE INDEX subscriptions_one_trial_idx ON billing.subscriptions (user_id)
        WHERE plan_id = 'free_trial';

    -- The durable copy of what the proxy meters in Redis, one row per billing period.
    CREATE TABLE billing.usage_periods (
        tenant_id       uuid NOT NULL,
        subscription_id uuid NOT NULL,
        user_id         uuid NOT NULL,
        period_start    timestamptz NOT NULL,
        period_end      timestamptz NOT NULL,
        credit_usd      numeric(10, 2) NOT NULL CHECK (credit_usd >= 0),
        spent_usd       numeric(12, 6) NOT NULL DEFAULT 0 CHECK (spent_usd >= 0),
        tokens          bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
        submissions     integer NOT NULL DEFAULT 0 CHECK (submissions >= 0),
        updated_at      timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (subscription_id, period_start),
        FOREIGN KEY (tenant_id, subscription_id)
            REFERENCES billing.subscriptions (tenant_id, id) ON DELETE CASCADE,
        CHECK (period_end > period_start)
    );
    CREATE INDEX usage_periods_user_idx ON billing.usage_periods
        (tenant_id, user_id, period_start DESC);

    -- Prices are never edited: a price change inserts a row with a later effective_from.
    CREATE TABLE billing.model_prices (
        model                     text NOT NULL,
        effective_from            timestamptz NOT NULL,
        input_usd_per_mtok        numeric(10, 4) NOT NULL CHECK (input_usd_per_mtok >= 0),
        output_usd_per_mtok       numeric(10, 4) NOT NULL CHECK (output_usd_per_mtok >= 0),
        cache_read_usd_per_mtok   numeric(10, 4) CHECK (cache_read_usd_per_mtok >= 0),
        cache_write_usd_per_mtok  numeric(10, 4) CHECK (cache_write_usd_per_mtok >= 0),
        PRIMARY KEY (model, effective_from)
    );

    -- The primary key is the webhook dedupe: a redelivered event inserts nothing.
    CREATE TABLE billing.paddle_events (
        event_id     text PRIMARY KEY,
        event_type   text NOT NULL,
        occurred_at  timestamptz NOT NULL,
        payload      jsonb NOT NULL,
        received_at  timestamptz NOT NULL DEFAULT now(),
        processed_at timestamptz,
        error        text
    );
    CREATE INDEX paddle_events_unprocessed_idx ON billing.paddle_events (received_at)
        WHERE processed_at IS NULL;
    """)

    op.execute("""
    -- Usage is metered per user. Rows written before this migration have no user.
    ALTER TABLE ops.llm_usage
        ADD COLUMN user_id uuid,
        ADD COLUMN cost_usd numeric(12, 6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0);
    CREATE INDEX llm_usage_user_idx ON ops.llm_usage (tenant_id, user_id, created_at)
        WHERE user_id IS NOT NULL;
    """)

    # Grants for orqen_app until 0004 replaces it with one database role per app role.
    # Moved tables keep the grants from 0001.
    op.execute(f"""
    GRANT USAGE ON SCHEMA {", ".join(SCHEMAS)} TO orqen_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON
        authoring.problem_authors, competition.contests, competition.contest_problems,
        competition.contest_standings, competition.practice_bests,
        billing.subscriptions, billing.usage_periods
        TO orqen_app;
    -- The catalog is read-only to the app. Webhooks are inserted, then marked processed.
    GRANT SELECT ON billing.plans, billing.model_prices TO orqen_app;
    GRANT SELECT, INSERT, UPDATE ON billing.paddle_events TO orqen_app;
    """)

    # Tables moved out of public keep the grants Supabase gave them there. 0002 revoked
    # anon and authenticated; service_role still holds TRUNCATE, TRIGGER and REFERENCES,
    # on these tables and on public.alembic_version. No Supabase role should hold any.
    op.execute(f"""
    DO $$
    DECLARE
        r text;
        s text;
    BEGIN
        FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = r) THEN
                FOREACH s IN ARRAY ARRAY{["public", *SCHEMAS]} LOOP
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM %I', s, r);
                    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM %I', s, r);
                END LOOP;
            END IF;
        END LOOP;
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
            ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM service_role;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM service_role;
        END IF;
    END
    $$;
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX ops.llm_usage_user_idx;
    ALTER TABLE ops.llm_usage DROP COLUMN user_id, DROP COLUMN cost_usd;

    DROP TABLE billing.paddle_events, billing.model_prices, billing.usage_periods,
        billing.subscriptions, billing.plans;
    DROP TABLE competition.practice_bests, competition.contest_standings;
    ALTER TABLE judging.submissions
        DROP CONSTRAINT submissions_contest_fk,
        DROP COLUMN contest_id,
        DROP COLUMN ranked;
    DROP TABLE competition.contest_problems, competition.contests;
    DROP TABLE authoring.problem_authors;
    ALTER TABLE authoring.problems DROP COLUMN pass_mark;

    ALTER TABLE identity.memberships DROP CONSTRAINT memberships_role_check;
    -- The old schema had no setter role; a setter keeps authoring rights as an admin.
    UPDATE identity.memberships SET role = 'admin' WHERE role = 'setter';
    UPDATE identity.memberships SET role = 'member' WHERE role = 'contestant';
    ALTER TABLE identity.memberships ADD CONSTRAINT memberships_role_check
        CHECK (role IN ('admin', 'member'));
    """)
    for schema, tables in MOVES.items():
        for table in tables:
            op.execute(f"ALTER TABLE {schema}.{table} SET SCHEMA public")
    for schema in SCHEMAS:
        op.execute(f"DROP SCHEMA {schema}")
