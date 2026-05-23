from blacknode.node import node


@node(
    inputs=["path:Text", "sql:Text", "params:List"],
    outputs=["rows:List", "columns:List", "row_count:Int"],
    name="SQLiteQuery",
)
def sqlite_query(ctx: dict) -> dict:
    import sqlite3

    params = ctx.get("params") or []
    conn = sqlite3.connect(str(ctx.get("path") or ""))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(str(ctx.get("sql") or ""), params)
        rows = [dict(row) for row in cursor.fetchall()]
        columns = [description[0] for description in cursor.description or []]
    finally:
        conn.close()
    return {"rows": rows, "columns": columns, "row_count": len(rows)}


@node(
    inputs=["path:Text", "sql:Text", "params:List"],
    outputs=["row_count:Int", "lastrowid:Int"],
    name="SQLiteExec",
)
def sqlite_exec(ctx: dict) -> dict:
    import sqlite3

    params = ctx.get("params") or []
    conn = sqlite3.connect(str(ctx.get("path") or ""))
    try:
        cursor = conn.execute(str(ctx.get("sql") or ""), params)
        conn.commit()
        lastrowid = cursor.lastrowid if cursor.lastrowid is not None else 0
        row_count = cursor.rowcount if cursor.rowcount is not None else 0
    finally:
        conn.close()
    return {"row_count": row_count, "lastrowid": lastrowid}
