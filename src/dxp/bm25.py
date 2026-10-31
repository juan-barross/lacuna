from contextlib import closing

import duckdb
import pyarrow as pa

INDEX = """PRAGMA create_fts_index(
    'atos', 'ato_id', 'text',
    stemmer = 'portuguese', stopwords = 'none', strip_accents = 1, lower = 1
)"""
QUERY = """SELECT ato_id, score FROM (
    SELECT ato_id, fts_main_atos.match_bm25(ato_id, ?) AS score FROM atos
) WHERE score IS NOT NULL ORDER BY score DESC, ato_id LIMIT ?"""


class BM25:
    def __init__(self, atos: pa.Table) -> None:
        ids = atos.column("ato_id").to_pylist()
        if len(set(ids)) != len(ids):
            raise ValueError("ato_id repetido: o índice BM25 exige identificadores únicos")
        self.con = duckdb.connect()
        self.con.execute("SET memory_limit = '512MB'")
        self.con.register("source", atos.select(["ato_id", "text"]))
        self.con.execute("CREATE TABLE atos AS SELECT ato_id, text FROM source")
        self.con.execute("INSTALL fts")
        self.con.execute("LOAD fts")
        self.con.execute(INDEX)

    def search(self, query: str, k: int = 20) -> list[tuple[str, float]]:
        with closing(self.con.cursor()) as cursor:
            return cursor.execute(QUERY, [query, k]).fetchall()
