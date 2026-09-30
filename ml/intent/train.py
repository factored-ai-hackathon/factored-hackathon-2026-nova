"""Train, evaluate and export the intent classifier (decision 29). Model card: ml/README.md.

    uv run python ml/intent/train.py          (from the repo root; ~10 s, no AWS)

Reads the team-written phrases in ml/intent/data (train_*.jsonl for fitting and model selection,
test_*.jsonl only for the final numbers), compares the model with two baselines and writes:
- backend/app/agent/intent_model.json: vocabulary, idf and coefficients for the plain-Python
  predict in backend/app/agent/intent.py (no scikit-learn in the Lambda)
- backend/tests/fixtures/intent_parity.json: scikit-learn's probabilities on sample texts, so a
  backend test checks the plain-Python predict matches
- ml/intent/metrics.json: the numbers in the model card
"""

import importlib.util
import itertools
import json
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import FeatureUnion, make_pipeline

HERE = Path(__file__).parent
REPO = HERE.parent.parent
MODEL_OUT = REPO / "backend/app/agent/intent_model.json"
PARITY_OUT = REPO / "backend/tests/fixtures/intent_parity.json"
METRICS_OUT = HERE / "metrics.json"

CLASSES = ["transactional", "product", "complaint", "technical", "commercial", "retention", "other"]
LANGS = ["es", "pt"]
SEED = 0
# Confident = the model's top probability reaches this on out-of-fold training predictions with
# at least this precision (chosen on train only, never on test).
TARGET_PRECISION = 0.9


def load(split: str) -> list[dict]:
    rows = []
    for lang in LANGS:
        for line in (HERE / f"data/{split}_{lang}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line) | {"lang": lang})
    return rows


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", text))


def char_ngrams(text: str, n: int = 4) -> set[str]:
    t = f" {normalize(text)} "
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def leakage_report(train: list[dict], test: list[dict]) -> dict:
    """Exact duplicates (after normalizing) must be zero; near duplicates are reported."""
    train_norm = {normalize(r["text"]) for r in train}
    exact = [r["text"] for r in test if normalize(r["text"]) in train_norm]
    train_grams = [char_ngrams(r["text"]) for r in train]
    nearest = []
    for r in test:
        grams = char_ngrams(r["text"])
        nearest.append(max(len(grams & g) / len(grams | g) for g in train_grams))
    nearest = np.array(nearest)
    return {
        "exact_duplicates": len(exact),
        "exact_duplicate_texts": exact,
        "nearest_train_jaccard_char4": {
            "median": round(float(np.median(nearest)), 3),
            "p90": round(float(np.quantile(nearest, 0.9)), 3),
            "max": round(float(nearest.max()), 3),
            "share_above_0.8": round(float((nearest > 0.8).mean()), 3),
        },
    }


# --- baselines ------------------------------------------------------------------------------------

# Keyword rules, ES + PT, on normalized text (no accents), checked in this order. Written from
# general banking vocabulary, the kind of routing rules a contact center starts with.
KEYWORDS = [
    (
        "retention",
        [
            "cancel",
            "cerrar",
            "encerr",
            "dar de baja",
            "baja de",
            "me voy",
            "me cambio",
            "otro banco",
            "outro banco",
            "mudar de banco",
            "portabilidad",
            "portabilidade",
            "dejar de ser cliente",
            "deixar de ser cliente",
            "fechar a conta",
        ],
    ),
    (
        "complaint",
        [
            "queja",
            "reclam",
            "molest",
            "harto",
            "cansad",
            "pesim",
            "no reconozco",
            "nao reconheco",
            "indebid",
            "sin autoriz",
            "sem autoriz",
            "verguenza",
            "vergonha",
            "contest",
            "disput",
            "robaron",
            "roubaram",
            "clon",
            "injust",
            "absurd",
            "abuso",
            "mal servicio",
            "mau atendimento",
            "inaceptable",
            "inaceitavel",
        ],
    ),
    (
        "technical",
        [
            "app",
            "aplicacion",
            "aplicativo",
            "contrasena",
            "senha",
            "clave",
            "codigo",
            "sms",
            "token",
            "error",
            "erro",
            "login",
            "sesion",
            "sessao",
            "pagina",
            "site",
            "web",
            "huella",
            "digital",
            "usuario",
            "no carga",
            "nao carrega",
        ],
    ),
    (
        "commercial",
        [
            "prestamo",
            "emprestimo",
            "credito",
            "financiamento",
            "hipotec",
            "promo",
            "invert",
            "invest",
            "seguro",
            "aumentar",
            "upgrade",
            "oferta",
            "preaprobado",
            "pre-aprovado",
            "pre aprovado",
            "solicitar",
            "contratar",
        ],
    ),
    (
        "product",
        [
            "tasa",
            "taxa",
            "interes",
            "juros",
            "beneficio",
            "comision",
            "tarifa",
            "anualidad",
            "anuidade",
            "cuota de manejo",
            "puntos",
            "pontos",
            "millas",
            "milhas",
            "activar",
            "ativar",
            "pin",
            "limite",
            "requisito",
            "costo",
            "custo",
        ],
    ),
    (
        "transactional",
        [
            "saldo",
            "movimiento",
            "movimentac",
            "lancamento",
            "transfer",
            "pix",
            "deposit",
            "retir",
            "saque",
            "sacar",
            "pago",
            "pagar",
            "pagamento",
            "fatura",
            "extracto",
            "extrato",
            "compra",
            "nomina",
            "salario",
            "cajero",
            "caixa",
        ],
    ),
]


def keyword_baseline(text: str) -> str:
    t = normalize(text)
    for label, words in KEYWORDS:
        if any(re.search(rf"\b{re.escape(w)}", t) for w in words):
            return label
    return "other"


# --- model ----------------------------------------------------------------------------------------


def build_model(C: float, char_range: tuple[int, int]) -> object:
    common = {"lowercase": True, "strip_accents": "unicode", "sublinear_tf": True}
    features = FeatureUnion(
        [
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), **common)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=char_range, **common)),
        ]
    )
    return make_pipeline(features, LogisticRegression(C=C, max_iter=5000, random_state=SEED))


def metrics(y_true: list[str], y_pred: list[str]) -> dict:
    return {
        "n": len(y_true),
        "accuracy": round(accuracy_score(y_true, y_pred), 3),
        "macro_f1": round(f1_score(y_true, y_pred, labels=CLASSES, average="macro"), 3),
        "f1_by_class": dict(
            zip(
                CLASSES,
                [round(x, 3) for x in f1_score(y_true, y_pred, labels=CLASSES, average=None)],
                strict=True,
            )
        ),
    }


def ece(confidence: np.ndarray, correct: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error of the top-class probability."""
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in itertools.pairwise(edges):
        mask = (confidence > lo) & (confidence <= hi)
        if mask.any():
            total += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return round(float(total), 3)


def choose_threshold(proba: np.ndarray, y: np.ndarray, classes: np.ndarray) -> float:
    """Smallest top-probability threshold whose confident predictions reach TARGET_PRECISION."""
    top = proba.max(axis=1)
    correct = classes[proba.argmax(axis=1)] == y
    for t in np.arange(0.2, 0.96, 0.01):
        mask = top >= t
        if mask.sum() >= 20 and correct[mask].mean() >= TARGET_PRECISION:
            return round(float(t), 2)
    return 0.95


def export(model, threshold: float, rates: dict, report: dict) -> dict:
    features, clf = model.steps[0][1], model.steps[-1][1]
    vectorizers = []
    for _, vec in features.transformer_list:
        vectorizers.append(
            {
                "analyzer": vec.analyzer,
                "ngram_range": list(vec.ngram_range),
                "lowercase": vec.lowercase,
                "strip_accents": vec.strip_accents,
                "sublinear_tf": vec.sublinear_tf,
                "token_pattern": vec.token_pattern,
                "vocabulary": {k: int(v) for k, v in sorted(vec.vocabulary_.items())},
                "idf": [float(x) for x in vec.idf_],
            }
        )
    return {
        "version": datetime.now(UTC).strftime("%Y-%m-%d"),
        "classes": [str(c) for c in clf.classes_],
        "vectorizers": vectorizers,
        "coef": [[float(x) for x in row] for row in clf.coef_],
        "intercept": [float(x) for x in clf.intercept_],
        "threshold": threshold,
        "resolution_rates": rates,
        "trained_on": "team-written phrases (ml/intent/data/train_*.jsonl), not bank customers",
        "test_macro_f1": report["model"]["test"]["macro_f1"],
    }


def main() -> None:
    train, test = load("train"), load("test")
    leakage = leakage_report(train, test)
    if leakage["exact_duplicates"]:
        sys.exit(f"test phrases also in train: {leakage['exact_duplicate_texts']}")

    X_train = [r["text"] for r in train]
    y_train = np.array([r["label"] for r in train])
    X_test = [r["text"] for r in test]
    y_test = np.array([r["label"] for r in test])

    # Model selection: 5-fold CV on train only.
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    grid = []
    for C in (1, 3, 10, 30, 100, 300, 1000):
        for char_range in ((2, 4), (3, 5)):
            pred = cross_val_predict(build_model(C, char_range), X_train, y_train, cv=cv)
            grid.append((f1_score(y_train, pred, average="macro"), C, char_range))
    best_f1, C, char_range = max(grid, key=lambda g: g[0])
    oof = cross_val_predict(
        build_model(C, char_range), X_train, y_train, cv=cv, method="predict_proba"
    )
    classes = np.array(sorted(set(y_train)))
    threshold = choose_threshold(oof, y_train, classes)

    model = build_model(C, char_range).fit(X_train, y_train)
    proba = model.predict_proba(X_test)
    pred = model.classes_[proba.argmax(axis=1)]
    top = proba.max(axis=1)
    correct = pred == y_test
    confident = top >= threshold

    majority = max(set(y_train), key=list(y_train).count)
    report = {
        "data": {
            "train": {lang: sum(r["lang"] == lang for r in train) for lang in LANGS},
            "test": {lang: sum(r["lang"] == lang for r in test) for lang in LANGS},
            "classes": CLASSES,
            "provenance": "team-generated (written for this project with Claude Code); no bank "
            "customer text: the dataset's transcripts carry no signal (see ml/README.md)",
        },
        "leakage": leakage,
        "selection": {
            "cv": "5-fold stratified on train",
            "best": {
                "C": C,
                "char_ngram_range": list(char_range),
                "cv_macro_f1": round(best_f1, 3),
            },
            "grid": [
                {"C": c, "char_ngram_range": list(r), "cv_macro_f1": round(f, 3)}
                for f, c, r in grid
            ],
            "threshold": threshold,
            "threshold_rule": f"smallest top probability with >= {TARGET_PRECISION} precision "
            "on out-of-fold train predictions",
        },
        "majority_baseline": {"test": metrics(list(y_test), [majority] * len(y_test))},
        "keyword_baseline": {"test": metrics(list(y_test), [keyword_baseline(t) for t in X_test])},
        "model": {
            "test": metrics(list(y_test), list(pred))
            | {
                "ece": ece(top, correct),
                "confident_coverage": round(float(confident.mean()), 3),
                "confident_accuracy": round(float(correct[confident].mean()), 3),
            },
        },
        "by_language": {},
        "confusion_matrix": {
            "labels": CLASSES,
            "rows_true_cols_pred": confusion_matrix(y_test, pred, labels=CLASSES).tolist(),
        },
    }
    for lang in LANGS:
        idx = [i for i, r in enumerate(test) if r["lang"] == lang]
        yt = [y_test[i] for i in idx]
        report["by_language"][lang] = {
            "keyword_baseline": metrics(yt, [keyword_baseline(X_test[i]) for i in idx]),
            "model": metrics(yt, [pred[i] for i in idx]),
        }

    rates = json.loads((HERE / "resolution_rates.json").read_text(encoding="utf-8"))["by_intent"]
    spec = export(model, threshold, rates, report)
    MODEL_OUT.write_text(json.dumps(spec, ensure_ascii=False, separators=(",", ":")), "utf-8")

    # Parity: the plain-Python predict must give scikit-learn's probabilities.
    # Loaded by path: the app.agent package imports LangChain, which this environment lacks.
    module_spec = importlib.util.spec_from_file_location(
        "intent", REPO / "backend/app/agent/intent.py"
    )
    intent = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(intent)
    plain = intent.IntentModel(spec)
    samples = X_test[::7] + ["", "!!!", "ÁÉÍÓÚ ñ ç ãõ", "saldo saldo saldo"]
    expected = model.predict_proba(samples)
    worst = 0.0
    for text, row in zip(samples, expected, strict=True):
        got = plain.predict_proba(text)
        worst = max(worst, max(abs(got[c] - p) for c, p in zip(model.classes_, row, strict=True)))
    if worst > 1e-9:
        sys.exit(f"plain-Python predict differs from scikit-learn by {worst}")
    PARITY_OUT.parent.mkdir(parents=True, exist_ok=True)
    PARITY_OUT.write_text(
        json.dumps(
            [
                {"text": t, "proba": dict(zip(model.classes_, map(float, p), strict=True))}
                for t, p in zip(samples, expected, strict=True)
            ],
            ensure_ascii=False,
            indent=1,
        ),
        "utf-8",
    )
    report["export"] = {
        "model_json_kb": round(MODEL_OUT.stat().st_size / 1024),
        "parity_max_abs_diff": worst,
    }
    METRICS_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")

    m, k = report["model"]["test"], report["keyword_baseline"]["test"]
    print(f"train {len(train)}  test {len(test)}  leakage {leakage['nearest_train_jaccard_char4']}")
    print(f"selected C={C} char={char_range} cv macro-F1={best_f1:.3f} threshold={threshold}")
    print(f"majority  macro-F1 {report['majority_baseline']['test']['macro_f1']}")
    print(f"keywords  macro-F1 {k['macro_f1']}  acc {k['accuracy']}")
    print(
        f"model     macro-F1 {m['macro_f1']}  acc {m['accuracy']}  ece {m['ece']}  "
        f"confident {m['confident_coverage']:.0%} at acc {m['confident_accuracy']}"
    )
    for lang, r in report["by_language"].items():
        print(
            f"  {lang}: keywords {r['keyword_baseline']['macro_f1']}  model {r['model']['macro_f1']}"
        )
    print(f"model json {report['export']['model_json_kb']} KB, parity diff {worst:.1e}")


if __name__ == "__main__":
    main()
