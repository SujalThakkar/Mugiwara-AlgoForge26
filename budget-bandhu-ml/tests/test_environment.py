"""
Environment Validation
Checks all dependencies are installed correctly.

Run: python tests/test_environment.py
"""
import sys

def test_python_version():
    """Check Python version"""
    print(f"Python: {sys.version}")
    assert sys.version_info >= (3, 9), "Python 3.9+ required"
    print("✅ Python version OK")

def test_pytorch():
    """Test PyTorch installation"""
    try:
        import torch
        print(f"PyTorch: {torch.__version__}")
        print(f"CUDA Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"CUDA Version: {torch.version.cuda}")
            print(f"GPU: {torch.cuda.get_device_name(0)}")
        print("✅ PyTorch OK")
    except ImportError as e:
        print(f"❌ PyTorch not installed: {e}")
        sys.exit(1)

def test_transformers():
    """Test Transformers installation"""
    try:
        import transformers
        print(f"Transformers: {transformers.__version__}")
        print("✅ Transformers OK")
    except ImportError as e:
        print(f"❌ Transformers not installed: {e}")
        sys.exit(1)

def test_peft():
    """Test PEFT installation"""
    try:
        import peft
        print(f"PEFT: {peft.__version__}")
        print("✅ PEFT OK")
    except ImportError as e:
        print(f"❌ PEFT not installed: {e}")
        sys.exit(1)

def test_fastapi():
    """Test FastAPI installation"""
    try:
        import fastapi
        print(f"FastAPI: {fastapi.__version__}")
        print("✅ FastAPI OK")
    except ImportError as e:
        print(f"❌ FastAPI not installed: {e}")
        sys.exit(1)

def test_sklearn():
    """Test scikit-learn installation"""
    try:
        import sklearn
        print(f"scikit-learn: {sklearn.__version__}")
        print("✅ scikit-learn OK")
    except ImportError as e:
        print(f"❌ scikit-learn not installed: {e}")
        sys.exit(1)

def test_model_loading():
    """Test loading base model (without adapter)"""
    try:
        from transformers import AutoTokenizer
        print("\nTesting model loading...")
        tokenizer = AutoTokenizer.from_pretrained(
            "microsoft/Phi-3.5-mini-instruct",
            trust_remote_code=True
        )
        print("✅ Base model tokenizer loaded")
    except Exception as e:
        print(f"⚠️ Model loading failed (may need internet): {e}")

def main():
    print("="*60)
    print("ENVIRONMENT VALIDATION")
    print("="*60)
    
    test_python_version()
    test_pytorch()
    test_transformers()
    test_peft()
    test_fastapi()
    test_sklearn()
    test_model_loading()
    
    print("\n" + "="*60)
    print("✅ ALL DEPENDENCIES INSTALLED CORRECTLY")
    print("="*60)
    print("\nYou're ready to run tests!")

if __name__ == "__main__":
    main()
