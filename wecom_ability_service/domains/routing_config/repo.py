from __future__ import annotations

from ...db import get_db


def get_owner_role(userid: str):
    return get_db().execute(
        """
        SELECT userid, display_name, role, active, updated_at
        FROM owner_role_map
        WHERE userid = ?
        """,
        (userid,),
    ).fetchone()


def list_owner_role_map(active_only: bool = False):
    sql = """
        SELECT userid, display_name, role, active, updated_at
        FROM owner_role_map
    """
    params: list[object] = []
    if active_only:
        sql += " WHERE active = ?"
        params.append(True)
    sql += " ORDER BY active DESC, display_name ASC, userid ASC"
    return get_db().execute(sql, tuple(params)).fetchall()
