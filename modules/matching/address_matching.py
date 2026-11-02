import gc
from typing import List, Tuple

import hnswlib
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm

try:
    import torch
except ImportError:  # torch optional
    torch = None

MODEL_NAME = "sentence-transformers/LaBSE"
BATCH_SIZE = 128
TOP_K = 1
THRESHOLD = 0.80
EF_CONSTR = 200
EF_SEARCH = 200


def _free_accelerator():
    """Release accelerator (MPS/CUDA) cache + Python garbage."""
    gc.collect()
    if torch is None:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        torch.mps.empty_cache()


def _make_text(df: pd.DataFrame, name_col: str, addr_col: str | None) -> List[str]:
    if addr_col:
        return (
            df[name_col].fillna("").astype(str).str.strip() + ", " + df[addr_col].fillna("").astype(str).str.strip()
        ).tolist()
    else:
        # address already baked into a single column
        return df[name_col].fillna("").astype(str).str.strip().tolist()


def _embed(model: SentenceTransformer, texts: List[str], batch: int) -> np.ndarray:
    return model.encode(
        texts,
        batch_size=batch,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    ).astype("float32")


def build_hnsw_index(vectors: np.ndarray) -> hnswlib.Index:
    dim = vectors.shape[1]
    index = hnswlib.Index(space="cosine", dim=dim)
    index.init_index(max_elements=len(vectors), ef_construction=EF_CONSTR, M=32)
    index.add_items(vectors, np.arange(len(vectors)))
    index.set_ef(EF_SEARCH)
    return index


def match_tables(
    internal_df: pd.DataFrame,
    external_df: pd.DataFrame,
    *,
    internal_name_col: str = "name",
    internal_addr_col: str = "address",
    external_name_col: str = "name",
    external_addr_col: str = "address",
    top_k: int = TOP_K,
    threshold: float = THRESHOLD,
    batch_size: int = BATCH_SIZE,
    model_name: str = MODEL_NAME,
) -> pd.DataFrame:
    """Return DataFrame of matches using hnswlib for similarity search."""
    # 1. Embed external table and build HNSW index
    model = SentenceTransformer(model_name)
    ext_vecs = _embed(model, _make_text(external_df, external_name_col, external_addr_col), batch_size)
    _free_accelerator()
    index = build_hnsw_index(ext_vecs)

    # 2. Embed & query internal rows in batches
    int_texts = _make_text(internal_df, internal_name_col, internal_addr_col)
    rows: List[Tuple[int, object, object, float]] = []

    for start in tqdm(range(0, len(int_texts), batch_size), desc="Matching"):
        try:
            sub_vecs = _embed(model, int_texts[start : start + batch_size], batch_size)
        except RuntimeError as e:
            if "out of memory" in str(e).lower() and batch_size > 4:
                new_bs = max(4, batch_size // 2)
                print(f"OOM; retry with batch_size={new_bs}")
                return match_tables(
                    internal_df,
                    external_df,
                    internal_name_col=internal_name_col,
                    internal_addr_col=internal_addr_col,
                    external_name_col=external_name_col,
                    external_addr_col=external_addr_col,
                    top_k=top_k,
                    threshold=threshold,
                    batch_size=new_bs,
                    model_name=model_name,
                )
            else:
                raise

        # hnswlib works on batches directly
        labels, dists = index.knn_query(sub_vecs, k=top_k)  # shapes: (batch, k)
        _free_accelerator()

        for offset, (lbl_row, dist_row) in enumerate(zip(labels, dists)):
            int_idx = start + offset
            for ext_idx, dist in zip(lbl_row, dist_row):
                score = 1.0 - dist if dist is not None else 0.0
                if score < threshold:
                    continue
                rows.append(
                    (
                        int_idx,
                        internal_df.index[int_idx],  # keep index label as-is
                        external_df.index[int(ext_idx)],  # ext_idx is already scalar
                        float(score),
                    )
                )

    # 3. Assemble tidy result DataFrame
    result = (
        pd.DataFrame(rows, columns=["internal_row", "internal_idx", "external_idx", "score"])
        .merge(internal_df.add_prefix("int_"), left_on="internal_idx", right_index=True)
        .merge(external_df.add_prefix("ext_"), left_on="external_idx", right_index=True)
        .reset_index(drop=True)
    )
    return result
