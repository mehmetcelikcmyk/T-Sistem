"""
Metin Vektörleştirme (Embedding) Modülü
"""
from typing import List

def get_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Verilen metin dizisini sayısal vektörlere dönüştürür.
    """
    # TODO: Birhan tarafından Issue #3 kapsamında kodlanacak.
    return [[0.0] * 384 for _ in texts]
