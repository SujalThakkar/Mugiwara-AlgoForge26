import torch

print("=" * 50)
print("PyTorch")
print(f"  CUDA available : {torch.cuda.is_available()}")
print(f"  GPU            : {torch.cuda.get_device_name(0)}")
print(f"  VRAM           : {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
x = torch.randn(1000, 1000).cuda()
print(f"  Test tensor    : {x.device} ✅")

print("\nSentenceTransformers")
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2", device="cuda")
test = model.encode(["test sentence"])
print(f"  Embedding shape: {test.shape} on CUDA ✅")

print("\nAll systems GO — ready to train 🚀")