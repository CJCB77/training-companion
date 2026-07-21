"""seed common exercises

Revision ID: 879db719772b
Revises: 669a3036ea19
Create Date: 2026-06-07 23:04:45.468940

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.data.seed_exercises import EXERCISE_SEED

# revision identifiers, used by Alembic.
revision: str = "879db719772b"
down_revision: str | None = "669a3036ea19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Ad-hoc table reference so this migration is independent of the live model.
# created_by_user_id is left unset -> NULL (a system exercise); created_at/updated_at
# fall back to their server defaults.
_exercises = sa.table(
    "exercises",
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("muscle_group", sa.String),
    sa.column("equipment", sa.String),
    sa.column("category", sa.String),
    sa.column("created_by_user_id", sa.Integer),
)


def upgrade() -> None:
    op.bulk_insert(
        _exercises,
        [
            {
                "name": row["name"],
                "description": row.get("description"),
                "muscle_group": str(row["muscle_group"]),
                "equipment": str(row["equipment"]),
                "category": str(row["category"]) if row.get("category") else None,
            }
            for row in EXERCISE_SEED
        ],
    )


def downgrade() -> None:
    names = [row["name"] for row in EXERCISE_SEED]
    op.execute(
        _exercises.delete().where(
            _exercises.c.name.in_(names),
            _exercises.c.created_by_user_id.is_(None),
        )
    )
