import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoImageProcessor, AutoModel


class ImageEncoder:
    def __init__(self, model_name: str = "facebook/dinov2-small"):
        self.model_name = model_name

        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"

        self.processor = AutoImageProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()

    @torch.inference_mode()
    def encode(self, images: list[Image.Image]) -> torch.Tensor:
        inputs = self.processor(images=images, return_tensors="pt")
        inputs = inputs.to(self.device)
        outputs = self.model(**inputs)

        embeddings = outputs.last_hidden_state[:, 0]
        return F.normalize(embeddings, p=2, dim=-1).cpu()
