"""
Metin Temizleme ve Chunking Modülü
"""
from typing import List, Dict, Any

def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> List[str]:
    """
    Rapor metnini semantik arama ve LLM analizi için anlamlı parçalara böler.
    """
    # TODO: Birhan tarafından Issue #1 kapsamında LangChain TextSplitter ile kodlanacak.
    return [text] if text else []
