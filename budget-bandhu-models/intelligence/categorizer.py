import os
import json
import joblib
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_DIR = "models/phi3_categorizer"

RULE_KEYWORDS = {
    "Food & Dining":     ["zomato","swiggy","domino","mcdonald","pizza","kfc",
                          "burger","food","khaana","khana","restaurant","cafe",
                          "biryani","dunzo","blinkit food","fassos","box8",
                          "haldiram","behrouz","eatfit","subway"],
    "Transport":         ["uber","ola","irctc","rapido","metro","bus","train",
                          "cab","taxi","petrol","fuel","redbus","yulu","vogo",
                          "indrive","meru","blusmart","dmrc","bmtc","best bus"],
    "Shopping":          ["amazon","flipkart","myntra","meesho","nykaa","ajio",
                          "snapdeal","croma","reliance digital","decathlon",
                          "tata cliq","shopclues","h&m","zara","lifestyle"],
    "Entertainment":     ["netflix","spotify","bookmyshow","hotstar","youtube",
                          "pvr","inox","prime video","sonyliv","zee5","gaana",
                          "jiosaavn","dream11","mpl gaming","winzo"],
    "Utilities & Bills": ["jio","airtel","electricity","bescom","tata power",
                          "gas","water","broadband","internet","recharge","bsnl",
                          "msedcl","tneb","act fibernet","hathway","dth"],
    "Healthcare":        ["apollo","1mg","practo","netmeds","medplus","pharmeasy",
                          "hospital","clinic","medicine","doctor","health",
                          "max hospital","fortis","manipal","cult.fit"],
    "Education":         ["unacademy","byju","coursera","udemy","college fee",
                          "vedantu","upgrad","tuition","exam","course","library",
                          "simplilearn","great learning","duolingo"],
    "Travel":            ["makemytrip","goibibo","oyo","yatra","airbnb","indigo",
                          "air india","spicejet","vistara","hotel","flight",
                          "treebo","fabhotel","akasaair"],
    "Groceries":         ["bigbasket","dmart","jiomart","zepto","blinkit",
                          "grocery","sabzi","kirana","milk","vegetables",
                          "spencer","reliance fresh","milkbasket","zepto"],
    "Transfers & ATM":   ["upi/","neft","atm","imps","rtgs","transfer",
                          "send money","withdrawal","wallet load","rent",
                          "phonepe","gpay","paytm"],
}


class CategoryResult:
    def __init__(self, category: str, confidence: float,
                 alternatives: list, model_version: str = "1.0"):
        self.category      = category
        self.confidence    = round(confidence, 4)
        self.alternatives  = alternatives          # list[(str, float)]
        self.model_version = model_version

    def dict(self) -> dict:
        return {
            "category":      self.category,
            "confidence":    self.confidence,
            "alternatives":  self.alternatives,
            "model_version": self.model_version,
        }

    def __repr__(self):
        return (f"CategoryResult(category={self.category!r}, "
                f"confidence={self.confidence:.2f})")


class TransactionCategorizer:
    """
    Categorises Indian UPI transaction descriptions into 10 categories.

    Architecture:
        all-MiniLM-L6-v2 (sentence-transformers, CUDA) →
        384-dim embedding →
        LogisticRegression(C=10) →
        10-class softmax

    Falls back to keyword rules if model files are absent.

    Example:
        cat = TransactionCategorizer()
        r   = cat.categorize("ZOMATO*ORDER82910")
        # CategoryResult(category='Food & Dining', confidence=0.97)
    """

    MODEL_VERSION = "1.0"

    def __init__(self, model_dir: str = MODEL_DIR):
        self._model_dir   = model_dir
        self._classifier  = None
        self._label_enc   = None
        self._embedder    = None
        self._metadata    = {}
        self._loaded      = False
        self._load()

    # ── Initialisation ────────────────────────────────────────────────
    def _load(self):
        clf_p  = os.path.join(self._model_dir, "classifier.joblib")
        le_p   = os.path.join(self._model_dir, "label_encoder.joblib")
        meta_p = os.path.join(self._model_dir, "model_metadata.json")

        if not (os.path.exists(clf_p) and os.path.exists(le_p)):
            print("[Categorizer] ⚠ Model files not found — using keyword fallback.")
            return
        try:
            self._classifier = joblib.load(clf_p)
            self._label_enc  = joblib.load(le_p)
            self._embedder   = SentenceTransformer(
                "all-MiniLM-L6-v2",
                device="cuda"
            )
            if os.path.exists(meta_p):
                with open(meta_p) as f:
                    self._metadata = json.load(f)
            self._loaded = True
            acc = self._metadata.get("accuracy", "?")
            print(f"[Categorizer] ✅ Loaded  (accuracy={acc})")
        except Exception as e:
            print(f"[Categorizer] ⚠ Load error: {e} — using keyword fallback.")

    def is_loaded(self) -> bool:
        return self._loaded

    # ── Public API ────────────────────────────────────────────────────
    def categorize(self, description: str) -> CategoryResult:
        """
        Categorise a single description.

        Args:
            description: raw UPI description string
        Returns:
            CategoryResult
        """
        if self._loaded:
            return self._ml_categorize([description])[0]
        return self._rule_categorize(description)

    def categorize_batch(self, descriptions: list[str]) -> list[CategoryResult]:
        """
        Categorise a batch efficiently (GPU-batched encoding).

        Args:
            descriptions: list of raw UPI strings
        Returns:
            list[CategoryResult]
        """
        if not descriptions:
            return []
        if self._loaded:
            return self._ml_categorize(descriptions)
        return [self._rule_categorize(d) for d in descriptions]

    # ── ML path ──────────────────────────────────────────────────────
    def _ml_categorize(self, descriptions: list[str]) -> list[CategoryResult]:
        try:
            embeddings = self._embedder.encode(
                descriptions,
                batch_size=512,
                show_progress_bar=False,
                normalize_embeddings=True,
                device="cuda",
                convert_to_numpy=True,
            )
            probas  = self._classifier.predict_proba(embeddings)
            version = self._metadata.get("model_version", self.MODEL_VERSION)
            results = []
            for proba in probas:
                order    = np.argsort(proba)[::-1]
                top_cat  = self._label_enc.classes_[order[0]]
                top_conf = float(proba[order[0]])
                alts     = [
                    (self._label_enc.classes_[i], round(float(proba[i]), 4))
                    for i in order[1:4]
                ]
                results.append(CategoryResult(top_cat, top_conf, alts, version))
            return results
        except Exception as e:
            print(f"[Categorizer] ML inference error: {e} — falling back.")
            return [self._rule_categorize(d) for d in descriptions]

    # ── Rule-based fallback ───────────────────────────────────────────
    def _rule_categorize(self, description: str) -> CategoryResult:
        desc = description.lower()
        scores: dict[str, int] = {}
        for cat, keywords in RULE_KEYWORDS.items():
            hit = sum(1 for kw in keywords if kw in desc)
            if hit:
                scores[cat] = hit
        if scores:
            total = sum(scores.values())
            ranked = sorted(scores.items(), key=lambda x: -x[1])
            best, best_score = ranked[0]
            conf = best_score / total
            alts = [(c, round(s / total, 4)) for c, s in ranked[1:4]]
            return CategoryResult(best, conf, alts, "rule_fallback_v1")
        return CategoryResult("Transfers & ATM", 0.30, [], "rule_fallback_v1")