"""Merge LoRA adapter with base model"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

print("[1/4] Loading base model...")
base_model = AutoModelForCausalLM.from_pretrained(
    "microsoft/Phi-3.5-mini-instruct",
    torch_dtype=torch.float16,
    device_map="cpu",
    trust_remote_code=True
)

print("[2/4] Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    "microsoft/Phi-3.5-mini-instruct",
    trust_remote_code=True
)

print("[3/4] Loading LoRA adapter...")
model_with_lora = PeftModel.from_pretrained(
    base_model,
    "models/phi3_chatbot",
    is_trainable=False
)

print("[4/4] Merging and saving...")
merged_model = model_with_lora.merge_and_unload()

merged_model.save_pretrained("models/phi3_merged")
tokenizer.save_pretrained("models/phi3_merged")

print("✅ Merged model saved to models/phi3_merged")
