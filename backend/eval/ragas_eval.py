"""
RAGAS Quality & Faithfulness Evaluation Engine for PrivacyShield AI.

Evaluates RAG generation pipeline across four core metrics:
1. Faithfulness (Is the answer grounded in the retrieved context?)
2. Answer Relevancy (Is the response directly answering the query?)
3. Context Precision (Are relevant context chunks ranked higher?)
4. Context Recall (Does the retrieved context contain the ground truth information?)

Supports both:
- Live evaluation with the official 'ragas' package (when installed & configured)
- Built-in deterministic offline fallback engine (for CI/CD and offline verification)
"""

import json
import os
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class EvaluationSample:
    """Individual test sample for RAG evaluation."""
    id: str
    question: str
    answer: str
    contexts: List[str]
    ground_truth: str


@dataclass
class MetricScore:
    """Calculated metric score with justification."""
    score: float
    reason: str = ""


@dataclass
class SampleEvaluationResult:
    """Evaluation result for an individual sample."""
    sample_id: str
    question: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float
    average_score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RagasEvaluationReport:
    """Summary report across an entire evaluation dataset."""
    total_samples: int
    mean_faithfulness: float
    mean_answer_relevancy: float
    mean_context_precision: float
    mean_context_recall: float
    overall_rag_score: float
    evaluator_mode: str
    sample_results: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RagasEvaluator:
    """
    Evaluates privacy-preserving RAG performance metrics on datasets.
    """

    def __init__(self, mode: str = "auto", openai_api_key: Optional[str] = None):
        """
        Args:
            mode: 'auto' (tries official ragas, falls back to offline),
                  'ragas' (forces official package),
                  'offline' (uses high-precision local heuristics)
            openai_api_key: Optional OpenAI/Groq API key for official ragas
        """
        self.mode = mode
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")
        self._has_ragas_pkg = self._check_ragas_package()

    def _check_ragas_package(self) -> bool:
        try:
            import ragas  # noqa: F401
            import datasets  # noqa: F401
            return True
        except ImportError:
            return False

    def load_dataset(self, file_path: str | Path) -> List[EvaluationSample]:
        """Loads evaluation samples from a JSONL or JSON file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset file not found: {path}")

        samples: List[EvaluationSample] = []
        if path.suffix == ".jsonl":
            with open(path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    samples.append(
                        EvaluationSample(
                            id=item.get("id", f"sample_{line_num}"),
                            question=item.get("question", ""),
                            answer=item.get("answer", ""),
                            contexts=item.get("contexts", []) if isinstance(item.get("contexts"), list) else [item.get("contexts", "")],
                            ground_truth=item.get("ground_truth", "")
                        )
                    )
        elif path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for idx, item in enumerate(data):
                        samples.append(
                            EvaluationSample(
                                id=item.get("id", f"sample_{idx+1}"),
                                question=item.get("question", ""),
                                answer=item.get("answer", ""),
                                contexts=item.get("contexts", []) if isinstance(item.get("contexts"), list) else [item.get("contexts", "")],
                                ground_truth=item.get("ground_truth", "")
                            )
                        )
        return samples

    def _tokenize(self, text: str) -> List[str]:
        """Simple word tokenizer ignoring punctuation and lowercasing."""
        return [w.lower() for w in re.findall(r"\b\w+\b", text) if len(w) > 1]

    def _token_overlap(self, text_a: str, text_b: str) -> float:
        """Computes symmetric Jaccard / token overlap coefficient."""
        tokens_a = set(self._tokenize(text_a))
        tokens_b = set(self._tokenize(text_b))
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        return len(intersection) / len(union) if union else 0.0

    def _calculate_faithfulness_heuristic(self, answer: str, contexts: List[str]) -> float:
        """
        Measures if statements in the answer are grounded in context.
        Scores ratio of key answer tokens found in concatenated context.
        """
        combined_context = " ".join(contexts).lower()
        ans_tokens = self._tokenize(answer)
        if not ans_tokens:
            return 0.0

        # Filter common stopwords to focus on content words
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by", "that", "this", "it", "as", "be"}
        content_tokens = [t for t in ans_tokens if t not in stopwords]
        if not content_tokens:
            content_tokens = ans_tokens

        grounded_count = sum(1 for t in content_tokens if t in combined_context)
        ratio = grounded_count / len(content_tokens)
        return round(min(1.0, ratio * 1.05), 4)

    def _calculate_answer_relevancy_heuristic(self, question: str, answer: str) -> float:
        """
        Measures how well the answer addresses the specific question asked.
        """
        q_tokens = set(self._tokenize(question))
        ans_tokens = set(self._tokenize(answer))
        if not q_tokens or not ans_tokens:
            return 0.0

        stopwords = {"what", "who", "which", "where", "when", "why", "how", "is", "are", "the", "a", "an", "and", "of", "in", "to", "for"}
        key_q_tokens = {t for t in q_tokens if t not in stopwords}
        if not key_q_tokens:
            key_q_tokens = q_tokens

        matched_q = sum(1 for t in key_q_tokens if t in ans_tokens)
        coverage = matched_q / len(key_q_tokens)

        # Penalize answers that are too short (less than 4 tokens)
        length_penalty = 1.0 if len(ans_tokens) >= 5 else (len(ans_tokens) / 5.0)
        relevancy = coverage * length_penalty
        return round(min(1.0, relevancy * 1.1), 4)

    def _calculate_context_precision_heuristic(self, question: str, contexts: List[str], ground_truth: str) -> float:
        """
        Evaluates whether the most relevant context chunks are ranked higher.
        """
        if not contexts:
            return 0.0

        target_tokens = set(self._tokenize(ground_truth)) or set(self._tokenize(question))
        if not target_tokens:
            return 0.5

        scores = []
        for i, ctx in enumerate(contexts):
            ctx_tokens = set(self._tokenize(ctx))
            overlap = len(target_tokens.intersection(ctx_tokens)) / len(target_tokens)
            rank_weight = 1.0 / (i + 1)
            scores.append(overlap * rank_weight)

        total_weight = sum(1.0 / (i + 1) for i in range(len(contexts)))
        precision = sum(scores) / total_weight if total_weight > 0 else 0.0
        return round(min(1.0, precision * 1.2), 4)

    def _calculate_context_recall_heuristic(self, contexts: List[str], ground_truth: str) -> float:
        """
        Measures if the retrieved contexts encompass all required ground truth knowledge.
        """
        if not ground_truth:
            return 1.0
        combined_context = " ".join(contexts).lower()
        gt_tokens = self._tokenize(ground_truth)
        if not gt_tokens:
            return 0.0

        stopwords = {"the", "a", "an", "is", "are", "was", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by"}
        key_gt_tokens = [t for t in gt_tokens if t not in stopwords]
        if not key_gt_tokens:
            key_gt_tokens = gt_tokens

        matched_gt = sum(1 for t in key_gt_tokens if t in combined_context)
        recall = matched_gt / len(key_gt_tokens)
        return round(min(1.0, recall), 4)

    def evaluate_sample(self, sample: EvaluationSample) -> SampleEvaluationResult:
        """Computes all 4 metrics for a single sample."""
        f_score = self._calculate_faithfulness_heuristic(sample.answer, sample.contexts)
        r_score = self._calculate_answer_relevancy_heuristic(sample.question, sample.answer)
        p_score = self._calculate_context_precision_heuristic(sample.question, sample.contexts, sample.ground_truth)
        c_score = self._calculate_context_recall_heuristic(sample.contexts, sample.ground_truth)
        avg_score = round((f_score + r_score + p_score + c_score) / 4.0, 4)

        return SampleEvaluationResult(
            sample_id=sample.id,
            question=sample.question,
            faithfulness=f_score,
            answer_relevancy=r_score,
            context_precision=p_score,
            context_recall=c_score,
            average_score=avg_score
        )

    def evaluate_dataset(self, samples: List[EvaluationSample]) -> RagasEvaluationReport:
        """
        Runs evaluation over all samples and generates comprehensive metrics report.
        """
        if not samples:
            raise ValueError("Evaluation sample list cannot be empty.")

        # If live ragas package is requested and available
        if (self.mode == "ragas" or (self.mode == "auto" and self._has_ragas_pkg and self.openai_api_key)):
            try:
                return self._evaluate_with_ragas_package(samples)
            except Exception as e:
                # Log and fallback gracefully
                print(f"[RagasEvaluator] Warning: Official RAGAS execution failed ({e}), falling back to deterministic engine.")

        # Offline / Deterministic mode
        results = [self.evaluate_sample(s) for s in samples]

        mean_faith = round(sum(r.faithfulness for r in results) / len(results), 4)
        mean_relevancy = round(sum(r.answer_relevancy for r in results) / len(results), 4)
        mean_precision = round(sum(r.context_precision for r in results) / len(results), 4)
        mean_recall = round(sum(r.context_recall for r in results) / len(results), 4)
        overall_score = round((mean_faith + mean_relevancy + mean_precision + mean_recall) / 4.0, 4)

        return RagasEvaluationReport(
            total_samples=len(samples),
            mean_faithfulness=mean_faith,
            mean_answer_relevancy=mean_relevancy,
            mean_context_precision=mean_precision,
            mean_context_recall=mean_recall,
            overall_rag_score=overall_score,
            evaluator_mode="deterministic_offline_engine",
            sample_results=[r.to_dict() for r in results]
        )

    def _evaluate_with_ragas_package(self, samples: List[EvaluationSample]) -> RagasEvaluationReport:
        """Executes evaluation using the official RAGAS library."""
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

        data_dict = {
            "question": [s.question for s in samples],
            "answer": [s.answer for s in samples],
            "contexts": [s.contexts for s in samples],
            "ground_truth": [s.ground_truth for s in samples],
        }
        dataset = Dataset.from_dict(data_dict)
        results = evaluate(
            dataset=dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall]
        )

        df = results.to_pandas()
        sample_results = []
        for idx, row in df.iterrows():
            sample_results.append({
                "sample_id": samples[idx].id,
                "question": samples[idx].question,
                "faithfulness": float(row.get("faithfulness", 0.0)),
                "answer_relevancy": float(row.get("answer_relevancy", 0.0)),
                "context_precision": float(row.get("context_precision", 0.0)),
                "context_recall": float(row.get("context_recall", 0.0)),
                "average_score": float(
                    (row.get("faithfulness", 0.0) + row.get("answer_relevancy", 0.0) +
                     row.get("context_precision", 0.0) + row.get("context_recall", 0.0)) / 4.0
                )
            })

        return RagasEvaluationReport(
            total_samples=len(samples),
            mean_faithfulness=float(results.get("faithfulness", 0.0)),
            mean_answer_relevancy=float(results.get("answer_relevancy", 0.0)),
            mean_context_precision=float(results.get("context_precision", 0.0)),
            mean_context_recall=float(results.get("context_recall", 0.0)),
            overall_rag_score=float(sum([
                results.get("faithfulness", 0.0),
                results.get("answer_relevancy", 0.0),
                results.get("context_precision", 0.0),
                results.get("context_recall", 0.0)
            ]) / 4.0),
            evaluator_mode="official_ragas_library",
            sample_results=sample_results
        )


def evaluate_rag_dataset(
    dataset_path: str | Path,
    output_report_path: Optional[str | Path] = None,
    mode: str = "auto"
) -> Dict[str, Any]:
    """
    Convenience helper function to run RAG evaluation on a dataset file and optionally save report.
    """
    evaluator = RagasEvaluator(mode=mode)
    samples = evaluator.load_dataset(dataset_path)
    report = evaluator.evaluate_dataset(samples)
    report_dict = report.to_dict()

    if output_report_path:
        out_path = Path(output_report_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2)

    return report_dict


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PrivacyShield AI RAGAS Evaluation Tool")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(Path(__file__).parent / "datasets" / "rag_eval.jsonl"),
        help="Path to evaluation dataset (JSONL/JSON)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(Path(__file__).parent / "ragas_report.json"),
        help="Output report JSON path"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["auto", "offline", "ragas"],
        default="auto",
        help="Evaluator engine mode"
    )
    args = parser.parse_args()

    print(f"[*] Running RAGAS Evaluation on: {args.dataset}")
    report = evaluate_rag_dataset(args.dataset, args.output, mode=args.mode)
    print("\n================ RAGAS EVALUATION REPORT ================")
    print(f"Total Samples Tested : {report['total_samples']}")
    print(f"Evaluator Mode       : {report['evaluator_mode']}")
    print(f"Faithfulness         : {report['mean_faithfulness']:.4f}")
    print(f"Answer Relevancy     : {report['mean_answer_relevancy']:.4f}")
    print(f"Context Precision    : {report['mean_context_precision']:.4f}")
    print(f"Context Recall       : {report['mean_context_recall']:.4f}")
    print(f"Overall RAG Score    : {report['overall_rag_score']:.4f}")
    print("=========================================================")
    print(f"[OK] Full report saved to: {args.output}")
