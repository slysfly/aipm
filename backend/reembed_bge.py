import sys, json, sqlite3, logging, time
logging.basicConfig(filename="/opt/AI-PM/reembed.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reembed")
model_name = sys.argv[1] if len(sys.argv) > 1 else "BAAI/bge-base-zh"
db = "/opt/AI-PM/backend/tw_ai_pms.db"
log.info("reembed start model=%s", model_name)
from sentence_transformers import SentenceTransformer
m = SentenceTransformer(model_name)
dim = int(m.get_sentence_embedding_dimension())
log.info("model loaded dim=%s", dim)
conn = sqlite3.connect(db)
cur = conn.cursor()
total = cur.execute("select count(*) from knowledge_chunks").fetchone()[0]
log.info("total chunks=%s", total)
rows = cur.execute("select id, content from knowledge_chunks").fetchall()
ids = [r[0] for r in rows]
texts = [(r[1] or "") for r in rows]
B = 256
done = 0
t0 = time.time()
for i in range(0, len(texts), B):
    b_ids = ids[i:i+B]
    b_txt = texts[i:i+B]
    vecs = m.encode(b_txt, normalize_embeddings=True, batch_size=32,
                    show_progress_bar=False, convert_to_numpy=True)
    for cid, vec in zip(b_ids, vecs):
        cur.execute("update knowledge_chunks set embedding=? where id=?",
                    (json.dumps([float(x) for x in vec]), cid))
    conn.commit()
    done += len(b_ids)
    if done % 2000 < B:
        el = time.time() - t0
        log.info("progress %s/%s  %.1f chunks/s", done, total, done/el if el else 0)
log.info("DONE reembed total=%s dim=%s elapsed=%.1fs", total, dim, time.time()-t0)
