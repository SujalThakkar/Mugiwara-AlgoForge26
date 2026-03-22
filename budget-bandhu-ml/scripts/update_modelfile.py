"""
Script to update Modelfile with proper currency enforcement
Run: python scripts/update_modelfile.py
"""
import os

modelfile_path = r"E:\PICT Techfiesta\BudgetBandhu\budget-bandhu-ml\Modelfile"

modelfile_content = '''FROM E:\\PICT Techfiesta\\BudgetBandhu\\budget-bandhu-ml\\models\\budget-bandhu-q4km.gguf

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
PARAMETER num_predict 256
PARAMETER repeat_penalty 1.1

PARAMETER stop "
