from typing import Any, Dict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from app.services.adapters.base import BaseAdapter

_TRAINING_TEXT = [
    "this product is amazing and works great",
    "I love how well this performs",
    "excellent quality, highly recommend",
    "terrible experience, complete waste of money",
    "this broke after one day, awful",
    "worst purchase I have ever made",
]
_TRAINING_LABELS = [
    "positive",
    "positive",
    "positive",
    "negative",
    "negative",
    "negative",
]

_vectorizer = TfidfVectorizer()
_X = _vectorizer.fit_transform(_TRAINING_TEXT)
_model = LogisticRegression()
_model.fit(_X, _TRAINING_LABELS)


class TextClassificationAdapter(BaseAdapter):
    task_type = "text_classification"
    is_async = False

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = payload["text"]
        vector = _vectorizer.transform([text])
        label = _model.predict(vector)[0]
        confidence = float(max(_model.predict_proba(vector)[0]))
        return {"label": label, "confidence": confidence}
