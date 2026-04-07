from typing import List, Literal, Optional
import os
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
from inventory.ports.embedding_provider import EmbeddingProvider
from inventory.domain.exceptions import ValidationError

TextType = Literal["query", "passage"]

class E5BaseEmbeddingProvider(EmbeddingProvider):
    MODEL_NAME = "intfloat/e5-base-v2"
    DEFAULT_BATCH_SIZE = 32
    MAX_LENGTH = 512
    PREFIX_MAP: dict[TextType, str] = {
        "query": "query: ",
        "passage": "passage: ",
    }
    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None, batch_size: int = DEFAULT_BATCH_SIZE):
        self._model_name = model_name or os.environ.get("E5_MODEL_PATH") or self.MODEL_NAME
        self.batch_size = batch_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            self.model = AutoModel.from_pretrained(self._model_name)
            self.model.to(self.device)
            self.model.eval()
        except Exception as e:
            raise ValidationError(f"Failed to load E5 model '{self._model_name}': {e}") from e
        self._embedding_dimension: int = self.model.config.hidden_size

    def generate_embeddings(self, texts: List[str], text_type: str = "passage",) -> List[List[float]]:

        if not texts:
            return []
        self._validate_texts(texts)
        if text_type not in self.PREFIX_MAP:
            text_type = "passage"
        prefix = self.PREFIX_MAP[text_type]
        prefixed = [f"{prefix}{t.strip()}" for t in texts]
        all_embeddings: List[List[float]] = []
        for batch_start in range(0, len(prefixed), self.batch_size):
            batch = prefixed[batch_start : batch_start + self.batch_size]
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
        return all_embeddings

    def get_embedding_dimension(self) -> int:
        return self._embedding_dimension

    def _validate_texts(self, texts: List[str]) -> None:
        blank = [i for i, t in enumerate(texts) if not t or not t.strip()]
        if blank:
            raise ValidationError(f"Empty or whitespace-only texts at indices: {blank}")

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        try:
            encoded = self.tokenizer(texts,max_length=self.MAX_LENGTH,padding=True,truncation=True,return_tensors="pt",)
            encoded = {k: v.to(self.device) for k, v in encoded.items()}
            with torch.no_grad():
                output = self.model(**encoded)
                embeddings = self._average_pool(output.last_hidden_state, encoded["attention_mask"],)
                embeddings = F.normalize(embeddings, p=2, dim=1)
            return embeddings.cpu().numpy().tolist()
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Failed to generate embeddings: {e}") from e
        finally:
            if self.device.startswith("cuda"):
                torch.cuda.empty_cache()

    @staticmethod
    def _average_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor,) -> torch.Tensor:
        hidden = last_hidden_state.masked_fill(~attention_mask.unsqueeze(-1).bool(), 0.0)
        return hidden.sum(dim=1) / attention_mask.sum(dim=1, keepdim=True)


embedding_provider = E5BaseEmbeddingProvider()